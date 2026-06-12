#!/usr/bin/env python3
"""
Media Search CLI for Radarr/Sonarr
Provides commands to search, add, list, delete, and check queues.
Can be used manually or integrated into an AI Agent gateway (like OpenClaw).

Usage:
  python3 media_search_cli.py search-movie <term>
  python3 media_search_cli.py search-series <term>
  python3 media_search_cli.py add-movie <tmdbId> <title>
  python3 media_search_cli.py add-series <tvdbId> <title>
  python3 media_search_cli.py queue-movie
  python3 media_search_cli.py queue-series
  python3 media_search_cli.py list-movies
  python3 media_search_cli.py list-series
  python3 media_search_cli.py delete-movie <title>
  python3 media_search_cli.py delete-movie-id <id>
  python3 media_search_cli.py delete-series <title>
  python3 media_search_cli.py delete-series-id <id>
"""
import os
import sys
import json
import urllib.request
import urllib.parse

# ==========================================
# ⚙️ CONFIGURATION RESOLVER
# ==========================================
def load_config():
    config = {}
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception as e:
            pass

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
        "SONARR_URL": get_val("SONARR_URL", ["sonarr", "url"], "http://localhost:8989/api/v3"),
        "SONARR_KEY": get_val("SONARR_KEY", ["sonarr", "api_key"], ""),
        "JELLYFIN_URL": get_val("JELLYFIN_URL", ["jellyfin", "url"], "http://localhost:8096"),
        "JELLYFIN_KEY": get_val("JELLYFIN_KEY", ["jellyfin", "api_key"], ""),
    }

CFG = load_config()

# ==========================================
# 🛠️ HTTP REQUEST HELPER
# ==========================================
def api(url, key, path, method="GET", data=None):
    full_url = f"{url.rstrip('/')}/{path.lstrip('/')}"
    req = urllib.request.Request(
        full_url,
        headers={"X-Api-Key": key, "Content-Type": "application/json"},
        method=method,
    )
    if data is not None:
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404 and method == "DELETE":
            return None  # Already deleted
        print(f"HTTP ERROR: {e.code} on {path}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e} on {path}")
        sys.exit(1)

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
    except Exception:
        pass

