from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.schemas.evidence import EvidenceItem, EvidenceKind


class EvidenceStore:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self._items: list[EvidenceItem] = []
        self._next_id = 1

    def add_item(
        self,
        kind: EvidenceKind,
        source_url: str | None = None,
        page_title: str | None = None,
        text: str | None = None,
        screenshot_path: str | None = None,
        trace_event_id: str | None = None,
        transcript_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        item = EvidenceItem(
            evidence_id=f"ev_{self._next_id:06d}",
            kind=kind,
            source_url=source_url,
            page_title=page_title,
            text=text,
            screenshot_path=screenshot_path,
            trace_event_id=trace_event_id,
            transcript_event_id=transcript_event_id,
            created_at=datetime.now(UTC).isoformat(),
            metadata=metadata or {},
        )
        self._next_id += 1
        self._items.append(item)
        return item

    def list_items(self) -> list[EvidenceItem]:
        return list(self._items)

    def write_jsonl(self) -> None:
        if self.output_path is None:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", encoding="utf-8") as file:
            for item in self._items:
                file.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
                file.write("\n")

    def to_context_pack(self, max_items: int | None = None) -> dict[str, Any]:
        items = self._items if max_items is None else self._items[:max_items]
        return {
            "evidence_count": len(self._items),
            "items": [item.model_dump(mode="json") for item in items],
        }
