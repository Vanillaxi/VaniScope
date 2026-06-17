from __future__ import annotations

from pathlib import Path

from webscoper.schemas.prompt import AgentsMdInstruction


MAX_AGENTS_MD_FILES = 5
MAX_AGENTS_MD_CHARS = 8000


class AgentsMdLoader:
    def __init__(self, include_global: bool = False) -> None:
        self.include_global = include_global

    def load(self, workspace: Path | None = None) -> list[AgentsMdInstruction]:
        instructions: list[AgentsMdInstruction] = []

        if self.include_global:
            global_path = Path.home() / ".vaniscope" / "AGENTS.md"
            instruction = _read_agents_md(global_path)
            if instruction is not None:
                instructions.append(instruction)

        if workspace is not None:
            start = workspace.parent if workspace.is_file() else workspace
            for path in _candidate_paths(start):
                if len(instructions) >= MAX_AGENTS_MD_FILES:
                    break
                instruction = _read_agents_md(path)
                if instruction is not None:
                    instructions.append(instruction)

        return instructions


def _candidate_paths(start: Path) -> list[Path]:
    paths: list[Path] = []
    current = start.resolve()
    while True:
        paths.append(current / "AGENTS.md")
        if (current / ".git").exists() or current.parent == current:
            break
        current = current.parent
    return paths


def _read_agents_md(path: Path) -> AgentsMdInstruction | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    if len(content) > MAX_AGENTS_MD_CHARS:
        content = content[:MAX_AGENTS_MD_CHARS].rstrip() + "\n<!-- truncated -->"

    return AgentsMdInstruction(source_path=str(path), content=content)
