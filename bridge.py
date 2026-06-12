#!/usr/bin/env python3
"""
Media Search Bridge for Radarr/Sonarr (Spanish/Castellano Priority)
Automatically searches Prowlarr, sends to Transmission, moves completed downloads,
notifies via Telegram, and refreshes Jellyfin.

Usage:
  python3 bridge.py movies     # Run Radarr movie search and import
  python3 bridge.py series     # Run Sonarr TV series search and import
  python3 bridge.py all        # Run both
"""
import os
import sys
import json
import urllib.request
import urllib.parse
import re
import shutil
import time
import base64
import logging
from datetime import datetime

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log = logging.getLogger("media_bridge")

# ==========================================
# ⚙️ CONFIGURATION RESOLVER
# ==========================================
def load_config():
    config = {}
    # Load config.json if present
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception as e:
            log.warning(f"Failed to read config.json: {e}")

    # Resolve settings (Environment variable has priority, then config.json, then default)
    def get_val(env_name, json_path, default=""):
        val = os.environ.get(env_name)
        if val is not None:
            return val
        curr = config
        for key in json_path:
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
            else:
                return default
        return curr if curr is not None else default

    return {
        "RADARR_URL": get_val("RADARR_URL", ["radarr", "url"], "http://localhost:7878/api/v3"),
        "RADARR_KEY": get_val("RADARR_KEY", ["radarr", "api_key"], ""),
        "RADARR_ROOT": get_val("RADARR_ROOT", ["radarr", "root_folder_path"], "/movies"),
        "RADARR_QUALITY": int(get_val("RADARR_QUALITY", ["radarr", "quality_profile_id"], 1)),
        
        "SONARR_URL": get_val("SONARR_URL", ["sonarr", "url"], "http://localhost:8989/api/v3"),
        "SONARR_KEY": get_val("SONARR_KEY", ["sonarr", "api_key"], ""),
        "SONARR_ROOT": get_val("SONARR_ROOT", ["sonarr", "root_folder_path"], "/tv"),
        "SONARR_QUALITY": int(get_val("SONARR_QUALITY", ["sonarr", "quality_profile_id"], 1)),
        
        "PROWLARR_URL": get_val("PROWLARR_URL", ["prowlarr", "url"], "http://localhost:9696"),
        "PROWLARR_KEY": get_val("PROWLARR_KEY", ["prowlarr", "api_key"], ""),
        
        "TRANSMISSION_URL": get_val("TRANSMISSION_URL", ["transmission", "url"], "http://localhost:9091/transmission/rpc"),
        "TRANSMISSION_USER": get_val("TRANSMISSION_USER", ["transmission", "username"], "admin"),
        "TRANSMISSION_PASS": get_val("TRANSMISSION_PASS", ["transmission", "password"], "power!!"),
        "DOWNLOAD_DIR_MOVIES": get_val("TRANSMISSION_DOWNLOAD_DIR_MOVIES", ["transmission", "download_dir_movies"], "/downloads/radarr"),
        "DOWNLOAD_DIR_TV": get_val("TRANSMISSION_DOWNLOAD_DIR_TV", ["transmission", "download_dir_tv"], "/downloads/tv-sonarr"),
        
        "JELLYFIN_URL": get_val("JELLYFIN_URL", ["jellyfin", "url"], "http://localhost:8096"),
        "JELLYFIN_KEY": get_val("JELLYFIN_KEY", ["jellyfin", "api_key"], ""),
        
        "TELEGRAM_BOT_TOKEN": get_val("TELEGRAM_BOT_TOKEN", ["telegram", "bot_token"], ""),
        "TELEGRAM_CHAT_ID": get_val("TELEGRAM_CHAT_ID", ["telegram", "chat_id"], ""),
        
        "GRABBED_MOVIES_FILE": get_val("GRABBED_MOVIES_FILE", ["paths", "grabbed_movies_file"], "movies_grabbed.json"),
        "GRABBED_TV_FILE": get_val("GRABBED_TV_FILE", ["paths", "grabbed_tv_file"], "tv_grabbed.json"),
        "DESTINATION_MOVIES_DIR": get_val("DESTINATION_MOVIES_DIR", ["paths", "destination_movies_dir"], "/mnt/datos/complete/Pelis"),
        "DESTINATION_TV_DIR": get_val("DESTINATION_TV_DIR", ["paths", "destination_tv_dir"], "/mnt/datos/complete/Series"),
        "TRANSMISSION_MOVIES_DIR_ON_HOST": get_val("TRANSMISSION_MOVIES_DIR_ON_HOST", ["paths", "transmission_movies_dir_on_host"], "/mnt/datos/complete/radarr"),
        "TRANSMISSION_TV_DIR_ON_HOST": get_val("TRANSMISSION_TV_DIR_ON_HOST", ["paths", "transmission_tv_dir_on_host"], "/mnt/datos/complete/tv-sonarr"),
    }

