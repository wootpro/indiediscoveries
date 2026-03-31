"""Scraper registry — builds scraper list from user_config.yaml."""
import logging

from config import ENABLED_SCRAPERS, BLOG_RSS_FEEDS

logger = logging.getLogger("scrapers")

# Map of scraper key → (import path, class name)
_SCRAPER_MAP = {
    "kexp":             ("scrapers.kexp",             "KEXPScraper"),
    "pitchfork":        ("scrapers.pitchfork",         "PitchforkScraper"),
    "stereogum":        ("scrapers.stereogum",         "StereogumScraper"),
    "gorilla_vs_bear":  ("scrapers.gorilla_vs_bear",   "GorillaVsBearScraper"),
    "reddit_indieheads":("scrapers.reddit_indieheads", "RedditIndieheadsScraper"),
    "nts":              ("scrapers.nts",               "NTSScraper"),
    "bbc_6music":       ("scrapers.bbc_6music",        "BBC6MusicScraper"),
    "hype_machine":     ("scrapers.hype_machine",      "HypeMachineScraper"),
    "album_of_the_year":("scrapers.album_of_the_year", "AlbumOfTheYearScraper"),
}

# Parser type name → function in blog_rss
_BLOG_PARSER_MAP = {
    "dash_quoted": "_parse_dash_quoted",
    "shares_new":  "_parse_shares_new",
    "colon":       "_parse_colon_separator",
    "blackwater":  "_parse_blackwater",
    "post_trash":  "_parse_post_trash",
    "generic":     "_parse_generic",
}


def get_all_scrapers():
    """Return scraper instances for all enabled sources."""
    import importlib
    scrapers = []

    for key in ENABLED_SCRAPERS:
        if key == "blog_rss":
            scrapers.extend(_get_blog_rss_scrapers())
            continue

        if key not in _SCRAPER_MAP:
            logger.warning(f"Unknown scraper '{key}' in enabled_scrapers — skipping")
            continue

        module_path, class_name = _SCRAPER_MAP[key]
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            scrapers.append(cls())
        except Exception as e:
            logger.error(f"Failed to load scraper '{key}': {e}")

    return scrapers


def _get_blog_rss_scrapers():
    """Build BlogRSSScraper instances from user_config.yaml blog_rss_feeds."""
    from scrapers.blog_rss import BlogRSSScraper
    import scrapers.blog_rss as blog_rss_module

    scrapers = []

    if not BLOG_RSS_FEEDS:
        logger.warning("blog_rss enabled but no blog_rss_feeds configured in user_config.yaml")
        return scrapers

    for feed in BLOG_RSS_FEEDS:
        name = feed.get("name")
        url = feed.get("url")
        parser_type = feed.get("parser", "generic")

        if not name or not url:
            logger.warning(f"Blog RSS feed missing name or url: {feed}")
            continue

        parser_fn_name = _BLOG_PARSER_MAP.get(parser_type)
        if not parser_fn_name:
            logger.warning(f"Unknown parser type '{parser_type}' for feed '{name}' — using generic")
            parser_fn_name = "_parse_generic"

        parser_fn = getattr(blog_rss_module, parser_fn_name)
        scrapers.append(BlogRSSScraper(
            name=name,
            source_key=name,
            feed_url=url,
            parser=parser_fn,
        ))

    return scrapers
