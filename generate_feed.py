"""
Podcast RSS 피드 생성기
- briefings/ 폴더의 mp3 파일들을 스캔하여 feed.xml 생성
- GitHub Pages URL 기반 팟캐스트 피드
"""

import os
import glob
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

# ── 설정 ──────────────────────────────────────────────
REPO_OWNER = "novvave"
REPO_NAME = "morning-fm"
SITE_URL = f"https://{REPO_OWNER}.github.io/{REPO_NAME}"

PODCAST_TITLE = "Morning FM — Monocle Briefing"
PODCAST_DESCRIPTION = "Monocle Weekend Opener 칼럼의 핵심 인사이트를 매일 한국어로 브리핑합니다."
PODCAST_AUTHOR = "Morning FM Bot"
PODCAST_LANGUAGE = "ko"
PODCAST_IMAGE = f"{SITE_URL}/cover.jpg"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BRIEFINGS_DIR = os.path.join(SCRIPT_DIR, "briefings")
FEED_PATH = os.path.join(SCRIPT_DIR, "feed.xml")

# iTunes 네임스페이스
ITUNES_NS = "http://www.itunes.apple.com/dtds/podcast-1.0.dtd"


def parse_briefing_txt(txt_path: str) -> dict:
    """브리핑 텍스트 파일에서 제목과 요약을 파싱한다."""
    title = ""
    summary = ""

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 제목 추출
    m = re.search(r"■ 제목\n\s+(.+)", content)
    if m:
        title = m.group(1).strip()

    # 요약 추출
    m = re.search(r"■ 핵심 인사이트.*?\n\n(.*?)(?:\n─)", content, re.DOTALL)
    if m:
        summary = m.group(1).strip()

    return {"title": title, "summary": summary}


def scan_episodes() -> list[dict]:
    """briefings/ 폴더에서 mp3 파일들을 스캔하고 에피소드 정보를 수집한다."""
    mp3_files = sorted(glob.glob(os.path.join(BRIEFINGS_DIR, "*.mp3")), reverse=True)
    episodes = []

    for mp3_path in mp3_files:
        filename = os.path.basename(mp3_path)
        # monocle_briefing_2026-04-13.mp3 → 2026-04-13
        m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if not m:
            continue

        date_str = m.group(1)
        pub_date = datetime.strptime(date_str, "%Y-%m-%d").replace(
            hour=9, tzinfo=timezone.utc
        )
        file_size = os.path.getsize(mp3_path)

        # 같은 날짜의 txt 파일에서 메타데이터 파싱
        txt_path = mp3_path.replace(".mp3", ".txt")
        meta = parse_briefing_txt(txt_path) if os.path.exists(txt_path) else {}

        title = meta.get("title", f"Monocle Briefing {date_str}")
        summary = meta.get("summary", "")

        episodes.append(
            {
                "title": title,
                "date_str": date_str,
                "pub_date": pub_date,
                "file_size": file_size,
                "filename": filename,
                "summary": summary,
                "url": f"{SITE_URL}/briefings/{filename}",
            }
        )

    return episodes


def generate_feed() -> str:
    """podcast RSS 2.0 feed.xml을 생성한다."""
    episodes = scan_episodes()

    rss = Element("rss", version="2.0")
    rss.set("xmlns:itunes", ITUNES_NS)

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = PODCAST_TITLE
    SubElement(channel, "link").text = SITE_URL
    SubElement(channel, "description").text = PODCAST_DESCRIPTION
    SubElement(channel, "language").text = PODCAST_LANGUAGE
    SubElement(channel, "generator").text = "Morning FM Bot"

    last_build = datetime.now(timezone.utc)
    SubElement(channel, "lastBuildDate").text = format_datetime(last_build)

    # iTunes 메타데이터
    SubElement(channel, f"{{{ITUNES_NS}}}author").text = PODCAST_AUTHOR
    SubElement(channel, f"{{{ITUNES_NS}}}summary").text = PODCAST_DESCRIPTION
    SubElement(channel, f"{{{ITUNES_NS}}}explicit").text = "no"
    SubElement(channel, f"{{{ITUNES_NS}}}category").text = "News"

    img = SubElement(channel, f"{{{ITUNES_NS}}}image")
    img.set("href", PODCAST_IMAGE)

    # 에피소드 추가
    for ep in episodes:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = f"[{ep['date_str']}] {ep['title']}"
        SubElement(item, "description").text = ep["summary"] or ep["title"]
        SubElement(item, "pubDate").text = format_datetime(ep["pub_date"])
        SubElement(item, "guid", isPermaLink="false").text = (
            f"morning-fm-{ep['date_str']}"
        )

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", ep["url"])
        enclosure.set("length", str(ep["file_size"]))
        enclosure.set("type", "audio/mpeg")

        SubElement(item, f"{{{ITUNES_NS}}}author").text = PODCAST_AUTHOR
        SubElement(item, f"{{{ITUNES_NS}}}duration").text = "1:00"
        SubElement(item, f"{{{ITUNES_NS}}}summary").text = (
            ep["summary"] or ep["title"]
        )

    # XML 저장
    tree = ElementTree(rss)
    indent(tree, space="  ")

    with open(FEED_PATH, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)

    return FEED_PATH


if __name__ == "__main__":
    path = generate_feed()
    print(f"✅ feed.xml 생성됨: {path}")
