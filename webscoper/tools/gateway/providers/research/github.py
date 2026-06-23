from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from webscoper.tools.gateway.providers.common import optional_int, optional_str
from webscoper.tools.gateway.providers.research.extractors import (
    compact_text,
    compact_whitespace,
    first_non_empty,
    heading_text,
    meta_content,
    tag_text,
    unique_non_empty,
    visible_text,
)


def github_url(arguments: dict[str, Any], *, kind: str) -> str | None:
    url = optional_str(arguments.get("url"))
    if url:
        return url
    repo = optional_str(arguments.get("repo"))
    number = optional_int(arguments.get("number"))
    if not repo or number is None:
        return None
    path = "pull" if kind == "pull" else "issues"
    return f"https://github.com/{repo.strip('/')}/{path}/{number}"


def is_github_url(url: str, *, kind: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname != "github.com":
        return False
    parts = [part for part in parsed.path.split("/") if part]
    marker = "pull" if kind == "pull" else "issues"
    return len(parts) >= 4 and parts[2] == marker and parts[3].isdigit()


def github_output(html: str, *, source_url: str, kind: str) -> dict[str, Any]:
    text = visible_text(html)
    title = first_non_empty(
        meta_content(html, "og:title"),
        tag_text(html, "title"),
        heading_text(html),
    )
    return {
        "kind": kind,
        "title": title or "Untitled GitHub item",
        "state": state(text),
        "labels": labels(html, text),
        "author": author(text),
        "body_text": compact_text(text, limit=6000),
        "comments_excerpt": comments_excerpt(text),
        "source_url": source_url,
        "status": "success",
    }


def labels(html: str, text: str) -> list[str]:
    html_labels = [
        visible_text(match).strip()
        for match in re.findall(
            r'class=["\'][^"\']*label[^"\']*["\'][^>]*>(.*?)</',
            html,
            flags=re.I | re.S,
        )
    ]
    if html_labels:
        return unique_non_empty(html_labels)[:20]
    section = re.search(
        r"Labels\s+(.+?)(?:Issue Body|Expected Behavior|Current Behavior|$)",
        text,
        flags=re.I,
    )
    if not section:
        return []
    return unique_non_empty(re.split(r"\s{2,}|,\s*", section.group(1)))[:20]


def state(text: str) -> str | None:
    match = re.search(r"\b(open|closed|merged)\b", text, flags=re.I)
    return match.group(1).lower() if match else None


def author(text: str) -> str | None:
    match = re.search(r"(?:Author|Maintainer):\s*([^\n\.]+)", text, flags=re.I)
    return match.group(1).strip() if match else None


def comments_excerpt(text: str) -> list[str]:
    excerpts = []
    for label in ("Maintainer Comments", "Comments", "Review"):
        match = re.search(rf"{label}\s+(.+?)(?:Acceptance Criteria|Risks|$)", text, flags=re.I)
        if match:
            excerpts.append(compact_text(match.group(1), limit=600))
    return excerpts[:5]
