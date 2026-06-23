from __future__ import annotations

from webscoper.schemas.tool import ToolCatalogSnapshot, ToolSearchResult, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> ToolSpec | None:
        return self._tools.get(tool_id)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def snapshot(self) -> ToolCatalogSnapshot:
        core_tools: list[ToolSpec] = []
        lazy_tools: list[ToolSpec] = []
        runtime_tools: list[ToolSpec] = []

        for tool in self._tools.values():
            if tool.exposure in {"compatibility", "disabled"} or tool.compatibility_wrapper:
                continue
            if tool.loading_mode == "core":
                core_tools.append(tool)
            elif tool.loading_mode == "lazy":
                lazy_tools.append(tool)
            elif tool.loading_mode == "runtime":
                runtime_tools.append(tool)

        return ToolCatalogSnapshot(
            core_tools=core_tools,
            lazy_tools=lazy_tools,
            runtime_tools=runtime_tools,
        )

    def search(self, query: str, limit: int = 5) -> ToolSearchResult:
        normalized_query = query.lower()
        matches: list[ToolSpec] = []

        for tool in self._tools.values():
            haystack = " ".join(
                [
                    tool.tool_id,
                    tool.name,
                    tool.description,
                    " ".join(tool.tags),
                ]
            ).lower()
            if normalized_query in haystack or _all_terms_match(normalized_query, haystack):
                matches.append(tool)
            if len(matches) >= limit:
                break

        return ToolSearchResult(query=query, matches=matches)


