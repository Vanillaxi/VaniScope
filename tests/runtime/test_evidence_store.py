from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.evidence import EvidenceStore


def test_evidence_store_add_list_and_context_pack() -> None:
    store = EvidenceStore()

    first = store.add_item(
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text="Hello",
    )
    second = store.add_item(
        kind="action_result",
        text="Clicked Quickstart.",
        metadata={"verified": True},
    )

    assert first.evidence_id == "ev_000001"
    assert second.evidence_id == "ev_000002"
    assert [item.evidence_id for item in store.list_items()] == [
        "ev_000001",
        "ev_000002",
    ]
    pack = store.to_context_pack(max_items=1)
    assert pack["evidence_count"] == 2
    assert len(pack["items"]) == 1
    assert pack["items"][0]["evidence_id"] == "ev_000001"


def test_evidence_store_writes_jsonl(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence.jsonl"
    store = EvidenceStore(output_path)
    store.add_item(kind="text_excerpt", text="pip install playwright")

    store.write_jsonl()

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["evidence_id"] == "ev_000001"
    assert payload["kind"] == "text_excerpt"
    assert payload["text"] == "pip install playwright"
