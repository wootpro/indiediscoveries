"""Filter out unwanted tracks."""
import logging
import re
from collections import Counter
from datetime import date

from config import DEALBREAKER_GENRES, MAX_RELEASE_AGE_YEARS
from storage.database import get_recently_played_keys
from storage.models import ScoredTrack

logger = logging.getLogger("scoring.filters")

MAX_TRACKS_PER_ARTIST = 3

REMASTER_PATTERNS = re.compile(
    r"remaster|reissue|deluxe|anniversary|bonus track|expanded edition",
    re.IGNORECASE,
)


def filter_dealbreaker_genres(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Remove tracks whose genre matches a dealbreaker."""
    filtered = []
    removed = 0
    for track in tracks:
        genre_lower = track.genre.lower()
        is_dealbreaker = any(d in genre_lower for d in DEALBREAKER_GENRES)
        if is_dealbreaker:
            removed += 1
        else:
            filtered.append(track)
    if removed:
        logger.info(f"Removed {removed} tracks with dealbreaker genres")
    return filtered


def filter_already_played(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Remove tracks that appeared in playlists from the last 8 weeks."""
    recent_keys = get_recently_played_keys(weeks=8)
    if not recent_keys:
        return tracks

    filtered = []
    removed = 0
    for track in tracks:
        key = (track.artist_name_normalized, track.track_title_normalized)
        if key in recent_keys:
            removed += 1
        else:
            filtered.append(track)
    if removed:
        logger.info(f"Removed {removed} already-played tracks")
    return filtered


def filter_no_spotify(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Remove tracks without a Spotify URI."""
    filtered = [t for t in tracks if t.spotify_uri]
    removed = len(tracks) - len(filtered)
    if removed:
        logger.info(f"Removed {removed} tracks not found on Spotify")
    return filtered


def limit_per_artist(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Limit tracks per artist so one artist doesn't dominate the playlist.

    Assumes tracks are already sorted by score descending — keeps the
    highest-scoring tracks for each artist.
    """
    artist_counts = Counter()
    filtered = []
    removed = 0
    for track in tracks:
        artist_counts[track.artist_name_normalized] += 1
        if artist_counts[track.artist_name_normalized] <= MAX_TRACKS_PER_ARTIST:
            filtered.append(track)
        else:
            removed += 1
    if removed:
        logger.info(f"Removed {removed} tracks exceeding {MAX_TRACKS_PER_ARTIST}/artist limit")
    return filtered


def filter_remastered(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Remove remastered/reissued tracks — these are old songs, not new music."""
    filtered = []
    removed = 0
    for track in tracks:
        title = track.track_title
        album = track.album_name or ""
        if REMASTER_PATTERNS.search(title) or REMASTER_PATTERNS.search(album):
            removed += 1
        else:
            filtered.append(track)
    if removed:
        logger.info(f"Removed {removed} remastered/reissued tracks")
    return filtered


def apply_pre_spotify_filters(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Apply filters that don't need Spotify data (run before Spotify search)."""
    tracks = filter_dealbreaker_genres(tracks)
    tracks = filter_remastered(tracks)
    tracks = filter_already_played(tracks)
    tracks = limit_per_artist(tracks)
    return tracks


def filter_old_releases(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Remove tracks whose Spotify release date is older than MAX_RELEASE_AGE_YEARS.

    Tracks with no release date are kept — we can't confirm they're old.
    """
    cutoff = date.today().replace(year=date.today().year - MAX_RELEASE_AGE_YEARS)
    filtered = []
    removed = 0
    for track in tracks:
        if not track.release_date:
            filtered.append(track)
            continue
        try:
            rel = date.fromisoformat(track.release_date[:10])
            if rel >= cutoff:
                filtered.append(track)
            else:
                removed += 1
        except ValueError:
            filtered.append(track)
    if removed:
        logger.info(f"Removed {removed} tracks with release date older than {MAX_RELEASE_AGE_YEARS} years")
    return filtered


def apply_post_spotify_filters(tracks: list[ScoredTrack]) -> list[ScoredTrack]:
    """Apply filters that need Spotify data (run after Spotify search)."""
    tracks = filter_old_releases(tracks)
    return filter_no_spotify(tracks)
