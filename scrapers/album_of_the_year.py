"""Scrape Album of the Year for highly-rated new releases."""
import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.album_of_the_year")

BASE_URL = "https://www.albumoftheyear.org"

REISSUE_KEYWORDS = [
    "remaster", "reissue", "deluxe edition", "anniversary",
    "expanded edition", "redux", "revisited", "re-issue",
    "bonus track", "special edition", "collector",
]


class AlbumOfTheYearScraper(BaseScraper):
    """Scrape new and highly-rated releases from Album of the Year."""

    def __init__(self):
        super().__init__("album_of_the_year")
        # AOTY blocks default user agents
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })

    def scrape(self) -> list[RawTrack]:
        tracks = []
        seen = set()

        # Scrape this week's releases (highest rated page 403s with bot protection)
        pages = [
            f"{BASE_URL}/releases/this-week/",
        ]

        for page_url in pages:
            try:
                page_tracks = self._scrape_page(page_url, seen)
                tracks.extend(page_tracks)
            except Exception as e:
                self.logger.warning(f"AOTY page failed ({page_url}): {e}")

        self.logger.info(f"Found {len(tracks)} albums from Album of the Year")
        return tracks

    def _scrape_page(self, url: str, seen: set) -> list[RawTrack]:
        tracks = []
        self._rate_limit(2.0)
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Grid layout (releases pages): separate artistTitle and albumTitle divs
        for block in soup.select("div.albumBlock"):
            # Skip reissues via data-type attribute
            release_type = block.get("data-type", "")
            if release_type in ("reissue", "live"):
                continue

            artist_el = block.select_one(".artistTitle")
            album_el = block.select_one(".albumTitle")

            if not artist_el or not album_el:
                continue

            artist = artist_el.get_text(strip=True)
            album = album_el.get_text(strip=True)

            if not artist or not album:
                continue

            # Skip reissues/rereleases by album title keywords
            album_lower = album.lower()
            if any(kw in album_lower for kw in REISSUE_KEYWORDS):
                continue

            key = (artist.lower(), album.lower())
            if key in seen:
                continue
            seen.add(key)

            album_link = block.select_one('a[href*="/album/"]')
            album_url = f"{BASE_URL}{album_link['href']}" if album_link else None

            tracks.append(RawTrack(
                artist_name=artist,
                track_title=album,
                source_name="album_of_the_year",
                source_url=album_url,
                album_name=album,
                discovered_date=date.today(),
            ))

        # List layout (highest rated pages): "Artist - Album" in a single link
        for row in soup.select("div.albumListRow"):
            title_link = row.select_one(".albumListTitle a")
            if not title_link:
                continue

            text = title_link.get_text(strip=True)
            # Remove leading rank number like "1. "
            text = re.sub(r'^\d+\.\s*', '', text)

            parts = text.split(" - ", 1)
            if len(parts) != 2:
                continue

            artist, album = parts[0].strip(), parts[1].strip()
            if not artist or not album:
                continue

            key = (artist.lower(), album.lower())
            if key in seen:
                continue
            seen.add(key)

            album_url = f"{BASE_URL}{title_link['href']}" if title_link.get('href') else None

            # Get genre if available
            genre_el = row.select_one(".albumListGenre a")
            genre_hint = genre_el.get_text(strip=True) if genre_el else None

            tracks.append(RawTrack(
                artist_name=artist,
                track_title=album,
                source_name="album_of_the_year",
                source_url=album_url,
                album_name=album,
                genre_hint=genre_hint,
                discovered_date=date.today(),
            ))

        return tracks