CFG = load_config()

# ==========================================
# 🛠️ UTILITY CLASSES & HTTP FUNCTIONS
# ==========================================
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

def api_request(url, path, api_key, method="GET", data=None):
    full_url = f"{url.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
    
    req = urllib.request.Request(full_url, headers=headers, method=method)
    if data is not None:
        req.data = json.dumps(data).encode()
        
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return json.loads(body) if body else None
    except Exception as e:
        log.error(f"HTTP Request failed on {path}: {e}")
        return None

# ==========================================
# 📺 JELLYFIN & TELEGRAM INTEGRATION
# ==========================================
def refresh_jellyfin():
    if not CFG["JELLYFIN_URL"] or not CFG["JELLYFIN_KEY"]:
        return
    try:
        req = urllib.request.Request(
            f"{CFG['JELLYFIN_URL'].rstrip('/')}/Library/Refresh",
            headers={"X-Emby-Token": CFG["JELLYFIN_KEY"]},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        log.info("Jellyfin library scan triggered.")
    except Exception as e:
        log.warning(f"Failed to refresh Jellyfin library: {e}")

def send_telegram(msg):
    if not CFG["TELEGRAM_BOT_TOKEN"] or not CFG["TELEGRAM_CHAT_ID"]:
        log.info(f"Telegram not configured. Log: {msg}")
        return
    try:
        url = f"https://api.telegram.org/bot{CFG['TELEGRAM_BOT_TOKEN']}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": CFG["TELEGRAM_CHAT_ID"], "text": msg, "parse_mode": "Markdown"}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
    except Exception as e:
        log.error(f"Telegram notification failed: {e}")

# ==========================================
# 💾 TRANSMISSION CONTROLLER
# ==========================================
def get_transmission_sid():
    auth = base64.b64encode(f"{CFG['TRANSMISSION_USER']}:{CFG['TRANSMISSION_PASS']}".encode()).decode()
    req = urllib.request.Request(CFG["TRANSMISSION_URL"], data=json.dumps({"method": "session-get"}).encode(),
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return ""
    except urllib.error.HTTPError as e:
        return e.headers.get("X-Transmission-Session-Id", "")
    except Exception as e:
        log.error(f"Transmission connection error: {e}")
        return None

def trans_request(method, arguments=None):
    auth = base64.b64encode(f"{CFG['TRANSMISSION_USER']}:{CFG['TRANSMISSION_PASS']}".encode()).decode()
    sid = get_transmission_sid()
    if sid is None:
        return None
    
    payload = {"method": method}
    if arguments:
        payload["arguments"] = arguments
        
    req = urllib.request.Request(CFG["TRANSMISSION_URL"], data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "X-Transmission-Session-Id": sid
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"Transmission RPC {method} failed: {e}")
        return None

def trans_add(uri, download_dir):
    args = {"download-dir": download_dir}
    if uri.startswith("base64:"):
        args["metainfo"] = uri[7:]
    else:
        args["filename"] = uri
    return trans_request("torrent-add", args)

def trans_remove(tid):
    trans_request("torrent-remove", {"ids": [tid], "delete-local-data": False})

def trans_list():
    res = trans_request("torrent-get", {"fields": ["id", "name", "percentDone", "downloadDir"]})
    return res.get("arguments", {}).get("torrents", []) if res else []

def get_uri(dl_url):
    opener = urllib.request.build_opener(NoRedirect)
    try:
        resp = opener.open(dl_url, timeout=15)
        ct = resp.headers.get("Content-Type", "")
        if "torrent" in ct or "octet" in ct:
            return "base64:" + base64.b64encode(resp.read()).decode()
        return dl_url
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "")
        if loc.startswith("magnet:"):
            return loc
        try:
            body = e.read()
            if body and len(body) > 50:
                return "base64:" + base64.b64encode(body).decode()
        except:
            pass
        return None
    except Exception as e:
        log.error(f"Failed to fetch URI: {e}")
        return None