def create_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    for tool in _browser_v2_tools():
        registry.register(tool)

    registry.register(
        ToolSpec(
            tool_id="web_search",
            name="Web Search",
            description="Search public web pages for relevant sources.",
            prompt="Search public web pages for relevant sources.",
            loading_mode="lazy",
            exposure="lazy",
            real_llm_prompt_allowed=False,
            tags=["web", "search", "sources"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="github_fetch_issue",
            name="GitHub Fetch Issue",
            description="Fetch public GitHub issue metadata, body, comments and linked pull requests.",
            prompt="Fetch public GitHub issue metadata, body, comments and linked pull requests.",
            loading_mode="lazy",
            exposure="lazy",
            real_llm_prompt_allowed=False,
            tags=["github", "issue", "comments"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="github_fetch_pr",
            name="GitHub Fetch PR",
            description="Fetch public GitHub pull request metadata, checks and review information.",
            prompt="Fetch public GitHub pull request metadata, checks and review information.",
            loading_mode="lazy",
            exposure="lazy",
            real_llm_prompt_allowed=False,
            tags=["github", "pull request", "pr", "checks", "review"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="docs_search",
            name="Docs Search",
            description="Search official documentation pages.",
            prompt="Search official documentation pages.",
            loading_mode="lazy",
            exposure="lazy",
            real_llm_prompt_allowed=False,
            tags=["docs", "documentation", "official", "search"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="table_extract",
            name="Table Extract",
            description="Extract structured rows from visible HTML tables.",
            prompt="Extract structured rows from visible HTML tables.",
            loading_mode="lazy",
            exposure="lazy",
            real_llm_prompt_allowed=False,
            tags=["table", "extract", "html", "structured"],
        )
    )

    return registry


def _browser_v2_tools() -> list[ToolSpec]:
    return [
        _browser_tool(
            "browser_open",
            "Browser Open",
            "Open a URL in the task browser session without extracting the full page.",
            input_schema={
                "url": "string",
                "session_id": "string optional",
                "wait_until": "load | domcontentloaded | networkidle optional",
                "reason": "string optional",
            },
            output_schema={
                "url": "string",
                "final_url": "string",
                "title": "string",
                "status": "success | failed | blocked",
                "navigation_timing": "object",
                "screenshot_evidence_id": "string optional",
                "observation_id": "string optional",
            },
            produces_evidence=True,
            produces_screenshot=True,
            exposure="core",
            tags=["browser", "v2", "open", "navigation"],
        ),
        _browser_tool(
            "browser_observe",
            "Browser Observe",
            "Observe the current page as LLM-ready DOM text, accessibility summary, interactions, readiness, risk signals, and optional screenshot.",
            input_schema={
                "session_id": "string optional",
                "include_screenshot": "bool default true",
                "include_accessibility": "bool default true",
                "reason": "string optional",
            },
            output_schema={
                "observation_id": "string",
                "url": "string",
                "title": "string",
                "visible_text_summary": "string",
                "main_content_summary": "string",
                "accessibility_summary": "string",
                "interactive_elements": "array",
                "screenshot_path": "string optional",
                "screenshot_evidence_id": "string optional",
                "readiness": "object",
                "risk_signals": "array",
            },
            produces_evidence=True,
            produces_screenshot=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "observe", "accessibility"],
        ),
        _browser_tool(
            "browser_click",
            "Browser Click",
            "Click a target by natural-language hint, then verify the expected effect.",
            input_schema={
                "target_hint": "string",
                "expected_effect": "object optional",
                "session_id": "string optional",
                "reason": "string optional",
            },
            output_schema={
                "selected_target": "object",
                "url_before": "string",
                "url_after": "string",
                "title_before": "string",
                "title_after": "string",
                "status": "success | failed | blocked",
                "effect_verification": "object",
                "before_screenshot_evidence_id": "string optional",
                "after_screenshot_evidence_id": "string optional",
            },
            produces_evidence=True,
            produces_screenshot=True,
            can_mutate_page=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "click", "intent", "verifier"],
        ),
        _browser_tool(
            "browser_type",
            "Browser Type",
            "Type mock or safe text into a target field. It never submits and blocks sensitive input.",
            input_schema={
                "target_hint": "string",
                "text": "string",
                "session_id": "string optional",
                "reason": "string optional",
            },
            output_schema={
                "selected_target": "object",
                "status": "success | failed | blocked",
                "safety_decision": "object",
                "evidence_ids": "array",
            },
            permission="sensitive",
            risk_level="sensitive",
            produces_evidence=True,
            can_mutate_page=True,
            requires_session=True,
            public_web_allowed=False,
            exposure="contextual",
            public_web_exposure="approval_required",
            tags=["browser", "v2", "type", "input", "safe-fixture"],
        ),
        _browser_tool(
            "browser_select",
            "Browser Select",
            "Select an option by visible text or option value on safe local pages.",
            input_schema={
                "target_hint": "string",
                "option_text": "string optional",
                "option_value": "string optional",
                "session_id": "string optional",
                "reason": "string optional",
            },
            output_schema={
                "selected_target": "object",
                "selected_option": "object",
                "status": "success | failed | blocked",
                "safety_decision": "object",
                "evidence_ids": "array",
            },
            permission="sensitive",
            risk_level="sensitive",
            produces_evidence=True,
            can_mutate_page=True,
            requires_session=True,
            public_web_allowed=False,
            exposure="contextual",
            public_web_exposure="approval_required",
            tags=["browser", "v2", "select", "input", "safe-fixture"],
        ),
        _browser_tool(
            "browser_scroll",
            "Browser Scroll",
            "Scroll the current page and record an observation and screenshot evidence.",
            input_schema={
                "direction": "down | up",
                "amount": "small | medium | large",
                "session_id": "string optional",
                "reason": "string optional",
            },
            output_schema={
                "scroll_position_before": "object",
                "scroll_position_after": "object",
                "observation_id": "string",
                "screenshot_evidence_id": "string optional",
                "status": "success | failed",
            },
            produces_evidence=True,
            produces_screenshot=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "scroll", "read_only"],
        ),
        _browser_tool(
            "browser_wait",
            "Browser Wait",
            "Wait for a browser condition such as readiness, URL change, content, network quiet, or fixed delay.",
            input_schema={
                "condition": "readiness | url_changes | content_appears | network_quiet | fixed_delay",
                "value": "string optional",
                "timeout_ms": "integer optional",
                "session_id": "string optional",
                "reason": "string optional",
            },
            output_schema={
                "status": "success | failed | timeout",
                "elapsed_ms": "integer",
                "readiness": "object",
                "warnings": "array",
                "observation_id": "string optional",
            },
            produces_evidence=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "wait", "readiness"],
        ),
        _browser_tool(
            "browser_extract",
            "Browser Extract",
            "Extract visible information from the current page into evidence-backed summary.",
            input_schema={
                "instruction": "string",
                "session_id": "string optional",
                "evidence_mode": "text | observation optional",
            },
            output_schema={
                "extracted_summary": "string",
                "structured_data": "object optional",
                "evidence_ids": "array",
                "source_url": "string",
                "status": "success | failed",
            },
            produces_evidence=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "extract", "visible", "structured"],
        ),
        _browser_tool(
            "browser_screenshot",
            "Browser Screenshot",
            "Capture an explicit screenshot as first-class evidence.",
            input_schema={"session_id": "string optional", "reason": "string optional"},
            output_schema={
                "screenshot_path": "string",
                "screenshot_evidence_id": "string",
                "url": "string",
                "title": "string",
                "status": "success | failed",
            },
            produces_evidence=True,
            produces_screenshot=True,
            requires_session=True,
            exposure="contextual",
            tags=["browser", "v2", "screenshot", "evidence"],
        ),
        _browser_tool(
            "ask_human",
            "Ask Human",
            "Pause for human input or approval when a browser action would be unsafe or ambiguous.",
            input_schema={
                "reason": "string",
                "options": "array optional",
                "risk_context": "object optional",
            },
            output_schema={
                "decision": "approved | rejected | needs_input",
                "selected_option": "string optional",
                "comment": "string optional",
            },
            permission="sensitive",
            risk_level="sensitive",
            public_web_allowed=True,
            exposure="core",
            tags=["human", "approval", "safety"],
        ),
        _browser_tool(
            "finish_task",
            "Finish Task",
            "Finish without new browser actions and request evidence-based report generation.",
            input_schema={
                "summary_instruction": "string optional",
                "evidence_ids": "array optional",
            },
            output_schema={
                "final_report_path": "string optional",
                "status": "success",
                "evidence_ids": "array",
            },
            exposure="core",
            tags=["finish", "task", "summary", "v2"],
        ),
        _browser_tool(
            "browser_open_observe",
            "Browser Open Observe",
            "Compatibility wrapper for browser_open followed by browser_observe.",
            input_schema={"url": "string", "reason": "string optional"},
            output_schema={"observation": "object", "status": "success | blocked | failed"},
            produces_evidence=True,
            produces_screenshot=True,
            compatibility_wrapper=True,
            exposure="compatibility",
            real_llm_prompt_allowed=False,
            tags=["browser", "compatibility", "open", "observe"],
        ),
        _browser_tool(
            "browser_click_intent",
            "Browser Click Intent",
            "Compatibility wrapper for browser_click.",
            input_schema={"action": "object"},
            output_schema={"status": "success | blocked | failed", "observation": "object"},
            produces_evidence=True,
            produces_screenshot=True,
            can_mutate_page=True,
            compatibility_wrapper=True,
            exposure="compatibility",
            real_llm_prompt_allowed=False,
            tags=["browser", "compatibility", "click", "intent"],
        ),
        _browser_tool(
            "browser_upload_file",
            "Browser Upload File",
            "Reserved disabled file-upload contract. Public web upload is disabled by default.",
            input_schema={"target_hint": "string", "file_path": "string"},
            output_schema={"status": "blocked", "error_type": "TOOL_DISABLED"},
            permission="dangerous",
            risk_level="dangerous",
            can_mutate_page=True,
            public_web_allowed=False,
            enabled=False,
            exposure="disabled",
            public_web_exposure="hidden",
            local_fixture_exposure="hidden",
            real_llm_prompt_allowed=False,
            tags=["browser", "v2", "reserved", "upload", "disabled"],
        ),
        _browser_tool(
            "browser_download",
            "Browser Download",
            "Reserved disabled download contract. Downloads must use a controlled directory when enabled.",
            input_schema={"target_hint": "string optional", "url": "string optional"},
            output_schema={"status": "blocked", "error_type": "TOOL_DISABLED"},
            permission="dangerous",
            risk_level="dangerous",
            public_web_allowed=False,
            enabled=False,
            exposure="disabled",
            public_web_exposure="hidden",
            local_fixture_exposure="hidden",
            real_llm_prompt_allowed=False,
            tags=["browser", "v2", "reserved", "download", "disabled"],
        ),
        _browser_tool(
            "browser_drag",
            "Browser Drag",
            "Reserved disabled drag contract. Drag actions that mutate state require approval.",
            input_schema={"source_hint": "string", "target_hint": "string"},
            output_schema={"status": "blocked", "error_type": "TOOL_DISABLED"},
            permission="dangerous",
            risk_level="dangerous",
            can_mutate_page=True,
            public_web_allowed=False,
            enabled=False,
            exposure="disabled",
            public_web_exposure="hidden",
            local_fixture_exposure="hidden",
            real_llm_prompt_allowed=False,
            tags=["browser", "v2", "reserved", "drag", "disabled"],
        ),
    ]


