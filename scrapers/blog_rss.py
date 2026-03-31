"""Generic RSS/Atom feed scraper for music blogs.

Each blog gets its own parser function since title formats vary.
Blogs that don't yield clean artist/track parsing are skipped.
"""
import logging
import re
from datetime import date

import feedparser

from scrapers.base import BaseScraper
from storage.models import RawTrack

logger = logging.getLogger("scraper.blog_rss")


# --- Title parsers for each blog ---

def _parse_dash_quoted(title: str) -> tuple[str, str] | None:
    """Parse 'Artist -- "Track"' or 'Artist – "Track"' format (Obscure Sound style)."""
    match = re.match(
        r"^(.+?)\s*[\u2013\u2014\-]{1,2}\s*['\u2018\u2019\u201c\u201d\"]+(.+?)['\u2018\u2019\u201c\u201d\"]+\s*$",
        title
    )
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None


def _parse_shares_new(title: str) -> tuple[str, str] | None:
    """Parse 'Artist shares/releases/unveils new single "Track"' format (EARMILK, Line of Best Fit)."""
    # Try "Artist verb ... 'Track'" pattern
    match = re.match(
        r'^(.+?)\s+(?:share|release|drop|announce|unveil|debut|premiere|return|offer|reveal|deliver)s?\s+.*?'
        r'[\u201c\u201d"\u2018\u2019\'](.+?)[\u201c\u201d"\u2018\u2019\']',
        title, re.IGNORECASE
    )
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
        # Skip if artist part is too long or contains "sign to" (news, not music)
        if len(artist) > 50 or re.search(r'\b(?:sign|join|leave|sue)\b', artist, re.IGNORECASE):
            return None
        return artist, track

    # Try "Artist - 'Track'" with dash separator and quotes
    match = re.match(
        r'^(.+?)\s*[\u2013\u2014\-]\s*[\u201c\u201d"\u2018\u2019\'](.+?)[\u201c\u201d"\u2018\u2019\']',
        title
    )
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
        if len(artist) > 50:
            return None
        return artist, track

    return None


def _parse_colon_separator(title: str) -> tuple[str, str] | None:
    """Parse 'Artist :: Track' format (Aquarium Drunkard).

    Skip editorial entries like 'The Lagniappe Sessions :: Artist' or
    'Transmissions at Big Ears :: ...' which are article titles, not tracks.
    """
    match = re.match(r'^(.+?)\s*::\s*(.+)$', title)
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
        # Skip common non-track prefixes
        skip_prefixes = ["the lagniappe sessions", "transmissions", "aquarium drunkard",
                         "only the good shit", "sidecar", "mixtape", "podcast"]
        if any(artist.lower().startswith(p) for p in skip_prefixes):
            return None
        return artist, track
    return None


def _parse_blackwater(title: str) -> tuple[str, str] | None:
    """Parse 'Artist -- Track (suffix)' format (Blackwater Collective).

    Titles like: '0054: Coughy Bitters -- 1986 (2024)' or 'J.R. Gilmore -- Ghosts (Official Video)'
    Strip leading numbers, trailing (year), (Official Video), etc.
    """
    # Strip leading "0054: " prefix
    cleaned = re.sub(r'^\d+:\s*', '', title)
    # Try dash separator
    match = re.match(r'^(.+?)\s*[\u2013\u2014\-]{1,2}\s+(.+)$', cleaned)
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
        # Remove trailing suffixes like (Official Video), (2024), (Lyric Video)
        track = re.sub(r'\s*\((?:Official|Lyric|Music)?\s*(?:Video|Audio|Visualizer)?\s*\)\s*$', '', track, flags=re.IGNORECASE)
        track = re.sub(r'\s*\(\d{4}\)\s*$', '', track)
        if artist and track and len(artist) < 60:
            return artist, track
    return None


def _parse_post_trash(title: str) -> tuple[str, str] | None:
    """Parse 'Artist - "Track" | Album Review' format (Post-Trash).

    Titles like: 'Dimples - "Obscure Residue" | Album Review'
    Skip interviews and features.
    """
    # Skip non-music posts
    if re.search(r'\b(?:Interview|Feature)\b', title, re.IGNORECASE):
        return None
    # Try 'Artist - "Track" | ...' pattern
    match = re.match(
        r'^(.+?)\s*[\u2013\u2014\-]\s*["\u201c](.+?)["\u201d]\s*(?:\|.*)?$',
        title
    )
    if match:
        artist = match.group(1).strip()
        track = match.group(2).strip()
        if artist and track and len(artist) < 60:
            return artist, track
    return None


def _parse_generic(title: str) -> tuple[str, str] | None:
    """Try multiple common formats as fallback."""
    for parser in [_parse_dash_quoted, _parse_shares_new, _parse_colon_separator]:
        result = parser(title)
        if result:
            return result
    return None


# --- Blog definitions ---

BLOG_FEEDS = [
    {
        "name": "obscure_sound",
        "source_key": "obscure_sound",
        "url": "https://obscuresound.com/feed/",
        "parser": _parse_dash_quoted,
    },
    {
        "name": "earmilk",
        "source_key": "earmilk",
        "url": "https://earmilk.com/feed/",
        "parser": _parse_shares_new,
    },
    {
        "name": "line_of_best_fit",
        "source_key": "line_of_best_fit",
        "url": "https://www.thelineofbestfit.com/feed",
        "parser": _parse_shares_new,
    },
    {
        "name": "aquarium_drunkard",
        "source_key": "aquarium_drunkard",
        "url": "https://aquariumdrunkard.com/feed/",
        "parser": _parse_colon_separator,
    },
    {
        "name": "brooklyn_vegan",
        "source_key": "brooklyn_vegan",
        "url": "https://www.brooklynvegan.com/feed/",
        "parser": _parse_generic,
    },
    {
        "name": "blackwater_collective",
        "source_key": "blackwater_collective",
        "url": "https://blackwaterco.org/feed/",
        "parser": _parse_blackwater,
    },
    {
        "name": "post_trash",
        "source_key": "post_trash",
        "url": "https://post-trash.com/news?format=rss",
        "parser": _parse_post_trash,
    },
]


class BlogRSSScraper(BaseScraper):
    """Scrape a single RSS blog feed for track mentions."""

    def __init__(self, name: str, source_key: str, feed_url: str, parser):
        super().__init__(name)
        self.source_key = source_key
        self.feed_url = feed_url
        self.parser = parser

    def scrape(self) -> list[RawTrack]:
        tracks = []
        try:
            feed = feedparser.parse(self.feed_url)

            for entry in feed.entries:
                title = entry.get("title", "")
                url = entry.get("link", "")

                parsed = self.parser(title)
                if parsed:
                    artist, track_title = parsed
                    tracks.append(RawTrack(
                        artist_name=artist,
                        track_title=track_title,
                        source_name=self.source_key,
                        source_url=url,
                        discovered_date=date.today(),
                    ))

        except Exception as e:
            self.logger.error(f"RSS scrape failed for {self.name}: {e}")

        self.logger.info(f"Found {len(tracks)} tracks from {self.name}")
        return tracks


def get_blog_rss_scrapers() -> list[BlogRSSScraper]:
    """Return a scraper instance for each configured blog feed."""
    return [
        BlogRSSScraper(
            name=blog["name"],
            source_key=blog["source_key"],
            feed_url=blog["url"],
            parser=blog["parser"],
        )
        for blog in BLOG_FEEDS
    ]
