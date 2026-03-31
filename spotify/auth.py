"""Spotify OAuth authentication via Spotipy."""
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import (
    SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPE, PROJECT_ROOT,
)

logger = logging.getLogger("spotify.auth")

_sp_instance = None


def get_spotify() -> spotipy.Spotify:
    """Get an authenticated Spotify client (cached singleton)."""
    global _sp_instance
    if _sp_instance is not None:
        return _sp_instance

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")

    auth_manager = SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
        cache_path=str(PROJECT_ROOT / ".spotify_cache"),
    )

    _sp_instance = spotipy.Spotify(auth_manager=auth_manager)
    user = _sp_instance.current_user()
    logger.info(f"Authenticated as: {user['display_name']} ({user['id']})")
    return _sp_instance
