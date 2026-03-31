"""KEXP 90.3 FM recently played tracks via public JSON API."""
import logging
from datetime import date, datetime, timedelta, timezone

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.kexp")

KEXP_API = "https://api.kexp.org/v2/plays/"


class KEXPScraper(BaseScraper):
    """Scrape recently played tracks from KEXP's public API."""

    def __init__(self):
        super().__init__("kexp")

    def scrape(self) -> list[RawTrack]:
        tracks = []
        seen = set()

        start = datetime.now(timezone.utc) - timedelta(days=7)
        url = f"{KEXP_API}?begin_time={start.isoformat()}&has_airplay=true&limit=200&ordering=-airdate"

        try:
            self._rate_limit(1.0)
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for play in data.get("results", []):
                artist_name = play.get("artist", "")
                title = play.get("song", "")
                album = play.get("album", "")

                if not isinstance(artist_name, str) or not isinstance(title, str):
                    continue
                artist_name = artist_name.strip()
                title = title.strip()

                if not artist_name or not title:
                    continue

                key = (artist_name.lower(), title.lower())
                if key in seen:
                    continue
                seen.add(key)

                tracks.append(RawTrack(
                    artist_name=artist_name,
                    track_title=title,
                    source_name="kexp",
                    album_name=album.strip() if isinstance(album, str) and album.strip() else None,
                    discovered_date=date.today(),
                ))

        except Exception as e:
            self.logger.error(f"KEXP scrape failed: {e}")

        return tracks
