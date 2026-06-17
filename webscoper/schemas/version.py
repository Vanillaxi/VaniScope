from __future__ import annotations

from pydantic import BaseModel


class VersionContext(BaseModel):
    runtime_version: str = "0.1.0"
    skill_version: str = "browser_runtime@0.1.0"
    prompt_version: str = "none"
    tool_schema_version: str = "browser_tools@0.1.0"
    review_policy_version: str = "none"
    eval_case_version: str | None = None
    model: str = "none"
