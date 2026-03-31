"""Run summary reporting — log output and HTML report."""
import logging
from datetime import date
from pathlib import Path

from config import PROJECT_ROOT
from storage.models import ScoredTrack

logger = logging.getLogger("reporting")

REPORT_PATH = PROJECT_ROOT / "last_run_report.html"


def log_summary(
    raw_count: int,
    scored_count: int,
    after_filter_count: int,
    playlist_count: int,
    playlist_url: str | None,
):
    logger.info("=" * 50)
    logger.info("RUN SUMMARY")
    logger.info(f"  Raw track mentions scraped: {raw_count}")
    logger.info(f"  Unique tracks after dedup:  {scored_count}")
    logger.info(f"  Tracks after filtering:     {after_filter_count}")
    logger.info(f"  Tracks added to playlist:   {playlist_count}")
    if playlist_url:
        logger.info(f"  Playlist URL: {playlist_url}")
    logger.info("=" * 50)


def generate_html_report(
    raw_count: int,
    scored_count: int,
    after_filter_count: int,
    playlist_tracks: list[ScoredTrack],
    playlist_url: str | None,
    source_stats: dict,
    rate_limited: bool = False,
):
    """Generate an HTML summary report for the run."""
    today = date.today().strftime("%B %d, %Y")
    playlist_count = len(playlist_tracks)

    # Source stats table rows
    source_rows = ""
    for name, info in sorted(source_stats.items(), key=lambda x: x[1]["count"], reverse=True):
        status_class = "ok" if info["status"] == "ok" else "fail"
        source_rows += f"""
        <tr class="{status_class}">
            <td>{name}</td>
            <td>{info['count']}</td>
            <td>{info['status']}</td>
        </tr>"""

    # Playlist tracks table rows
    track_rows = ""
    for i, t in enumerate(playlist_tracks, 1):
        sources = t.sources.replace(",", ", ") if t.sources else ""
        track_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{t.artist_name}</td>
            <td>{t.track_title}</td>
            <td>{t.genre}</td>
            <td>{t.total_score:.3f}</td>
            <td>{sources}</td>
        </tr>"""

    # Top artists in playlist
    artist_counts = {}
    for t in playlist_tracks:
        artist_counts[t.artist_name] = artist_counts.get(t.artist_name, 0) + 1
    top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    top_artists_html = "".join(f"<li>{a} ({c} tracks)</li>" for a, c in top_artists)

    # Genre distribution
    genre_counts = {}
    for t in playlist_tracks:
        genre_counts[t.genre] = genre_counts.get(t.genre, 0) + 1
    genre_dist = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)
    genre_html = "".join(f"<li>{g}: {c}</li>" for g, c in genre_dist)

    rate_limit_banner = ""
    if rate_limited:
        rate_limit_banner = """
        <div class="banner warn">
            Spotify rate limit was hit during this run. Some tracks may be missing Spotify URIs.
            Cached results were used where available. Next run will pick up the rest.
        </div>"""

    playlist_link = ""
    if playlist_url:
        playlist_link = f'<a href="{playlist_url}" class="playlist-link">Open Playlist in Spotify</a>'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Indie Discoveries - {today}</title>
<style>
    body {{ font-family: -apple-system, 'Segoe UI', sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #1a1a2e; color: #e0e0e0; }}
    h1 {{ color: #1db954; margin-bottom: 5px; }}
    h2 {{ color: #b3b3b3; border-bottom: 1px solid #333; padding-bottom: 8px; margin-top: 30px; }}
    .date {{ color: #888; font-size: 14px; }}
    .stats {{ display: flex; gap: 20px; flex-wrap: wrap; margin: 20px 0; }}
    .stat {{ background: #16213e; border-radius: 8px; padding: 15px 20px; min-width: 120px; }}
    .stat .num {{ font-size: 28px; font-weight: bold; color: #1db954; }}
    .stat .label {{ font-size: 12px; color: #888; text-transform: uppercase; }}
    .playlist-link {{ display: inline-block; background: #1db954; color: #000; padding: 12px 24px; border-radius: 24px; text-decoration: none; font-weight: bold; margin: 15px 0; }}
    .playlist-link:hover {{ background: #1ed760; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 10px 0; }}
    th {{ text-align: left; padding: 8px; background: #16213e; color: #b3b3b3; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #222; }}
    tr:hover {{ background: #16213e; }}
    tr.fail td {{ color: #e74c3c; }}
    .banner {{ padding: 12px 16px; border-radius: 6px; margin: 15px 0; }}
    .banner.warn {{ background: #3d2e00; border: 1px solid #f39c12; color: #f5d76e; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ padding: 3px 0; }}
    .two-col {{ display: flex; gap: 40px; }}
    .two-col > div {{ flex: 1; }}
</style>
</head>
<body>
    <h1>Indie Discoveries</h1>
    <div class="date">{today}</div>

    {rate_limit_banner}

    <div class="stats">
        <div class="stat"><div class="num">{raw_count}</div><div class="label">Raw Mentions</div></div>
        <div class="stat"><div class="num">{scored_count}</div><div class="label">Unique Tracks</div></div>
        <div class="stat"><div class="num">{after_filter_count}</div><div class="label">After Filters</div></div>
        <div class="stat"><div class="num">{playlist_count}</div><div class="label">In Playlist</div></div>
    </div>

    {playlist_link}

    <h2>Sources</h2>
    <table>
        <tr><th>Source</th><th>Tracks</th><th>Status</th></tr>
        {source_rows}
    </table>

    <div class="two-col">
        <div>
            <h2>Top Artists</h2>
            <ul>{top_artists_html}</ul>
        </div>
        <div>
            <h2>Genre Distribution</h2>
            <ul>{genre_html}</ul>
        </div>
    </div>

    <h2>Playlist Tracks</h2>
    <table>
        <tr><th>#</th><th>Artist</th><th>Track</th><th>Genre</th><th>Score</th><th>Sources</th></tr>
        {track_rows}
    </table>
</body>
</html>"""

    REPORT_PATH.write_text(html, encoding="utf-8")
    logger.info(f"HTML report saved to {REPORT_PATH}")
