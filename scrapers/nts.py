"""Scrape NTS Radio tracklists via their public API.

Step 1: Fetch /latest pages to get recent episode show_alias + episode_alias
Step 2: Hit /api/v2/shows/{show}/episodes/{episode}/tracklist for each
"""
import json
import logging
import re
from datetime import date

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.nts")

BASE_URL = "https://www.nts.live"
API_BASE = f"{BASE_URL}/api/v2"


class NTSScraper(BaseScraper):
    """Scrape NTS Radio tracklists from recent episodes."""

    def __init__(self):
        super().__init__("nts")

    def scrape(self) -> list[RawTrack]:
        episodes = self._get_recent_episodes()
        self.logger.info(f"Found {len(episodes)} recent NTS episodes")

        tracks = []
        seen = set()

        for show_alias, episode_alias in episodes:
            try:
                self._rate_limit(0.5)
                episode_tracks = self._get_tracklist(show_alias, episode_alias)
                for artist, title in episode_tracks:
                    key = (artist.lower(), title.lower())
                    if key not in seen:
                        seen.add(key)
                        tracks.append(RawTrack(
                            artist_name=artist,
                            track_title=title,
                            source_name="nts",
                            source_url=f"{BASE_URL}/shows/{show_alias}/episodes/{episode_alias}",
                            discovered_date=date.today(),
                        ))
            except Exception as e:
                self.logger.debug(f"NTS tracklist failed for {show_alias}/{episode_alias}: {e}")

        self.logger.info(f"Found {len(tracks)} unique tracks from NTS")
        return tracks

    def _get_recent_episodes(self) -> list[tuple[str, str]]:
        """Fetch recent episode identifiers from /latest pages."""
        episodes = []

        # Fetch 3 pages of latest (36 episodes)
        for offset in [0, 12, 24]:
            try:
                self._rate_limit(1.0)
                url = f"{BASE_URL}/latest?offset={offset}"
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()

                # Extract window._REACT_STATE_ JSON from HTML
                match = re.search(r'window\._REACT_STATE_\s*=\s*({.+?});\s*</script>', resp.text, re.DOTALL)
                if not match:
                    continue

                state = json.loads(match.group(1))

                # Navigate to recentlyAdded episodes
                recently = state.get("recentlyAdded", {})
                items = recently.get("episodes", [])

                for item in items:
                    show_alias = item.get("show_alias", "")
                    episode_alias = item.get("episode_alias", "")
                    if show_alias and episode_alias:
                        episodes.append((show_alias, episode_alias))

            except Exception as e:
                self.logger.warning(f"NTS /latest offset={offset} failed: {e}")

        return episodes

    def _get_tracklist(self, show_alias: str, episode_alias: str) -> list[tuple[str, str]]:
        """Fetch tracklist for a specific episode."""
        url = f"{API_BASE}/shows/{show_alias}/episodes/{episode_alias}/tracklist"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        tracks = []
        for item in data.get("results", []):
            artist = item.get("artist", "").strip()
            title = item.get("title", "").strip()
            if artist and title:
                tracks.append((artist, title))

        return tracks
