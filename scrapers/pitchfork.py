"""Scrape Pitchfork's Best New Tracks and recent reviews."""
import logging
import re
from datetime import date

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.pitchfork")


class PitchforkScraper(BaseScraper):
    """Scrape Pitchfork for best new tracks and highly rated reviews."""

    def __init__(self):
        super().__init__("pitchfork")

    def scrape(self) -> list[RawTrack]:
        tracks = []
        tracks.extend(self._scrape_best_new_tracks())
        tracks.extend(self._scrape_best_albums())
        return tracks

    def _scrape_best_new_tracks(self) -> list[RawTrack]:
        """Scrape the Best New Tracks page."""
        tracks = []
        try:
            html = self.fetch("https://pitchfork.com/reviews/best/tracks/")
            soup = BeautifulSoup(html, "lxml")

            for item in soup.select(".summary-item"):
                text = item.get_text(" ", strip=True)

                # Pattern: "Genre(s) \u00abTrack Title\u00bb Artist By Reviewer Date"
                # The guillemets \u00ab \u00bb wrap the track title
                match = re.search(
                    r'[\u00ab\u201c\u2018](.+?)[\u00bb\u201d\u2019]\s+(.+?)\s+By\s+',
                    text
                )
                if match:
                    track_title = match.group(1).strip()
                    artist = match.group(2).strip()

                    if artist and track_title and len(artist) < 100:
                        tracks.append(RawTrack(
                            artist_name=artist,
                            track_title=track_title,
                            source_name="pitchfork",
                            source_url="https://pitchfork.com/reviews/best/tracks/",
                            discovered_date=date.today(),
                        ))

        except Exception as e:
            self.logger.error(f"Best new tracks scrape failed: {e}")

        return tracks

    def _scrape_best_albums(self) -> list[RawTrack]:
        """Scrape Best New Albums for artist names (search will find top tracks)."""
        tracks = []
        try:
            html = self.fetch("https://pitchfork.com/reviews/best/albums/")
            soup = BeautifulSoup(html, "lxml")

            for item in soup.select(".summary-item"):
                text = item.get_text(" ", strip=True)

                # Pattern: "Genre(s) Album Title Artist By Reviewer Date"
                match = re.search(
                    r'[\u00ab\u201c\u2018](.+?)[\u00bb\u201d\u2019]\s+(.+?)\s+By\s+',
                    text
                )
                if match:
                    album = match.group(1).strip()
                    artist = match.group(2).strip()

                    if artist and album and len(artist) < 100:
                        tracks.append(RawTrack(
                            artist_name=artist,
                            track_title=album,
                            source_name="pitchfork",
                            source_url="https://pitchfork.com/reviews/best/albums/",
                            album_name=album,
                            discovered_date=date.today(),
                        ))

        except Exception as e:
            self.logger.error(f"Best albums scrape failed: {e}")

        return tracks
