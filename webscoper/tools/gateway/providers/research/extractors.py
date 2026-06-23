from __future__ import annotations

import re
from html import unescape
from typing import Any

from webscoper.tools.gateway.descriptors import ToolInvocationRequest


def docs_extract_output(request: ToolInvocationRequest) -> dict[str, Any]:
    html = text_arg(request, "html")
    text = text_arg(request, "text") or page_observation_text(request)
    source_url = text_arg(request, "url") or page_observation_value(request, "url")
    title = page_observation_value(request, "title")
    if html:
        text = visible_text(html)
        title = title or first_non_empty(tag_text(html, "title"), heading_text(html))
    query = text_arg(request, "query")
    matched_excerpt = matched_excerpt_for_query(text, query) if query else compact_text(text, limit=600)
    return {
        "source_url": source_url,
        "title": title,
        "content_text": compact_text(text, limit=10000),
        "matched_excerpt": matched_excerpt,
        "status": "success",
    }


def table_extract_output(request: ToolInvocationRequest) -> dict[str, Any]:
    html = text_arg(request, "html")
    text = text_arg(request, "text") or page_observation_text(request)
    tables = html_tables(html) if html else text_tables(text)
    return {
        "source_url": text_arg(request, "url") or page_observation_value(request, "url"),
        "tables": tables,
        "table_count": len(tables),
        "status": "success",
    }


def html_tables(html: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table_html in re.findall(r"<table\b[^>]*>(.*?)</table>", html, flags=re.I | re.S):
        rows: list[list[str]] = []
        for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
            cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, flags=re.I | re.S)
            if cells:
                rows.append([visible_text(cell).strip() for cell in cells])
        if not rows:
            continue
        headers = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        tables.append(
            {
                "headers": headers,
                "rows": [
                    {
                        headers[index] if index < len(headers) else f"column_{index + 1}": value
                        for index, value in enumerate(row)
                    }
                    for row in data_rows
                ],
            }
        )
    return tables


def text_tables(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    if len(lines) < 2:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=False)))
    return [{"headers": headers, "rows": rows}] if rows else []


def visible_text(html: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return compact_whitespace(unescape(text))


def tag_text(html: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, flags=re.I | re.S)
    return visible_text(match.group(1)) if match else None


def heading_text(html: str) -> str | None:
    for level in range(1, 4):
        value = tag_text(html, f"h{level}")
        if value:
            return value
    return None


def meta_content(html: str, property_name: str) -> str | None:
    match = re.search(
        rf'<meta\b[^>]*(?:property|name)=["\']{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    return unescape(match.group(1)).strip() if match else None


def matched_excerpt_for_query(text: str, query: str | None) -> str | None:
    if not query:
        return None
    terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", query) if len(term) > 2]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term in lowered for term in terms):
            return compact_text(sentence, limit=600)
    return compact_text(text, limit=600)


def page_observation_text(request: ToolInvocationRequest) -> str:
    observation = request.page_observation if isinstance(request.page_observation, dict) else {}
    return compact_whitespace(
        str(
            observation.get("visible_text_summary")
            or observation.get("main_content_summary")
            or observation.get("accessibility_summary")
            or ""
        )
    )


def page_observation_value(request: ToolInvocationRequest, key: str) -> str | None:
    observation = request.page_observation if isinstance(request.page_observation, dict) else {}
    value = observation.get(key)
    return str(value) if value else None


def text_arg(request: ToolInvocationRequest, key: str) -> str:
    value = request.arguments.get(key)
    return str(value) if value else ""


def first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = compact_whitespace(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def compact_text(text: str, *, limit: int) -> str:
    compacted = compact_whitespace(text)
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 14].rstrip() + " [truncated]"


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
