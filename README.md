# IndieMusic Discovery

Automatically scrapes 10+ music blogs, radio stations, and community sources every week, scores tracks against your taste, and drops the best discoveries into a fresh Spotify playlist.

**The Spotify playlist is the only output.** No website, no app — just open Spotify on Wednesday morning and there's a new playlist waiting.

---

## How it works

1. **Scrapes** sources like KEXP, NTS, BBC 6 Music, Pitchfork, Stereogum, Hype Machine, Reddit, and a dozen blogs
2. **Deduplicates** — a track mentioned by 5 sources is stronger than one mentioned by 1
3. **Enriches** — looks up genre via MusicBrainz
4. **Scores** each track on source trust, mention count, genre match, and recency
5. **Filters** out dealbreaker genres and tracks already in recent playlists
6. **Creates** a Spotify playlist with the top 40–60 tracks

---

## Prerequisites

- Python 3.10 or later
- A [Spotify account](https://spotify.com) (free or premium)
- A [Spotify Developer app](https://developer.spotify.com/dashboard) (free, takes 2 minutes)

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/yourusername/indiemusic.git
cd indiemusic
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Create a Spotify Developer app

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Click **Create App**
3. Fill in any name and description
4. Set **Redirect URI** to `http://127.0.0.1:8888/callback`
5. Copy your **Client ID** and **Client Secret**

### 3. Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

### 4. Configure your preferences

```bash
cp user_config.yaml.example user_config.yaml
```

Edit `user_config.yaml` to set your preferred genres, dealbreaker genres, which scrapers to enable, and playlist size. The file is heavily commented — read through it once.

Key things to customize:
- `preferred_genres` — genres that score higher
- `dealbreaker_genres` — genres that are excluded entirely
- `enabled_scrapers` — comment out sources you don't want
- `playlist.max_tracks` — how many tracks per playlist (default: 60)

### 5. First run

```bash
python main.py
```

The first run will open a browser window to authorize Spotify access. After that the token is cached and subsequent runs are fully automated.

---

## Running it

```bash
python main.py
```

After the run, `last_run_report.html` opens automatically showing:
- How many tracks each source contributed
- The full scored playlist with genres and sources
- Any errors or rate limit warnings

---

## Scheduling

### Windows (Task Scheduler)

```batch
schtasks /create /tn "IndieMusic" /tr "C:\path\to\indiemusic\run_discovery.bat" /sc weekly /d WED /st 07:00
```

Or open Task Scheduler manually → Create Basic Task → Weekly → Wednesday → 7:00 AM → Start a Program → point to `run_discovery.bat`.

### macOS (launchd)

Create `~/Library/LaunchAgents/com.indiemusic.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.indiemusic</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/indiemusic/.venv/bin/python</string>
        <string>/path/to/indiemusic/main.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>3</integer>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>/path/to/indiemusic</string>
    <key>StandardOutPath</key>
    <string>/path/to/indiemusic/indie_music.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/indiemusic/indie_music.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.indiemusic.plist
```

### Linux (cron)

```bash
crontab -e
```

Add:
```
0 7 * * 3 cd /path/to/indiemusic && .venv/bin/python main.py >> indie_music.log 2>&1
```

---

## Taste profile (optional)

The scoring system includes a `taste_profile` component that boosts artists similar to your listening history. To use it:

1. Install [spotify-brain](https://github.com/mossein/spotify-brain)
2. Run `spotify-brain pull` and `spotify-brain fingerprint`
3. Copy the output JSON to `taste_profile.json` in this directory

Without `taste_profile.json`, the taste component defaults to neutral (0.5) and the other scoring signals take over. The system works fine without it.

---

## Available scrapers

| Scraper | Source | Type |
|---|---|---|
| `kexp` | KEXP Radio (Seattle) | Radio — JSON API |
| `nts` | NTS Radio | Radio — JSON API |
| `bbc_6music` | BBC 6 Music | Radio — JSON API |
| `pitchfork` | Pitchfork Best New Tracks | Editorial |
| `stereogum` | Stereogum | Editorial/Blog |
| `gorilla_vs_bear` | Gorilla vs Bear | Blog — RSS |
| `reddit_indieheads` | r/indieheads | Community |
| `hype_machine` | Hype Machine | Aggregator |
| `album_of_the_year` | Album of the Year | Aggregator |
| `blog_rss` | Configured blog RSS feeds | Blogs |

Blog RSS feeds are configured separately under `blog_rss_feeds` in `user_config.yaml`.

---

## Troubleshooting

**"user_config.yaml not found"**
Copy the example: `cp user_config.yaml.example user_config.yaml`

**Spotify 401 errors**
Delete `.spotify_cache` and re-run — it will prompt you to re-authorize.

**Playlist has fewer than 40 tracks**
Lower your `min_tracks` setting or add more scrapers. The most common cause is strict `dealbreaker_genres` cutting too many tracks.

**MusicBrainz lookups are slow**
This is normal on first run — MusicBrainz requires a 1.1s delay between requests. Results are cached permanently so subsequent runs for the same artists are instant.

**Spotify rate limit hit**
The pipeline handles this gracefully — it stops searching and proceeds with whatever tracks have already been found via cache. Re-running the next day will pick up the rest.

---

## Project structure

```
indiemusic/
├── main.py                  # Pipeline orchestrator
├── config.py                # Loads user_config.yaml + .env
├── user_config.yaml         # Your preferences (gitignored)
├── .env                     # Spotify credentials (gitignored)
├── taste_profile.json       # Optional taste fingerprint (gitignored)
├── scrapers/
│   ├── __init__.py          # Builds scraper list from config
│   ├── base.py              # BaseScraper ABC
│   ├── kexp.py / nts.py ... # Individual scrapers
│   └── blog_rss.py          # Generic RSS scraper
├── storage/
│   ├── models.py            # RawTrack, ScoredTrack dataclasses
│   └── database.py          # SQLite operations
├── enrichment/
│   ├── genre.py             # MusicBrainz genre lookup
│   ├── taste.py             # taste_profile.json scoring
│   └── feedback.py          # Learns from your playlist engagement
├── scoring/
│   ├── ranker.py            # Weighted scoring formula
│   └── filters.py           # Genre/remaster/already-played filters
├── spotify/
│   ├── auth.py              # Spotipy OAuth
│   ├── search.py            # Track search with cache
│   └── playlist.py          # Playlist creation
└── reporting/
    └── logger.py            # Run summary + HTML report
```
