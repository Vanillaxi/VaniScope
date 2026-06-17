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

    registry.register(
        ToolSpec(
            tool_id="browser_open_observe",
            name="Browser Open Observe",
            description="Open a public webpage and return structured observation.",
            prompt=(
                "Use this tool to open a public URL or local mock page and collect "
                "title, visible text summary, interactive elements, risk signals, and screenshot evidence."
            ),
            loading_mode="core",
            risk_level="read_only",
            tags=["browser", "open", "observe", "page"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="browser_click_intent",
            name="Browser Click Intent",
            description=(
                "Click a visible page element by natural language target hint and verify expected effect."
            ),
            prompt=(
                "Use this tool only for read-only click interactions on visible, enabled controls. "
                "Resolve the target from a natural language hint, click it, verify the expected effect, "
                "and capture a final observation."
            ),
            loading_mode="core",
            risk_level="read_only",
            tags=["browser", "click", "intent", "effect"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="browser_extract",
            name="Browser Extract",
            description="Extract visible structured information from the current public webpage.",
            prompt=(
                "Use this tool to summarize or structure information that is visibly present on the page. "
                "Do not infer unsupported facts and keep source URL context with extracted evidence."
            ),
            loading_mode="core",
            risk_level="read_only",
            tags=["browser", "extract", "visible", "structured"],
        )
    )
    registry.register(
        ToolSpec(
            tool_id="finish_task",
            name="Finish Task",
            description="Mark the current browser task complete and return final summary metadata.",
            prompt=(
                "Use this tool after required browser actions and extraction are complete. "
                "It records a final task summary without performing additional browser interaction."
            ),
            loading_mode="core",
            risk_level="read_only",
            tags=["finish", "task", "summary"],
        )
    )

    registry.register(
        ToolSpec(
            tool_id="web_search",
            name="Web Search",
            description="Search public web pages for relevant sources.",
            prompt="Search public web pages for relevant sources.",
            loading_mode="lazy",
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
            tags=["table", "extract", "html", "structured"],
        )
    )

    return registry


def _all_terms_match(query: str, haystack: str) -> bool:
    terms = [term for term in query.split() if term]
    return bool(terms) and all(term in haystack for term in terms)