def _browser_tool(
    tool_id: str,
    name: str,
    description: str,
    *,
    input_schema: dict[str, str],
    output_schema: dict[str, str],
    permission: str = "read_only",
    risk_level: str = "read_only",
    produces_evidence: bool = False,
    produces_screenshot: bool = False,
    can_mutate_page: bool = False,
    can_submit_external: bool = False,
    public_web_allowed: bool = True,
    local_fixture_allowed: bool = True,
    requires_session: bool = False,
    enabled: bool = True,
    compatibility_wrapper: bool = False,
    exposure: str = "core",
    public_web_exposure: str = "allowed",
    local_fixture_exposure: str = "allowed",
    real_llm_prompt_allowed: bool = True,
    tags: list[str] | None = None,
) -> ToolSpec:
    return ToolSpec(
        tool_id=tool_id,
        name=name,
        display_name=name,
        description=description,
        prompt=description,
        loading_mode="core",
        permission=permission,
        risk_level=risk_level,
        input_schema=input_schema,
        output_schema=output_schema,
        schema_summary=input_schema,
        requires_session=requires_session,
        produces_evidence=produces_evidence,
        produces_screenshot=produces_screenshot,
        can_mutate_page=can_mutate_page,
        can_submit_external=can_submit_external,
        public_web_allowed=public_web_allowed,
        local_fixture_allowed=local_fixture_allowed,
        enabled=enabled,
        compatibility_wrapper=compatibility_wrapper,
        exposure=exposure,
        public_web_exposure=public_web_exposure,
        local_fixture_exposure=local_fixture_exposure,
        real_llm_prompt_allowed=real_llm_prompt_allowed,
        tags=tags or ["browser", "v2"],
    )


def _all_terms_match(query: str, haystack: str) -> bool:
    terms = [term for term in query.split() if term]
    return bool(terms) and all(term in haystack for term in terms)
