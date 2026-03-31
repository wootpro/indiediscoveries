"""Scrape Hype Machine popular tracks via their public JSON API."""
import logging
from datetime import date

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.hype_machine")

API_BASE = "https://api.hypem.com/v2/popular"


class HypeMachineScraper(BaseScraper):
    """Scrape trending tracks from Hype Machine's API."""

    def __init__(self):
        super().__init__("hype_machine")

    def scrape(self) -> list[RawTrack]:
        tracks = []
        seen = set()

        # Pull from multiple time windows for broader coverage
        modes = ["now", "lastweek", "3day"]

        for mode in modes:
            try:
                self._rate_limit(1.0)
                url = f"{API_BASE}?mode={mode}&count=50"
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                for item in data:
                    if not isinstance(item, dict):
                        continue

                    artist = item.get("artist", "").strip()
                    title = item.get("title", "").strip()

                    if not artist or not title:
                        continue

                    key = (artist.lower(), title.lower())
                    if key in seen:
                        continue
                    seen.add(key)

                    post_url = item.get("posturl", "")

                    tracks.append(RawTrack(
                        artist_name=artist,
                        track_title=title,
                        source_name="hype_machine",
                        source_url=post_url if post_url else None,
                        discovered_date=date.today(),
                    ))

            except Exception as e:
                self.logger.warning(f"Hype Machine mode={mode} failed: {e}")

        self.logger.info(f"Found {len(tracks)} tracks from Hype Machine")
        return tracks
