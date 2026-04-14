"""
Gmail에서 Monocle 뉴스레터를 읽어오는 모듈
- 최신 Monocle 뉴스레터 검색
- 제목, 날짜, 본문 텍스트 추출
- monocle_briefing.py와 동일한 dict 형식 반환
"""

from __future__ import annotations

import base64
import re
from typing import Optional

from bs4 import BeautifulSoup

from gmail_auth import get_gmail_service


def fetch_monocle_newsletter(max_results: int = 1) -> Optional[dict]:
    """Gmail에서 최신 Monocle 뉴스레터를 가져온다.

    Returns:
        scrape_article()과 동일한 형식의 dict:
        {"title": str, "date": str, "url": str, "body": str}
    """
    service = get_gmail_service()

    # Monocle 발신 이메일 검색
    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            q="from:monocle.com",
            maxResults=max_results,
        )
        .execute()
    )

    messages = results.get("messages", [])
    if not messages:
        print("⚠️  Monocle 뉴스레터를 찾을 수 없습니다.")
        return None

    msg_id = messages[0]["id"]
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="full")
        .execute()
    )

    # 헤더에서 제목, 날짜 추출
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    subject = headers.get("Subject", "제목 없음")
    date_str = headers.get("Date", "")

    # 본문 HTML 추출
    html_body = _extract_html_body(msg["payload"])
    body_text = _html_to_text(html_body) if html_body else ""

    # 뉴스레터 내 링크 중 monocle.com 링크 추출
    url = ""
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "monocle.com" in href and "/the-weekend-opener/" in href:
                url = href
                break
        if not url:
            for a in soup.find_all("a", href=True):
                if "monocle.com" in a["href"]:
                    url = a["href"]
                    break

    return {
        "title": subject,
        "date": date_str,
        "url": url or "https://monocle.com",
        "body": body_text,
    }


def _extract_html_body(payload: dict) -> str:
    """이메일 payload에서 HTML 본문을 재귀적으로 추출한다."""
    # 단일 파트
    if payload.get("mimeType") == "text/html" and "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    # 멀티파트
    for part in payload.get("parts", []):
        result = _extract_html_body(part)
        if result:
            return result

    # text/plain fallback
    if payload.get("mimeType") == "text/plain" and "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            return f"<p>{text}</p>"

    return ""


def _html_to_text(html: str) -> str:
    """HTML을 정리된 텍스트로 변환한다."""
    soup = BeautifulSoup(html, "html.parser")

    # 스타일, 스크립트 제거
    for tag in soup(["style", "script", "head"]):
        tag.decompose()

    # 텍스트 추출
    text = soup.get_text(separator="\n")

    # 빈 줄 정리
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    # 짧은 줄(네비게이션 등) 필터링하여 본문만 추출
    body_lines = [line for line in lines if len(line) > 20]

    return "\n\n".join(body_lines[:30])  # 앞부분 30줄


if __name__ == "__main__":
    newsletter = fetch_monocle_newsletter()
    if newsletter:
        print(f"제목: {newsletter['title']}")
        print(f"날짜: {newsletter['date']}")
        print(f"URL:  {newsletter['url']}")
        print(f"\n본문 ({len(newsletter['body'])}자):")
        print(newsletter["body"][:500])
