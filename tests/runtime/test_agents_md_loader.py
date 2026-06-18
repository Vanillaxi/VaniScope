from __future__ import annotations

from pathlib import Path

from webscoper.runtime.agents_md import AgentsMdLoader


def test_agents_md_loader_loads_workspace_instructions() -> None:
    workspace = Path("tests/fixtures/workspace")

    instructions = AgentsMdLoader(include_global=False).load(workspace)

    assert len(instructions) >= 1
    assert "Prefer official documentation" in instructions[0].content
    assert instructions[0].source_path.endswith("AGENTS.md")
