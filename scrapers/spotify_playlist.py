"""Scrape tracks from Spotify editorial/community playlists via API."""
import logging
from datetime import date

from config import SPOTIFY_PLAYLIST_SOURCES
from storage.models import RawTrack
from spotify.auth import get_spotify

logger = logging.getLogger("scraper.spotify_playlist")


class SpotifyPlaylistScraper:
    """Read tracks from a Spotify playlist."""

    def __init__(self, name: str, playlist_id: str):
        self.name = name
        self.playlist_id = playlist_id
        self.logger = logging.getLogger(f"scraper.{name}")

    def scrape(self) -> list[RawTrack]:
        sp = get_spotify()
        tracks = []

        try:
            results = sp.playlist_tracks(
                self.playlist_id,
                limit=100,
            )

            while results:
                for item in results.get("items", []):
                    track = item.get("track")
                    if not track or not track.get("name"):
                        continue

                    artist_names = ", ".join(a["name"] for a in track.get("artists", []))
                    if not artist_names:
                        continue

                    tracks.append(RawTrack(
                        artist_name=artist_names,
                        track_title=track["name"],
                        source_name=self.name,
                        album_name=track.get("album", {}).get("name"),
                        spotify_uri=track.get("uri"),
                        discovered_date=date.today(),
                    ))

                if results.get("next"):
                    results = sp.next(results)
                else:
                    break

        except Exception as e:
            self.logger.error(f"Failed to scrape playlist {self.name}: {e}")

        self.logger.info(f"Found {len(tracks)} tracks from {self.name}")
        return tracks


def get_spotify_playlist_scrapers() -> list[SpotifyPlaylistScraper]:
    """Create scraper instances for all configured Spotify playlists."""
    return [
        SpotifyPlaylistScraper(name, pid)
        for name, pid in SPOTIFY_PLAYLIST_SOURCES.items()
    ]
