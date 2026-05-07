import re
from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape

_SEASON_RE = re.compile(r"\b([Ss]eason\s*\d{1,2}|[Ss]\d{1,2})\b")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Matches the first quality/format marker after the show name (version tag, or opening bracket)
_QUALITY_MARKER_RE = re.compile(r"^(\[.*?\]\s*)(.*?)(\s+(?:v\d+|\(|\[))", re.DOTALL)
_QUALITY_MARKER_NO_GROUP_RE = re.compile(r"^(.*?)(\s+(?:v\d+|\(|\[))", re.DOTALL)


def _insert_before_quality(title: str, tag: str) -> str:
    m = _QUALITY_MARKER_RE.match(title)
    if m:
        return f"{m.group(1)}{m.group(2)} {tag}{m.group(3)}{title[m.end():]}"
    m = _QUALITY_MARKER_NO_GROUP_RE.match(title)
    if m:
        return f"{m.group(1)} {tag}{m.group(2)}{title[m.end():]}"
    return f"{title} {tag}"


def _insert_season_tag(title: str, season: int) -> str:
    return _insert_before_quality(title, f"[S{season:02d}]")


def _insert_year_tag(title: str, year: int) -> str:
    return _insert_before_quality(title, f"({year})")


def _caps_xml(mode: str) -> str:
    """Return the capabilities XML for either 'sonarr' or 'radarr' mode."""
    if mode == "sonarr":
        title = "SeaDex Sonarr"
        searching = """
    <search available="yes" supportedParams="q"/>
    <tv-search available="yes" supportedParams="q,tvdbid,season,ep"/>
    <movie-search available="no" supportedParams=""/>
    <music-search available="no" supportedParams=""/>
    <audio-search available="no" supportedParams=""/>
    <book-search available="no" supportedParams=""/>"""
        categories = """
    <category id="5000" name="TV">
      <subcat id="5070" name="Anime"/>
    </category>"""
    else:
        title = "SeaDex Radarr"
        searching = """
    <search available="yes" supportedParams="q"/>
    <tv-search available="no" supportedParams=""/>
    <movie-search available="yes" supportedParams="q,tmdbid,imdbid"/>
    <music-search available="no" supportedParams=""/>
    <audio-search available="no" supportedParams=""/>
    <book-search available="no" supportedParams=""/>"""
        categories = """
    <category id="2000" name="Movies">
      <subcat id="2070" name="Anime"/>
    </category>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.1" title="{title}" strapline="Best anime releases via SeaDex" url="https://releases.moe"/>
  <limits max="100" default="50"/>
  <registration available="no" open="no"/>
  <searching>{searching}
  </searching>
  <categories>{categories}
  </categories>
</caps>"""


def _prowlarr_test_xml(mode: str) -> str:
    """Return a minimal valid RSS feed for Prowlarr health checks."""
    cat = "5070" if mode == "sonarr" else "2070"
    title = "SeaDex Sonarr Indexer" if mode == "sonarr" else "SeaDex Radarr Indexer"
    dummy_title = "Fullmetal Alchemist Brotherhood [SeaDexBest]" if mode == "sonarr" \
        else "Sword of the Stranger [SeaDexBest]"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>{title}</title>
    <link>https://releases.moe</link>
    <description>Best anime releases via SeaDex</description>
    <item>
      <title><![CDATA[{dummy_title}]]></title>
      <guid>https://nyaa.si/download/1.torrent</guid>
      <comments>https://nyaa.si/view/1</comments>
      <link>https://nyaa.si/download/1.torrent</link>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
      <enclosure url="https://nyaa.si/download/1.torrent" length="1000000000" type="application/x-bittorrent"/>
      <torznab:attr name="category" value="{cat}"/>
      <torznab:attr name="seeders" value="100"/>
      <torznab:attr name="peers" value="100"/>
      <torznab:attr name="downloadvolumefactor" value="0"/>
      <torznab:attr name="uploadvolumefactor" value="1"/>
    </item>
  </channel>
</rss>"""


def _empty_xml(mode: str) -> str:
    title = "SeaDex Sonarr Indexer" if mode == "sonarr" else "SeaDex Radarr Indexer"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>{title}</title>
    <link>https://releases.moe</link>
    <description>Best anime releases via SeaDex</description>
  </channel>
</rss>"""


def _build_item(t: dict, mode: str, season: Optional[int] = None, year: Optional[int] = None) -> str:
    cat = "5070" if mode == "sonarr" else "2070"
    seadex_tag = "[SeaDexBest]" if t["best"] else "[SeaDexAlt]"
    tag_str = " ".join(f"[{tag}]" for tag in t.get("tags", []))

    title = t["title"]
    if season is not None and season > 0 and not _SEASON_RE.search(title):
        title = _insert_season_tag(title, season)
    if year is not None and not _YEAR_RE.search(title):
        title = _insert_year_tag(title, year)

    full_title = f"{title} {seadex_tag}"
    if tag_str:
        full_title += f" {tag_str}"

    hash_attr = (
        f'\n      <torznab:attr name="infohash" value="{t["hash"]}"/>'
        if t.get("hash")
        else ""
    )

    return f"""
    <item>
      <title><![CDATA[{full_title}]]></title>
      <guid>{escape(t['viewUrl'])}</guid>
      <comments>{escape(t['viewUrl'])}</comments>
      <link>{escape(t['link'])}</link>
      <pubDate>{t['pubDate']}</pubDate>
      <enclosure url="{escape(t['link'])}" length="{t['size']}" type="application/x-bittorrent"/>
      <torznab:attr name="category" value="{cat}"/>
      <torznab:attr name="seeders" value="{t['seeders']}"/>
      <torznab:attr name="peers" value="{t['peers']}"/>{hash_attr}
      <torznab:attr name="downloadvolumefactor" value="0"/>
      <torznab:attr name="uploadvolumefactor" value="1"/>
    </item>"""


def build_results_xml(torrents: list[dict], mode: str, season: Optional[int] = None, year: Optional[int] = None) -> str:
    title = "SeaDex Sonarr Indexer" if mode == "sonarr" else "SeaDex Radarr Indexer"
    items = "".join(_build_item(t, mode, season, year) for t in torrents if t.get("title") and t.get("link"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>{title}</title>
    <link>https://releases.moe</link>
    <description>Best anime releases via SeaDex</description>
    {items}
  </channel>
</rss>"""


# Public exports
caps_xml = _caps_xml
prowlarr_test_xml = _prowlarr_test_xml
empty_xml = _empty_xml