# ==========================================
# 📊 TEXT SCANNING & SCORING
# ==========================================
def clean_title(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())

def strip_year(t):
    return re.sub(r'\s*\(\d{4}\)\s*', ' ', t).strip()

def sanitize_query(t):
    t = t.replace("\u00b3", "3").replace("\u00b2", "2").replace("\u00b9", "1")
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r'[^\x00-\x7F]+', ' ', t).strip()
    return t

def parse_ep(title):
    m = re.search(r'(\d+)[×x](\d+)', title)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'S(\d+)E(\d+)', title, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None

def is_latino(t):
    tl = t.lower()
    return any(x in tl for x in ["latin", "latino", "lat.", " lat ", "latam"])

def is_castellano(t):
    tl = t.lower()
    return any(x in tl for x in ["spanish", "espa", "castellano", "esp.", " esp "])

def score_release(title, lang_tier):
    sc = 0
    t = title.lower()
    if lang_tier == 1:
        sc += 500
    elif lang_tier == 2:
        sc += 200
        
    if "1080p" in t:
        sc += 100
    elif "bluray" in t or "brrip" in t:
        sc += 90
    elif "720p" in t:
        sc += 50
    elif "hdtv" in t:
        sc += 30
    return sc

def prowlarr_search(query):
    params = urllib.parse.urlencode({"query": query})
    return api_request(CFG["PROWLARR_URL"], f"api/v1/search?{params}", CFG["PROWLARR_KEY"]) or []

# ==========================================
# 💾 STATE TRACKER
# ==========================================
def load_state(filepath):
    try:
        with open(filepath) as f:
            return json.load(f)
    except:
        return {}

def save_state(filepath, state):
    try:
        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log.error(f"Failed to save state file: {e}")

