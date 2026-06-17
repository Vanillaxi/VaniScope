from __future__ import annotations

from typing import Any, Protocol

from webscoper.schemas.workflow import WorkflowRunResult


class WorkflowAdapter(Protocol):
    def build_graph(self) -> Any:
        ...

    def run(self, request: Any) -> WorkflowRunResult:
        ...
