from __future__ import annotations

from typing import Any

from webscoper.workflows.langgraph_backend.state_io import TERMINAL_GRAPH_STATUSES
from webscoper.workflows.state import VaniScopeGraphState


def build_langgraph_workflow(*, nodes: Any, checkpointer: Any | None = None):
    try:
        from langgraph.graph import END, START, StateGraph
        from langgraph.checkpoint.memory import InMemorySaver
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph workflow requested but langgraph is not installed"
        ) from exc

    graph = StateGraph(VaniScopeGraphState)
    graph.add_node("init_task", nodes.init_task)
    graph.add_node("build_prompt", nodes.build_prompt)
    graph.add_node("plan_task", nodes.plan_task)
    graph.add_node("validate_plan", nodes.validate_plan)
    graph.add_node("execute_plan", nodes.execute_plan)
    graph.add_node("build_report", nodes.build_report)
    graph.add_node("review_report", nodes.review_report)
    graph.add_node("compact_context", nodes.compact_context)
    graph.add_node("maybe_revise", nodes.maybe_revise)
    graph.add_node("finalize_task", nodes.finalize_task)

    graph.add_edge(START, "init_task")
    graph.add_conditional_edges(
        "init_task",
        _route_to("build_prompt"),
        ["build_prompt", "finalize_task"],
    )
    graph.add_conditional_edges(
        "build_prompt",
        _route_to("plan_task"),
        ["plan_task", "finalize_task"],
    )
    graph.add_conditional_edges(
        "plan_task",
        _route_to("validate_plan"),
        ["validate_plan", "finalize_task"],
    )
    graph.add_conditional_edges(
        "validate_plan",
        _route_to("execute_plan"),
        ["execute_plan", "finalize_task"],
    )
    graph.add_conditional_edges(
        "execute_plan",
        _route_to("build_report"),
        ["build_report", "finalize_task"],
    )
    graph.add_conditional_edges(
        "build_report",
        _route_to("review_report"),
        ["review_report", "finalize_task"],
    )
    graph.add_conditional_edges(
        "review_report",
        _route_to("compact_context"),
        ["compact_context", "finalize_task"],
    )
    graph.add_conditional_edges(
        "compact_context",
        _route_to("maybe_revise"),
        ["maybe_revise", "finalize_task"],
    )
    graph.add_edge("maybe_revise", "finalize_task")
    graph.add_edge("finalize_task", END)
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _route_to(next_node: str):
    def route(state: VaniScopeGraphState) -> str:
        if state.get("status") in TERMINAL_GRAPH_STATUSES:
            return "finalize_task"
        return next_node

    return route
