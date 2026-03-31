"""Scrape r/indieheads for new music posts via JSON API."""
import logging
import re
from datetime import date

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.reddit_indieheads")


class RedditIndieheadsScraper(BaseScraper):
    """Scrape r/indieheads for [FRESH] track posts."""

    def __init__(self):
        super().__init__("reddit_indieheads")
        self.session.headers.update({"User-Agent": "IndieMusicDiscovery/1.0"})

    def scrape(self) -> list[RawTrack]:
        tracks = []
        try:
            self._rate_limit()
            resp = self.session.get(
                "https://old.reddit.com/r/indieheads/search.json",
                params={
                    "q": "[FRESH]",
                    "restrict_sr": "on",
                    "sort": "new",
                    "t": "week",
                    "limit": 100,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            for post in data.get("data", {}).get("children", []):
                title = post.get("data", {}).get("title", "")
                url = post.get("data", {}).get("url", "")

                # Skip non-track FRESH posts and recap posts
                if re.search(r'\[FRESH\s+(ALBUM|VIDEO|PERFORMANCE|STREAM)\]', title, re.IGNORECASE):
                    continue
                if 'recap for the week' in title.lower():
                    continue

                parsed = self._parse_title(title)
                if parsed:
                    artist, track_title = parsed
                    tracks.append(RawTrack(
                        artist_name=artist,
                        track_title=track_title,
                        source_name="reddit_indieheads",
                        source_url=url,
                        discovered_date=date.today(),
                    ))

        except Exception as e:
            self.logger.error(f"Reddit indieheads scrape failed: {e}")

        return tracks

    def _parse_title(self, title: str) -> tuple[str, str] | None:
        """Parse Reddit post title like '[FRESH] Artist - Track Title'."""
        clean = re.sub(r'\[.*?\]', '', title).strip()

        match = re.match(r'^(.+?)\s*[\u2013\u2014\-]\s+(.+)$', clean)
        if match:
            artist = match.group(1).strip()
            track = match.group(2).strip()
            if len(artist) < 80 and len(track) < 150:
                return artist, track

        return None
