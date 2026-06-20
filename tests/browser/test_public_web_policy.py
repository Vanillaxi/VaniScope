from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.browser.public_web import (
    PublicWebPolicy,
    PublicWebPolicyError,
    PublicWebRuntimeConfig,
    classify_url,
    load_public_web_config,
    load_runtime_config,
)
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.tools.gateway import (
    BrowserToolProvider,
    ToolGateway,
    ToolGatewayAuditStore,
    ToolInvocationRequest,
)


def test_public_web_policy_allows_local_fixture_and_localhost_by_default() -> None:
    policy = PublicWebPolicy()

    assert policy.check("file:///tmp/basic.html").decision == "allow"
    assert policy.check("tests/fixtures/mock_site/basic.html").decision == "allow"
    assert policy.check("http://localhost:8080").decision == "allow"
    assert policy.check("http://127.0.0.1:8080").decision == "allow"


def test_public_web_policy_blocks_public_private_and_unsupported_urls() -> None:
    policy = PublicWebPolicy()

    assert (
        policy.check("https://example.com").decision
        == "block_public_network_disabled"
    )
    assert policy.check("http://10.0.0.5").decision == "block_private_network"
    assert policy.check("http://printer.local").decision == "block_private_network"
    assert policy.check("javascript:alert(1)").decision == "block_unsupported_scheme"


def test_public_web_policy_requires_allowed_domain_when_enabled() -> None:
    policy = PublicWebPolicy(
        PublicWebRuntimeConfig(
            mode="public_safe",
            public_network_enabled=True,
            allowed_domains=["example.com"],
            max_pages_per_task=2,
        )
    )

    allowed = policy.check("https://docs.example.com/path")
    blocked = policy.check("https://github.com/openai")

    assert allowed.decision == "allow"
    assert allowed.matched_domain == "example.com"
    assert blocked.decision == "block_domain_not_allowed"


def test_public_open_allows_public_http_without_domain_match() -> None:
    policy = PublicWebPolicy(
        PublicWebRuntimeConfig(
            mode="public_open",
            public_network_enabled=True,
            allowed_domains=["*"],
        )
    )

    allowed = policy.check("https://example.com")
    private = policy.check("http://172.16.0.10")

    assert allowed.decision == "allow"
    assert allowed.matched_domain == "*"
    assert private.decision == "block_private_network"


def test_public_web_policy_enforces_max_pages_per_task() -> None:
    policy = PublicWebPolicy(
        PublicWebRuntimeConfig(
            mode="public_safe",
            public_network_enabled=True,
            allowed_domains=["example.com"],
            max_pages_per_task=1,
        )
    )

    decision = policy.check("https://example.com/next", pages_opened=1)

    assert decision.decision == "block_max_pages_per_task"


def test_public_web_config_loads_from_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime.local.toml"
    config_path.write_text(
        "\n".join(
            [
                "[web]",
                'mode = "public_safe"',
                "public_network_enabled = true",
                'allowed_domains = ["example.com"]',
                "max_pages_per_task = 4",
                "request_delay_ms = 10",
                "navigation_timeout_ms = 9000",
            ]
        ),
        encoding="utf-8",
    )

    config = load_public_web_config(config_path)

    assert config.mode == "public_safe"
    assert config.public_network_enabled is True
    assert config.allowed_domains == ["example.com"]
    assert config.max_pages_per_task == 4
    assert config.runtime_mode == "public_safe"


def test_runtime_config_loader_merges_example_and_local_override(
    tmp_path: Path,
) -> None:
    example_path = tmp_path / "runtime.example.toml"
    local_path = tmp_path / "runtime.local.toml"
    example_path.write_text(
        "\n".join(
            [
                "[web]",
                'mode = "local"',
                "public_network_enabled = false",
                "allowed_domains = []",
                "max_pages_per_task = 3",
                "request_delay_ms = 250",
                "navigation_timeout_ms = 8000",
            ]
        ),
        encoding="utf-8",
    )
    local_path.write_text(
        "\n".join(
            [
                "[web]",
                'mode = "public_safe"',
                "public_network_enabled = true",
                'allowed_domains = ["github.com"]',
                "navigation_timeout_ms = 12000",
            ]
        ),
        encoding="utf-8",
    )

    config = load_runtime_config(
        example_path=example_path,
        local_path=local_path,
    )
    decision = PublicWebPolicy(config).check("https://github.com/Vanillaxi")

    assert config.mode == "public_safe"
    assert config.public_network_enabled is True
    assert config.allowed_domains == ["github.com"]
    assert config.max_pages_per_task == 3
    assert config.navigation_timeout_ms == 12000
    assert config.source_path == str(local_path)
    assert decision.decision == "allow"
    assert decision.matched_domain == "github.com"


@pytest.mark.asyncio
async def test_browser_open_blocks_public_url_before_page_start(tmp_path: Path) -> None:
    recorder = TraceRecorder(run_dir=tmp_path / "run", run_id="public_block")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)

    with pytest.raises(PublicWebPolicyError) as exc_info:
        await runtime.open_observe("https://example.com")

    assert exc_info.value.decision.decision == "block_public_network_disabled"
    assert runtime.last_observation is not None
    trace_rows = [
        json.loads(line)
        for line in recorder.trace_path.read_text(encoding="utf-8").splitlines()
    ]
    assert trace_rows[-1]["status"] == "blocked"
    assert trace_rows[-1]["error_type"] == "PUBLIC_WEB_BLOCKED"
    assert trace_rows[-1]["observation"]["title"] == "Blocked by public web policy"
    assert trace_rows[-1]["observation"]["metadata"]["public_web_policy"]["decision"] == (
        "block_public_network_disabled"
    )


@pytest.mark.asyncio
async def test_tool_gateway_browser_open_returns_structured_public_web_block(
    tmp_path: Path,
) -> None:
    recorder = TraceRecorder(run_dir=tmp_path / "run", run_id="gateway_public_block")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    gateway = ToolGateway(
        providers=[BrowserToolProvider(runtime)],
        audit_store=ToolGatewayAuditStore(tmp_path / "tool_audit.jsonl"),
    )

    result = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="browser_open_observe",
            arguments={"url": "https://example.com"},
            run_dir=str(tmp_path / "run"),
        )
    )

    assert result.status == "blocked"
    assert result.decision == "blocked"
    assert result.error_type == "PUBLIC_WEB_BLOCKED"
    assert result.output["public_web_policy"]["decision"] == (
        "block_public_network_disabled"
    )
    audit_rows = [
        json.loads(line)
        for line in (tmp_path / "tool_audit.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert audit_rows[-1]["decision"] == "blocked"


def test_classify_url_keeps_localhost_out_of_private_network() -> None:
    assert classify_url("http://[::1]:8080").kind == "localhost"
    assert classify_url("http://192.168.1.10").kind == "private_network"
