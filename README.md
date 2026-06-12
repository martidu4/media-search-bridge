# Prowlarr/Radarr/Sonarr Spanish Search & Import Bridge 🎬📺

A clean, configurable, lightweight Python script designed to automatically search and bridge media content via **Prowlarr** into **Radarr/Sonarr**, prioritizing **Castellano (Spanish)** releases while excluding **Latino** audio, and falling back to **English** if necessary. It also moves completed downloads from **Transmission** to final library paths, notifies via **Telegram**, and refreshes **Jellyfin**.

---

## Features / Características

- 🔍 **Automated Prowlarr Search**: Searches Prowlarr indexers for missing movies in Radarr and missing episodes in Sonarr.
- 🇪🇸 **Spanish-First Scoring Engine**:
  1. **Tier 1**: Castellano (Spanish) audio.
  2. **Tier 2**: English/Original version (with optional subtitles).
  3. **Exclusion**: Completely ignores and filters out Latino audio.
- 💾 **Transmission Integration**: Auto-adds torrents/magnets using custom download paths for movies and series, and monitors progress.
- 🚚 **Automatic Importer**: Moves completed downloads into Jellyfin-ready directories (e.g., `/mnt/datos/complete/Pelis` and `/mnt/datos/complete/Series`).
- 🤖 **Telegram Notifications**: Sends instant alerts to a Telegram chat with download details (name, size, language badge).
- 🍿 **Jellyfin Refresh**: Triggers library rescans automatically after importing.

---

## Installation / Instalación

### 1. Clone the files / Clonar archivos
Copy `bridge.py` and the configuration template to your server or Raspberry Pi.

### 2. Configuration / Configuración
You can configure the bridge either by renaming `.env.example` to `.env` and setting the variables, OR by copying `config.json.example` to `config.json` and modifying it.

#### Option A: Using `config.json` (Recommended for multi-path setups)
```json
{
  "radarr": {
    "url": "http://localhost:7878/api/v3",
    "api_key": "YOUR_RADARR_API_KEY",
    "root_folder_path": "/movies",
    "quality_profile_id": 1
  },
  "sonarr": {
    "url": "http://localhost:8989/api/v3",
    "api_key": "YOUR_SONARR_API_KEY",
    "root_folder_path": "/tv",
    "quality_profile_id": 1
  },
  "prowlarr": {
    "url": "http://localhost:9696",
    "api_key": "YOUR_PROWLARR_API_KEY"
  },
  "transmission": {
    "url": "http://localhost:9091/transmission/rpc",
    "username": "admin",
    "password": "your_password",
    "download_dir_movies": "/downloads/radarr",
    "download_dir_tv": "/downloads/tv-sonarr"
  },
  "jellyfin": {
    "url": "http://localhost:8096",
    "api_key": "YOUR_JELLYFIN_API_KEY"
  },
  "telegram": {
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "chat_id": "YOUR_TELEGRAM_CHAT_ID"
  },
  "paths": {
    "grabbed_movies_file": "movies_grabbed.json",
    "grabbed_tv_file": "tv_grabbed.json",
    "destination_movies_dir": "/mnt/datos/complete/Pelis",
    "destination_tv_dir": "/mnt/datos/complete/Series",
    "transmission_movies_dir_on_host": "/mnt/datos/complete/radarr",
    "transmission_tv_dir_on_host": "/mnt/datos/complete/tv-sonarr"
  }
}
```

#### Option B: Using Environment Variables (`.env`)
```bash
RADARR_URL=http://localhost:7878/api/v3
RADARR_KEY=YOUR_RADARR_API_KEY
SONARR_URL=http://localhost:8989/api/v3
SONARR_KEY=YOUR_SONARR_API_KEY
PROWLARR_URL=http://localhost:9696
PROWLARR_KEY=YOUR_PROWLARR_API_KEY
TRANSMISSION_URL=http://localhost:9091/transmission/rpc
TRANSMISSION_USER=admin
TRANSMISSION_PASS=your_password
TRANSMISSION_DOWNLOAD_DIR_MOVIES=/downloads/radarr
TRANSMISSION_DOWNLOAD_DIR_TV=/downloads/tv-sonarr
JELLYFIN_URL=http://localhost:8096
JELLYFIN_KEY=YOUR_JELLYFIN_API_KEY
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID
DESTINATION_MOVIES_DIR=/mnt/datos/complete/Pelis
DESTINATION_TV_DIR=/mnt/datos/complete/Series
TRANSMISSION_MOVIES_DIR_ON_HOST=/mnt/datos/complete/radarr
TRANSMISSION_TV_DIR_ON_HOST=/mnt/datos/complete/tv-sonarr
GRABBED_MOVIES_FILE=movies_grabbed.json
GRABBED_TV_FILE=tv_grabbed.json
```

---

## Usage / Uso

Make the script executable:
```bash
chmod +x bridge.py
```

Run movies search and import:
```bash
python3 bridge.py movies
```

Run series search and import:
```bash
python3 bridge.py series
```

Run both sequentially:
```bash
python3 bridge.py all
```

---

## Automation (Cron setup) / Automatización

Add a cron job to run the script automatically (e.g., daily at 9:10 AM):

```bash
# Open crontab
crontab -e

# Run both search bridges daily at 09:10
10 9 * * * /usr/bin/python3 /path/to/media-search-bridge/bridge.py all >> /path/to/media-search-bridge/bridge.log 2>&1
```

---

## License / Licencia

MIT License. Feel free to modify and share!