# ==========================================
# 🎬 MOVIES SEARCH & IMPORT BRIDGE
# ==========================================
def run_movies_bridge():
    log.info("Starting Movies Bridge (Radarr)...")
    grabbed = load_state(CFG["GRABBED_MOVIES_FILE"])
    
    # 1. Process Completed Downloads
    torrents = trans_list()
    imported = []
    for key, info in list(grabbed.items()):
        if info.get("imported"):
            continue
        for t in torrents:
            if t["downloadDir"] != CFG["DOWNLOAD_DIR_MOVIES"] or t["percentDone"] < 1.0:
                continue
            
            tc = clean_title(t["name"])
            rc = clean_title(info.get("release", ""))
            if tc != rc and tc not in rc and rc not in tc:
                continue
                
            title = info["title"]
            year = info.get("year", "")
            folder_name = f"{title} ({year})" if year else title
            dest = os.path.join(CFG["DESTINATION_MOVIES_DIR"], folder_name)
            os.makedirs(dest, exist_ok=True)
            
            src = os.path.join(CFG["TRANSMISSION_MOVIES_DIR_ON_HOST"], t["name"])
            if os.path.exists(src):
                log.info(f"Moving Movie: {t['name']} -> {folder_name}")
                try:
                    shutil.move(src, os.path.join(dest, t["name"]))
                    trans_remove(t["id"])
                    info["imported"] = True
                    info["imported_date"] = datetime.now().isoformat()
                    imported.append(f"🎥 *{title}* ({year})")
                except Exception as e:
                    log.error(f"Move failed: {e}")
            break
            
    if imported:
        api_request(CFG["RADARR_URL"], "command", CFG["RADARR_KEY"], "POST", {"name": "RescanMovie"})
        send_telegram("🎬 *Peliculas Importadas*:\n\n" + "\n".join(imported))
        refresh_jellyfin()
        
    # 2. Search for Missing Movies
    movies = api_request(CFG["RADARR_URL"], "movie", CFG["RADARR_KEY"]) or []
    missing = [m for m in movies if m.get("monitored") and not m.get("hasFile")]
    log.info(f"Missing Movies in Radarr: {len(missing)}")
    
    new_grabs = 0
    grab_msgs = []
    
    for movie in missing:
        movie_key = str(movie["id"])
        if movie_key in grabbed:
            continue
            
        es_title = movie["title"]
        en_title = movie.get("originalTitle", es_title)
        year = movie.get("year", 0)
        
        best = None
        best_score = -1
        best_lang = ""
        
        clean_es = clean_title(es_title)
        clean_en = clean_title(en_title)
        search_es = sanitize_query(es_title)
        
        # Pass 1: Search Spanish Title
        if search_es.strip():
            log.info(f"[Radarr ES Search] Query: '{search_es}'")
            results = prowlarr_search(search_es)
            
            for r in results:
                rt = r.get("title", "")
                rc = clean_title(rt)
                if clean_es not in rc and clean_en not in rc:
                    continue
                if not r.get("downloadUrl"):
                    continue
                if is_latino(rt):
                    continue
                    
                sc = score_release(rt, 1) if is_castellano(rt) else score_release(rt, 2)
                if sc > best_score:
                    best = r
                    best_score = sc
                    best_lang = "🇪🇸 Castellano"
            time.sleep(1)
            
        # Pass 2: English Fallback
        if not best:
            search_en = sanitize_query(en_title)
            if search_en.strip() and search_en != search_es:
                log.info(f"[Radarr EN Fallback] Query: '{search_en}'")
                results = prowlarr_search(search_en)
                
                for r in results:
                    rt = r.get("title", "")
                    rc = clean_title(rt)
                    if clean_en not in rc:
                        continue
                    if not r.get("downloadUrl"):
                        continue
                    if is_latino(rt):
                        continue
                        
                    lang_tier = 1 if is_castellano(rt) else 2
                    sc = score_release(rt, lang_tier)
                    
                    if sc > best_score:
                        best = r
                        best_score = sc
                        best_lang = "🇪🇸 Castellano" if lang_tier == 1 else "🇬🇧 English"
                time.sleep(1)
                
        if best:
            size_mb = best.get("size", 0) // 1024 // 1024
            log.info(f"Grabbed best movie release: {best['title'][:70]} ({size_mb}MB) - Lang: {best_lang}")
            uri = get_uri(best["downloadUrl"])
            if uri:
                res = trans_add(uri, CFG["DOWNLOAD_DIR_MOVIES"])
                if res and res.get("result") == "success":
                    added = res.get("arguments", {})
                    ti = added.get("torrent-added") or added.get("torrent-duplicate")
                    name = ti.get("name", "?") if ti else "?"
                    grabbed[movie_key] = {
                        "title": es_title,
                        "year": year,
                        "release": best["title"],
                        "torrent_name": name,
                        "date": datetime.now().isoformat(),
                        "size_mb": size_mb,
                        "language": best_lang,
                        "imported": False
                    }
                    new_grabs += 1
                    grab_msgs.append(f"🎬 {best_lang} *{es_title}* ({year})\n_{best['title'][:55]}_ ({size_mb}MB)")
            time.sleep(1)
            
    save_state(CFG["GRABBED_MOVIES_FILE"], grabbed)
    if grab_msgs:
        send_telegram(f"🎬 *Radarr* - {new_grabs} nueva{'s' if new_grabs>1 else ''} enviada{'s' if new_grabs>1 else ''} a descargar:\n\n" + "\n\n".join(grab_msgs))

