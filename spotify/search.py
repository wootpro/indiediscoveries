"""Search Spotify for tracks by artist + title, or albums by artist + album.

Handles rate limiting gracefully — raises RateLimitError so callers can
stop searching and proceed with whatever tracks have URIs from cache.
"""
import logging
import time

from spotipy.exceptions import SpotifyException

from storage.database import get_cached_spotify, cache_spotify, normalize_artist, normalize_track
from spotify.auth import get_spotify

logger = logging.getLogger("spotify.search")


class RateLimitError(Exception):
    """Raised when Spotify rate limit is hit so callers can bail out."""
    def __init__(self, retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(f"Spotify rate limit hit (retry after {retry_after}s)")


def _check_rate_limit(e: Exception):
    """If e is a Spotify 429, raise RateLimitError. Otherwise re-raise."""
    if isinstance(e, SpotifyException) and e.http_status == 429:
        retry_after = int(e.headers.get("Retry-After", 0)) if hasattr(e, "headers") else 0
        raise RateLimitError(retry_after)
    # Also catch the "rate/request limit" message from spotipy
    if "rate" in str(e).lower() and "limit" in str(e).lower():
        raise RateLimitError()


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def search_track(artist_name: str, track_title: str) -> dict | None:
    """Search Spotify for a track. Returns {spotify_uri, spotify_track_id} or None.

    Raises RateLimitError if Spotify rate limit is hit.
    """
    artist_norm = normalize_artist(artist_name)
    track_norm = normalize_track(track_title)

    cached = get_cached_spotify(artist_norm, track_norm)
    if cached is not None:
        if cached["spotify_uri"]:
            return cached
        return None

    sp = get_spotify()
    query = f"artist:{artist_name} track:{track_title}"

    try:
        time.sleep(0.3)
        results = sp.search(q=query, type="track", limit=5)
        items = results.get("tracks", {}).get("items", [])

        for item in items:
            item_artists = " ".join(a["name"] for a in item["artists"])
            item_title = item["name"]

            artist_sim = _similarity(artist_norm, normalize_artist(item_artists))
            title_sim = _similarity(track_norm, normalize_track(item_title))

            if artist_sim >= 0.3 and title_sim >= 0.3:
                release_date = item.get("album", {}).get("release_date")
                result = {
                    "spotify_uri": item["uri"],
                    "spotify_track_id": item["id"],
                    "release_date": release_date,
                }
                cache_spotify(artist_norm, track_norm, item["uri"], item["id"], release_date)
                return result

        # No good match
        cache_spotify(artist_norm, track_norm, None, None)
        return None

    except Exception as e:
        _check_rate_limit(e)
        logger.warning(f"Spotify search failed for '{artist_name} - {track_title}': {e}")
        return None


def search_album_tracks(artist_name: str, album_name: str, max_tracks: int = 3) -> list[dict]:
    """Search Spotify for an album and return its top tracks.

    Returns list of {artist_name, track_title, spotify_uri, spotify_track_id}.
    Raises RateLimitError if Spotify rate limit is hit.
    """
    sp = get_spotify()
    artist_norm = normalize_artist(artist_name)

    try:
        time.sleep(0.3)
        query = f"artist:{artist_name} album:{album_name}"
        results = sp.search(q=query, type="album", limit=3)
        albums = results.get("albums", {}).get("items", [])

        for album in albums:
            album_artists = " ".join(a["name"] for a in album["artists"])
            artist_sim = _similarity(artist_norm, normalize_artist(album_artists))

            if artist_sim < 0.3:
                continue

            release_date = album.get("release_date")

            # Get album tracks
            time.sleep(0.3)
            album_tracks = sp.album_tracks(album["id"], limit=max_tracks)
            track_results = []

            for track in album_tracks.get("items", []):
                track_artist = ", ".join(a["name"] for a in track["artists"])
                track_title = track["name"]

                result = {
                    "artist_name": track_artist,
                    "track_title": track_title,
                    "spotify_uri": track["uri"],
                    "spotify_track_id": track["id"],
                    "album_name": album_name,
                    "release_date": release_date,
                }
                # Cache each track
                cache_spotify(
                    normalize_artist(track_artist),
                    normalize_track(track_title),
                    track["uri"],
                    track["id"],
                    release_date,
                )
                track_results.append(result)

            if track_results:
                return track_results

        return []

    except Exception as e:
        _check_rate_limit(e)
        logger.warning(f"Spotify album search failed for '{artist_name} - {album_name}': {e}")
        return []
