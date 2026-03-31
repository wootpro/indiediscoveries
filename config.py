"""Central configuration for IndieMusic Discovery.

Infrastructure settings live here.
User preferences (genres, weights, scrapers) live in user_config.yaml.
Secrets (Spotify credentials) live in .env.
"""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "storage" / "indie_music.db"
LOG_FILE = PROJECT_ROOT / "indie_music.log"
TASTE_PROFILE_PATH = PROJECT_ROOT / "taste_profile.json"

# --- Load user_config.yaml ---
_user_config_path = PROJECT_ROOT / "user_config.yaml"
if not _user_config_path.exists():
    raise FileNotFoundError(
        "user_config.yaml not found. Copy user_config.yaml.example to user_config.yaml and edit it."
    )
with open(_user_config_path) as _f:
    _cfg = yaml.safe_load(_f) or {}

# --- Spotify credentials (from .env) ---
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
SPOTIFY_SCOPE = "playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative user-library-read"

# --- Playlist settings ---
_playlist = _cfg.get("playlist", {})
PLAYLIST_NAME_FORMAT = _playlist.get("name_format", "Music Discoveries - {date}")
MIN_TRACKS = _playlist.get("min_tracks", 40)
MAX_TRACKS = _playlist.get("max_tracks", 60)
MAX_RELEASE_AGE_YEARS = _playlist.get("max_release_age_years", 3)

# --- Scraping parameters (not user-facing) ---
REQUEST_DELAY_SECONDS = 2.0
MUSICBRAINZ_DELAY = 1.1
LOOKBACK_DAYS = 7
USER_AGENT = "IndieMusicDiscovery/1.0 (github.com/yourusername/indiemusic)"

# --- Enabled scrapers ---
ENABLED_SCRAPERS = _cfg.get("enabled_scrapers", [
    "kexp", "nts", "bbc_6music", "pitchfork", "stereogum",
    "gorilla_vs_bear", "reddit_indieheads", "hype_machine",
    "album_of_the_year", "blog_rss",
])

# --- Blog RSS feeds ---
BLOG_RSS_FEEDS = _cfg.get("blog_rss_feeds", [])

# --- Source weights ---
_default_weights = {
    "kexp": 3.0, "nts": 3.0, "bbc_6music": 3.0, "pitchfork": 3.0,
    "stereogum": 2.5, "gorilla_vs_bear": 2.5,
    "aquarium_drunkard": 2.0, "line_of_best_fit": 2.0, "brooklyn_vegan": 2.0,
    "obscure_sound": 1.5, "earmilk": 1.5, "post_trash": 1.5,
    "blackwater_collective": 1.5, "hype_machine": 1.5,
    "album_of_the_year": 1.5, "reddit_indieheads": 1.5,
}
SOURCE_WEIGHTS = {**_default_weights, **_cfg.get("source_weights", {})}

# --- Preferred genres ---
PREFERRED_GENRES = _cfg.get("preferred_genres", [
    "rock", "indie", "electronic", "experimental", "alternative",
    "post-punk", "shoegaze", "synth", "garage", "punk", "noise",
    "hip hop", "r&b", "trip hop", "downtempo", "dream pop",
    "jazz", "funk", "soul", "lo-fi", "psychedelic", "ambient",
])

# --- Dealbreaker genres ---
DEALBREAKER_GENRES = _cfg.get("dealbreaker_genres", [
    "country", "metal", "hardcore", "metalcore", "death metal",
    "black metal", "thrash metal", "grindcore", "mainstream pop",
])

# --- Scoring weights ---
_default_scoring = {
    "source_weight": 0.25,
    "source_count": 0.20,
    "genre_match": 0.20,
    "taste_profile": 0.05,
    "recency": 0.05,
    "release_recency": 0.20,
    "feedback": 0.05,
}
SCORING_WEIGHTS = {**_default_scoring, **_cfg.get("scoring_weights", {})}
