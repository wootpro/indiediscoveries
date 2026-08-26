"""Genre detection via MusicBrainz with SQLite caching."""
import logging
import re
import time

import musicbrainzngs

from config import MUSICBRAINZ_DELAY
from storage.database import get_cached_genre, cache_genre

logger = logging.getLogger("enrichment.genre")

musicbrainzngs.set_useragent("IndieMusicDiscovery", "1.0", "indie-music-discovery@local")
logging.getLogger("musicbrainzngs").setLevel(logging.WARNING)

GENRE_MAP = {
    "indie": "Indie",
    "alternative": "Indie",
    "rock": "Rock",
    "electronic": "Electronic",
    "experimental": "Experimental",
    "punk": "Rock",
    "post-punk": "Rock",
    "garage": "Rock",
    "shoegaze": "Indie",
    "noise": "Experimental",
    "synth": "Electronic",
    "new wave": "Rock",
    "blues": "Blues",
    "jazz": "Jazz",
    "hip hop": "Hip-Hop",
    "rap": "Hip-Hop",
    "r&b": "R&B",
    "soul": "Soul",
    "country": "Country",
    "folk": "Folk",
    "metal": "Metal",
    "pop": "Pop",
    "singer-songwriter": "Folk",
    "ambient": "Electronic",
    "techno": "Electronic",
    "house": "Electronic",
    "dream pop": "Indie",
    "trip hop": "Electronic",
    "downtempo": "Electronic",
    "lo-fi": "Indie",
    "psychedelic": "Rock",
}


def _map_tag_to_genre(tag: str) -> str:
    tag_lower = tag.lower()
    for keyword, genre in GENRE_MAP.items():
        if keyword in tag_lower:
            return genre
    return tag.title()


def lookup_genre(artist_name: str, artist_norm: str) -> str:
    """Return best-effort genre string for an artist."""
    cached = get_cached_genre(artist_norm)
    if cached is not None:
        return cached

    search_name = re.sub(r"^the\s+", "", artist_name.strip(), flags=re.IGNORECASE)

    try:
        time.sleep(MUSICBRAINZ_DELAY)
        result = musicbrainzngs.search_artists(artist=search_name, limit=1)
        if result.get("artist-list"):
            mbid = result["artist-list"][0]["id"]
            time.sleep(MUSICBRAINZ_DELAY)
            artist_data = musicbrainzngs.get_artist_by_id(mbid, includes=["tags"])
            tags = artist_data.get("artist", {}).get("tag-list", [])
            if tags:
                tags.sort(key=lambda t: int(t.get("count", 0)), reverse=True)
                genre = _map_tag_to_genre(tags[0]["name"])
                cache_genre(artist_norm, genre)
                return genre
    except Exception as e:
        logger.warning(f"MusicBrainz lookup failed for '{artist_name}': {e}")

    cache_genre(artist_norm, "Unknown")
    return "Unknown"