# ==========================================
# 🚀 CLI COMMANDS
# ==========================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    args = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    if cmd == "search-movie":
        if not args:
            print("Usage: python3 media_search_cli.py search-movie <term>")
            sys.exit(1)
        results = api(CFG["RADARR_URL"], CFG["RADARR_KEY"], f"movie/lookup?term={urllib.parse.quote(args)}") or []
        for m in results[:5]:
            overview = (m.get("overview") or "Sin sinopsis")[:120]
            print(f"- {m['title']} ({m.get('year', '?')}) tmdbId={m.get('tmdbId', '?')}")
            print(f"  {overview}...")
        if not results:
            print("No se encontraron resultados.")

    elif cmd == "search-series":
        if not args:
            print("Usage: python3 media_search_cli.py search-series <term>")
            sys.exit(1)
        results = api(CFG["SONARR_URL"], CFG["SONARR_KEY"], f"series/lookup?term={urllib.parse.quote(args)}") or []
        for s in results[:5]:
            overview = (s.get("overview") or "Sin sinopsis")[:120]
            print(f"- {s['title']} ({s.get('year', '?')}) tvdbId={s.get('tvdbId', '?')}")
            print(f"  {overview}...")
        if not results:
            print("No se encontraron resultados.")

    elif cmd == "add-movie":
        if len(sys.argv) < 4:
            print("Usage: python3 media_search_cli.py add-movie <tmdbId> <title>")
            sys.exit(1)
        tmdb_id = int(sys.argv[2])
        title = " ".join(sys.argv[3:])
        result = api(CFG["RADARR_URL"], CFG["RADARR_KEY"], "movie", "POST", {
            "title": title,
            "tmdbId": tmdb_id,
            "qualityProfileId": 1,
            "rootFolderPath": "/movies",
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        })
        print(f"Pelicula añadida: {result.get('title', title)} - buscando descarga...")
        refresh_jellyfin()

    elif cmd == "add-series":
        if len(sys.argv) < 4:
            print("Usage: python3 media_search_cli.py add-series <tvdbId> <title>")
            sys.exit(1)
        tvdb_id = int(sys.argv[2])
        title = " ".join(sys.argv[3:])
        result = api(CFG["SONARR_URL"], CFG["SONARR_KEY"], "series", "POST", {
            "title": title,
            "tvdbId": tvdb_id,
            "qualityProfileId": 1,
            "rootFolderPath": "/tv",
            "seasonFolder": True,
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
        })
        print(f"Serie añadida: {result.get('title', title)} - buscando episodios...")
        refresh_jellyfin()

    elif cmd == "queue-movie":
        q = api(CFG["RADARR_URL"], CFG["RADARR_KEY"], "queue") or {}
        records = q.get("records", [])
        for r in records:
            left = r.get("sizeleft", "?")
            eta = r.get("timeleft", "?")
            print(f"- {r.get('title', '?')}: {r.get('status', '?')} (quedan {left} eta {eta})")
        if not records:
            print("Cola vacía.")

    elif cmd == "queue-series":
        q = api(CFG["SONARR_URL"], CFG["SONARR_KEY"], "queue") or {}
        records = q.get("records", [])
        for r in records:
            left = r.get("sizeleft", "?")
            eta = r.get("timeleft", "?")
            print(f"- {r.get('title', '?')}: {r.get('status', '?')} (quedan {left} eta {eta})")
        if not records:
            print("Cola vacía.")

    elif cmd == "list-movies":
        movies = api(CFG["RADARR_URL"], CFG["RADARR_KEY"], "movie") or []
        for m in movies:
            st = "descargada" if m.get("hasFile") else "pendiente"
            print(f"- {m.get('title', '?')} ({m.get('year', '?')}) [{st}]")
        print(f"\nTotal: {len(movies)} películas")

    elif cmd == "list-series":
        series = api(CFG["SONARR_URL"], CFG["SONARR_KEY"], "series") or []
        for s in series:
            stats = s.get("statistics", {})
            have = stats.get("episodeFileCount", 0)
            total = stats.get("episodeCount", 0)
            print(f"- {s.get('title', '?')} ({s.get('year', '?')}) id={s.get('id', '?')} [{have}/{total} eps]")
        print(f"\nTotal: {len(series)} series")

    elif cmd == "delete-movie":
        if not args:
            print("Usage: python3 media_search_cli.py delete-movie <title>")
            sys.exit(1)
        term = args.lower()
        movies = api(CFG["RADARR_URL"], CFG["RADARR_KEY"], "movie") or []
        found = [m for m in movies if term in m.get("title", "").lower()]
        if not found:
            print("No se encontró ninguna película con ese nombre.")
        elif len(found) > 1:
            print("Varias películas coinciden:")
            for m in found:
                print(f"- {m.get('title', '?')} ({m.get('year', '?')}) id={m.get('id', '?')}")
            print("Usa: delete-movie-id <id> para borrar una específica.")
        else:
            m = found[0]
            api(CFG["RADARR_URL"], CFG["RADARR_KEY"], f"movie/{m['id']}?deleteFiles=true", "DELETE")
            print(f"Película eliminada: {m.get('title', '?')} ({m.get('year', '?')})")
            refresh_jellyfin()

    elif cmd == "delete-movie-id":
        if not args:
            print("Usage: python3 media_search_cli.py delete-movie-id <id>")
            sys.exit(1)
        movie_id = int(args)
        api(CFG["RADARR_URL"], CFG["RADARR_KEY"], f"movie/{movie_id}?deleteFiles=true", "DELETE")
        print(f"Película con id={movie_id} eliminada.")
        refresh_jellyfin()

    elif cmd == "delete-series":
        if not args:
            print("Usage: python3 media_search_cli.py delete-series <title>")
            sys.exit(1)
        term = args.lower()
        series = api(CFG["SONARR_URL"], CFG["SONARR_KEY"], "series") or []
        found = [s for s in series if term in s.get("title", "").lower()]
        if not found:
            print("No se encontró ninguna serie con ese nombre.")
        elif len(found) > 1:
            print("Varias series coinciden:")
            for s in found:
                print(f"- {s.get('title', '?')} ({s.get('year', '?')}) id={s.get('id', '?')}")
            print("Usa: delete-series-id <id> para borrar una específica.")
        else:
            s = found[0]
            api(CFG["SONARR_URL"], CFG["SONARR_KEY"], f"series/{s['id']}?deleteFiles=true", "DELETE")
            print(f"Serie eliminada: {s.get('title', '?')} ({s.get('year', '?')})")
            refresh_jellyfin()

    elif cmd == "delete-series-id":
        if not args:
            print("Usage: python3 media_search_cli.py delete-series-id <id>")
            sys.exit(1)
        series_id = int(args)
        api(CFG["SONARR_URL"], CFG["SONARR_KEY"], f"series/{series_id}?deleteFiles=true", "DELETE")
        print(f"Serie con id={series_id} eliminada.")
        refresh_jellyfin()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