# ==========================================
# 📺 SERIES SEARCH & IMPORT BRIDGE
# ==========================================
def run_series_bridge():
    log.info("Starting Series Bridge (Sonarr)...")
    grabbed = load_state(CFG["GRABBED_TV_FILE"])
    
    # 1. Process Completed TV Downloads
    torrents = trans_list()
    imported = []
    for key, info in list(grabbed.items()):
        if info.get("imported"):
            continue
        for t in torrents:
            if t["downloadDir"] != CFG["DOWNLOAD_DIR_TV"] or t["percentDone"] < 1.0:
                continue
                
            tc = clean_title(t["name"])
            rc = clean_title(info.get("release", ""))
            if tc != rc and tc not in rc and rc not in tc:
                continue
                
            series = info.get("series", "Unknown")
            season = info.get("season", 1)
            season_folder = f"Season {season:02d}"
            dest = os.path.join(CFG["DESTINATION_TV_DIR"], series, season_folder)
            os.makedirs(dest, exist_ok=True)
            
            src = os.path.join(CFG["TRANSMISSION_TV_DIR_ON_HOST"], t["name"])
            if os.path.exists(src):
                log.info(f"Moving Series: {t['name']} -> {series}/{season_folder}")
                try:
                    shutil.move(src, os.path.join(dest, t["name"]))
                    trans_remove(t["id"])
                    info["imported"] = True
                    info["imported_date"] = datetime.now().isoformat()
                    imported.append(f"📺 *{series}* {info.get('episode', '')}")
                except Exception as e:
                    log.error(f"Move failed: {e}")
            break
            
    if imported:
        api_request(CFG["SONARR_URL"], "command", CFG["SONARR_KEY"], "POST", {"name": "RescanSeries"})
        send_telegram("📺 *Series Importadas*:\n\n" + "\n".join(imported))
        refresh_jellyfin()
        
    # 2. Search for Missing TV Episodes
    all_series = api_request(CFG["SONARR_URL"], "series", CFG["SONARR_KEY"]) or []
    series_by_id = {s["id"]: s for s in all_series}
    
    missing = api_request(CFG["SONARR_URL"], "wanted/missing?pageSize=200", CFG["SONARR_KEY"])
    if not missing:
        save_state(CFG["GRABBED_TV_FILE"], grabbed)
        return
        
    smap = {}
    for ep in missing.get("records", []):
        sid = ep["seriesId"]
        if sid not in smap:
            s = series_by_id.get(sid, {})
            # Determine original title slug to help find the title
            smap[sid] = {
                "title": s.get("title", "Unknown"),
                "en_title": s.get("originalLanguage", {}).get("name", "") if s.get("title") != s.get("titleSlug", "").replace("-", " ") else s.get("title", ""),
                "episodes": []
            }
        smap[sid]["episodes"].append({"season": ep["seasonNumber"], "episode": ep["episodeNumber"]})
        
    log.info(f"TV Shows with missing episodes: {len(smap)}")
    new_grabs = 0
    grab_msgs = []
    
    for sid, info in smap.items():
        title = info["title"]
        episodes = info["episodes"]
        log.info(f"Checking series: '{title}' ({len(episodes)} missing eps)")
        
        search_q = strip_year(title)
        results = prowlarr_search(search_q)
        ct = clean_title(search_q)
        
        for ep in episodes:
            ek = f"{sid}_S{ep['season']:02d}E{ep['episode']:02d}"
            if ek in grabbed:
                continue
                
            best = None
            best_sc = -1
            best_lang = ""
            
            # Find matching release for this episode
            for r in results:
                rt = r.get("title", "")
                rc = clean_title(rt)
                if ct not in rc:
                    continue
                rs, re_ = parse_ep(rt)
                if rs != ep["season"] or re_ != ep["episode"]:
                    continue
                if not r.get("downloadUrl"):
                    continue
                if is_latino(rt):
                    continue
                    
                lang_tier = 1 if is_castellano(rt) else 2
                sc = score_release(rt, lang_tier)
                if sc > best_sc:
                    best = r
                    best_sc = sc
                    best_lang = "🇪🇸" if lang_tier == 1 else "🇬🇧"
            
            if best:
                size_mb = best.get("size", 0) // 1024 // 1024
                log.info(f"  Grabbed S{ep['season']:02d}E{ep['episode']:02d} - release: {best['title'][:60]} ({size_mb}MB)")
                uri = get_uri(best["downloadUrl"])
                if uri:
                    res = trans_add(uri, CFG["DOWNLOAD_DIR_TV"])
                    if res and res.get("result") == "success":
                        added = res.get("arguments", {})
                        ti = added.get("torrent-added") or added.get("torrent-duplicate")
                        name = ti.get("name", "?") if ti else "?"
                        grabbed[ek] = {
                            "series": title,
                            "season": ep["season"],
                            "episode": f"S{ep['season']:02d}E{ep['episode']:02d}",
                            "release": best["title"],
                            "torrent_name": name,
                            "date": datetime.now().isoformat(),
                            "size_mb": size_mb,
                            "language": best_lang,
                            "imported": False
                        }
                        new_grabs += 1
                        grab_msgs.append(f"📺 {best_lang} *{title}* S{ep['season']:02d}E{ep['episode']:02d} ({size_mb}MB)")
                time.sleep(1)
        time.sleep(2)
        
    save_state(CFG["GRABBED_TV_FILE"], grabbed)
    if grab_msgs:
        send_telegram(f"📺 *Sonarr* - {new_grabs} nuevo{'s' if new_grabs>1 else ''} episodio{'s' if new_grabs>1 else ''} enviado{'s' if new_grabs>1 else ''} a descargar:\n\n" + "\n\n".join(grab_msgs[:10]))

# ==========================================
# 🚀 MAIN RUNNER
# ==========================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
        
    cmd = sys.argv[1].lower()
    
    if cmd == "movies":
        run_movies_bridge()
    elif cmd == "series":
        run_series_bridge()
    elif cmd == "all":
        run_movies_bridge()
        run_series_bridge()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
