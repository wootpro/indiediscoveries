"""Create and manage Spotify playlists."""
import logging
from datetime import date

from config import PLAYLIST_NAME_FORMAT, MIN_TRACKS, MAX_TRACKS
from spotify.auth import get_spotify
from storage.database import record_playlist, record_playlist_tracks
from storage.models import ScoredTrack

logger = logging.getLogger("spotify.playlist")


def create_weekly_playlist(tracks: list[ScoredTrack]) -> str | None:
    """Create a new Spotify playlist with the given tracks.

    Returns the playlist URL or None on failure.
    """
    if not tracks:
        logger.warning("No tracks to add to playlist")
        return None

    sp = get_spotify()
    user_id = sp.current_user()["id"]

    playlist_name = PLAYLIST_NAME_FORMAT.format(
        date=date.today().strftime("%b %d")
    )

    try:
        playlist = sp._post("me/playlists", payload={
            "name": playlist_name,
            "public": True,
            "description": f"Auto-curated indie music discoveries for the week of {date.today().strftime('%B %d, %Y')}",
        })
    except Exception as e:
        logger.error(f"Failed to create playlist: {e}")
        return None
    playlist_id = playlist["id"]
    playlist_url = playlist["external_urls"]["spotify"]

    # Add tracks in batches of 100 (Spotify API limit)
    uris = [t.spotify_uri for t in tracks if t.spotify_uri]
    for i in range(0, len(uris), 100):
        batch = uris[i:i + 100]
        sp.playlist_add_items(playlist_id, batch)

    logger.info(f"Created playlist '{playlist_name}' with {len(uris)} tracks: {playlist_url}")

    # Record in database
    db_playlist_id = record_playlist(playlist_name, playlist_id, len(uris))
    record_playlist_tracks(db_playlist_id, [t for t in tracks if t.spotify_uri])

    return playlist_url
