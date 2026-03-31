"""Scrape Gorilla vs Bear for new music via RSS feed.

The homepage is JS-rendered (React/Townsquare CMS), so BeautifulSoup can't parse it.
The RSS feed at /feed/ has 35 items with clean 'Artist -- Track' titles.
"""
import logging
import re
from datetime import date

import feedparser

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.gorilla_vs_bear")

# Skip non-track posts (photo galleries, year-end lists, mixes)
SKIP_PREFIXES = ["photos:", "gorilla vs. bear", "gorilla vs bear"]


class GorillaVsBearScraper(BaseScraper):
    """Scrape Gorilla vs Bear RSS feed for track posts."""

    def __init__(self):
        super().__init__("gorilla_vs_bear")

    def scrape(self) -> list[RawTrack]:
        tracks = []
        try:
            feed = feedparser.parse("https://www.gorillavsbear.net/feed/")

            for entry in feed.entries:
                title = entry.get("title", "")
                url = entry.get("link", "")

                # Skip non-music posts
                title_lower = title.lower().strip()
                if any(title_lower.startswith(p) for p in SKIP_PREFIXES):
                    continue

                # Skip posts tagged only as photos/lists (not mp3)
                categories = [c.get("term", "").lower() for c in entry.get("tags", [])]
                if categories and "mp3" not in categories and "on blast" not in categories:
                    # If it has categories but none are music-related, check if title parses
                    # Some posts have no mp3 tag but are still track posts
                    pass

                # Strip stray HTML tags from RSS titles
                title = re.sub(r'<[^>]+>', '', title)

                parsed = self._parse_title(title)
                if parsed:
                    artist, track_title = parsed
                    tracks.append(RawTrack(
                        artist_name=artist,
                        track_title=track_title,
                        source_name="gorilla_vs_bear",
                        source_url=url,
                        discovered_date=date.today(),
                    ))

        except Exception as e:
            self.logger.error(f"Gorilla vs Bear scrape failed: {e}")

        self.logger.info(f"Found {len(tracks)} tracks from Gorilla vs Bear")
        return tracks

    def _parse_title(self, text: str) -> tuple[str, str] | None:
        """Parse blog post title into (artist, track)."""
        # "Artist – "Track Title"" or "Artist - "Track""
        match = re.match(r'^(.+?)\s*[\u2013\u2014\-]{1,2}\s*["\u201c](.+?)["\u201d]', text)
        if match:
            return match.group(1).strip(), match.group(2).strip()

        # "Artist -- Track Title" or "Artist – Track Title" (no quotes)
        match = re.match(r'^(.+?)\s*[\u2013\u2014]\s+(.+)$', text)
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()
            if len(artist) < 60 and len(title) < 100:
                return artist, title

        # "Artist x Artist -- Track" (collab format)
        match = re.match(r'^(.+?)\s+(?:x|X|feat\.?|ft\.?)\s+(.+?)\s*[\u2013\u2014\-]{1,2}\s+(.+)$', text)
        if match:
            artist = f"{match.group(1).strip()} x {match.group(2).strip()}"
            title = match.group(3).strip()
            return artist, title

        # "Artist drop/share/release Track" (verb format)
        match = re.match(
            r'^(.+?)\s+(?:drop|share|release|debut|unveil|return with)s?\s+(.+)$',
            text, re.IGNORECASE
        )
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()
            if len(artist) < 50:
                return artist, title

        return None
