"""Scrape Stereogum for new music posts via RSS feed."""
import logging
import re
from datetime import date

import feedparser

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.stereogum")


class StereogumScraper(BaseScraper):
    """Scrape Stereogum's RSS feed for new music."""

    def __init__(self):
        super().__init__("stereogum")

    def scrape(self) -> list[RawTrack]:
        tracks = []
        try:
            feed = feedparser.parse("https://www.stereogum.com/feed/")

            for entry in feed.entries:
                title = entry.get("title", "")
                url = entry.get("link", "")

                parsed = self._parse_title(title)
                if parsed:
                    artist, track_title = parsed
                    tracks.append(RawTrack(
                        artist_name=artist,
                        track_title=track_title,
                        source_name="stereogum",
                        source_url=url,
                        discovered_date=date.today(),
                    ))

        except Exception as e:
            self.logger.error(f"Stereogum scrape failed: {e}")

        return tracks

    def _parse_title(self, text: str) -> tuple[str, str] | None:
        """Parse RSS entry title into (artist, track)."""
        # "Artist \u2013 \u201cTrack Title\u201d" or with regular quotes
        match = re.match(r'^(.+?)\s*[\u2013\u2014\-]\s*[\u201c\u201d\u2018\u2019"\'](.+?)[\u201c\u201d\u2018\u2019"\']', text)
        if match:
            return match.group(1).strip(), match.group(2).strip()

        # "Artist Share/Release/Debut New Song \u201cTrack\u201d"
        match = re.match(
            r'^(.+?)\s+(?:Share|Release|Drop|Announce|Unveil|Debut)\w*\s+.*?[\u201c\u201d"\'](.+?)[\u201c\u201d"\']',
            text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip(), match.group(2).strip()

        # "Artist Perform/Cover ... \u201cSong\u201d"
        match = re.match(
            r'^(.+?)\s+(?:Perform|Cover)\w*\s+.*?[\u201c\u201d"\'](.+?)[\u201c\u201d"\']',
            text, re.IGNORECASE
        )
        if match:
            return match.group(1).strip(), match.group(2).strip()

        return None
