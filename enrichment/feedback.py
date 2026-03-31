"""Collect listening feedback from previous playlists to improve future scoring."""
import logging

from spotify.auth import get_spotify
from storage.database import (
    get_unchecked_playlists, get_playlist_track_ids,
    insert_feedback, rebuild_artist_affinity, get_all_artist_affinities,
)

logger = logging.getLogger("enrichment.feedback")

# In-memory affinity cache — populated once at startup
_affinity_cache: dict = {}


def collect_feedback():
    """Check previous playlists for user engagement signals.

    For each unchecked playlist:
    - Check which tracks the user saved to their library (strong positive)
    - Check which tracks were removed from the playlist (moderate negative)
    Then rebuild the artist_affinity table from all accumulated feedback.
    """
    unchecked = get_unchecked_playlists()
    if not unchecked:
        logger.info("No unchecked playlists for feedback collection")
        load_affinity_cache()
        return

    sp = get_spotify()
    total_saved = 0
    total_removed = 0
    total_checked = 0

    for playlist in unchecked:
        playlist_id = playlist["id"]
        spotify_playlist_id = playlist["spotify_playlist_id"]
        logger.info(f"Collecting feedback for '{playlist['playlist_name']}'")

        tracks = get_playlist_track_ids(playlist_id)
        if not tracks:
            continue

        # Get track IDs that are still valid
        track_ids = [t["spotify_track_id"] for t in tracks if t["spotify_track_id"]]
        if not track_ids:
            continue

        # Check which tracks are saved in user's library (batch of 50)
        saved_set = set()
        for i in range(0, len(track_ids), 50):
            batch = track_ids[i:i + 50]
            try:
                results = sp.current_user_saved_tracks_contains(batch)
                for tid, is_saved in zip(batch, results):
                    if is_saved:
                        saved_set.add(tid)
            except Exception as e:
                logger.warning(f"Failed to check saved tracks: {e}")
                break

        # Check which tracks were removed from the Spotify playlist
        removed_set = set()
        try:
            current_uris = set()
            results = sp.playlist_items(spotify_playlist_id, fields="items.track.uri,next", limit=100)
            while results:
                for item in results.get("items", []):
                    track = item.get("track")
                    if track and track.get("uri"):
                        current_uris.add(track["uri"])
                results = sp.next(results) if results.get("next") else None

            # Tracks that were in our DB but not in the current playlist = removed
            for t in tracks:
                if t["spotify_uri"] and t["spotify_uri"] not in current_uris:
                    if t["spotify_track_id"]:
                        removed_set.add(t["spotify_track_id"])
        except Exception as e:
            # 403/404 means playlist was deleted — not a removal signal
            logger.warning(f"Could not check playlist contents: {e}")

        # Record feedback for each track
        for t in tracks:
            tid = t["spotify_track_id"]
            if not tid:
                continue
            was_saved = tid in saved_set
            was_removed = tid in removed_set
            insert_feedback(playlist_id, tid, t["artist_name_normalized"], was_saved, was_removed)
            total_checked += 1
            if was_saved:
                total_saved += 1
            if was_removed:
                total_removed += 1

    # Rebuild affinity scores from all feedback, then load into memory
    rebuild_artist_affinity()
    _affinity_cache.update(get_all_artist_affinities())

    logger.info(f"Feedback collected: {total_checked} tracks checked, "
                f"{total_saved} saved, {total_removed} removed")


def load_affinity_cache():
    """Load artist affinity scores into memory (call at startup if no feedback to collect)."""
    global _affinity_cache
    _affinity_cache = get_all_artist_affinities()


def get_feedback_score(artist_name_normalized: str) -> float:
    """Return feedback-based score for an artist (0-1, 0.5 = neutral/no data)."""
    return _affinity_cache.get(artist_name_normalized, 0.5)
