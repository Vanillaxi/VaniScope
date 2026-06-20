from __future__ import annotations

import ipaddress
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs/runtime.example.toml"
DEFAULT_RUNTIME_LOCAL_CONFIG_PATH = PROJECT_ROOT / "configs/runtime.local.toml"
DEFAULT_RUNTIME_CONFIG_PATH = DEFAULT_RUNTIME_LOCAL_CONFIG_PATH
DEFAULT_PUBLIC_WEB_CONFIG_PATH = DEFAULT_RUNTIME_LOCAL_CONFIG_PATH

WebRuntimeMode = Literal["local", "public_safe", "public_open"]


class PublicWebRuntimeConfig(BaseModel):
    mode: WebRuntimeMode = "local"
    public_network_enabled: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    max_pages_per_task: int = Field(default=3, ge=1)
    request_delay_ms: int = Field(default=250, ge=0)
    navigation_timeout_ms: int = Field(default=8000, ge=1000)
    source_path: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def runtime_mode(self) -> str:
        return self.mode

    @model_validator(mode="after")
    def normalize_warnings(self) -> PublicWebRuntimeConfig:
        warnings = list(self.warnings)
        if self.mode == "public_open":
            warning = "public_open allows any public HTTP/HTTPS domain."
            if warning not in warnings:
                warnings.append(warning)
        self.warnings = warnings
        return self

    def diagnostics_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "public_network_enabled": self.public_network_enabled,
            "allowed_domains": self.allowed_domains,
            "max_pages_per_task": self.max_pages_per_task,
            "request_delay_ms": self.request_delay_ms,
            "navigation_timeout_ms": self.navigation_timeout_ms,
            "source_path": self.source_path,
            "warnings": self.warnings,
        }


class PublicWebDecision(BaseModel):
    allow: bool
    decision: str
    reason: str
    url: str
    url_classification: str
    host: str | None = None
    matched_domain: str | None = None


@dataclass
class PublicWebPolicyError(RuntimeError):
    decision: PublicWebDecision
    observation: Any | None = None

    def __str__(self) -> str:
        return self.decision.reason


class PublicWebPolicy:
    def __init__(self, config: PublicWebRuntimeConfig | None = None) -> None:
        self.config = config or PublicWebRuntimeConfig()

    def check(self, url: str, *, pages_opened: int = 0) -> PublicWebDecision:
        classification = classify_url(url)
        host = classification.host
        if classification.kind in {"local_fixture", "localhost"}:
            return _allow(url, classification.kind, host=host)

        if classification.kind == "unsupported_scheme":
            return _block(
                "block_unsupported_scheme",
                f"Unsupported URL scheme for browser_open_observe: {classification.scheme or 'none'}",
                url,
                classification.kind,
                host=host,
            )

        if classification.kind == "private_network":
            return _block(
                "block_private_network",
                f"Blocked private or internal network URL: {url}",
                url,
                classification.kind,
                host=host,
            )

        if classification.kind == "public_http":
            if self.config.mode == "local" or not self.config.public_network_enabled:
                return _block(
                    "block_public_network_disabled",
                    "Public web access is disabled by runtime configuration.",
                    url,
                    classification.kind,
                    host=host,
                )
            matched_domain = (
                "*"
                if self.config.mode == "public_open"
                else _matched_allowed_domain(host, self.config.allowed_domains)
            )
            if matched_domain is None:
                return _block(
                    "block_domain_not_allowed",
                    f"Public domain is not in allowed_domains: {host or 'unknown'}",
                    url,
                    classification.kind,
                    host=host,
                )
            if pages_opened >= self.config.max_pages_per_task:
                return _block(
                    "block_max_pages_per_task",
                    (
                        "Public page limit reached for this task: "
                        f"{self.config.max_pages_per_task}"
                    ),
                    url,
                    classification.kind,
                    host=host,
                    matched_domain=matched_domain,
                )
            return _allow(
                url,
                classification.kind,
                host=host,
                matched_domain=matched_domain,
            )

        return _block(
            "block_unsupported_scheme",
            f"Unsupported URL for browser_open_observe: {url}",
            url,
            classification.kind,
            host=host,
        )


@dataclass(frozen=True)
class UrlClassification:
    kind: str
    scheme: str | None = None
    host: str | None = None


def load_runtime_config(
    *,
    example_path: str | Path | None = None,
    local_path: str | Path | None = None,
) -> PublicWebRuntimeConfig:
    example_config_path = (
        Path(example_path) if example_path is not None else DEFAULT_RUNTIME_EXAMPLE_CONFIG_PATH
    )
    local_config_path = (
        Path(local_path) if local_path is not None else DEFAULT_RUNTIME_LOCAL_CONFIG_PATH
    )
    payload: dict[str, Any] = {}
    source_path: Path | None = None

    if example_config_path.exists():
        payload.update(_read_web_payload(example_config_path))
        source_path = example_config_path
    if local_config_path.exists():
        payload.update(_read_web_payload(local_config_path))
        source_path = local_config_path

    config = PublicWebRuntimeConfig.model_validate(payload)
    return config.model_copy(
        update={"source_path": _display_path(source_path) if source_path is not None else None}
    )


def load_public_web_config(path: str | Path | None = None) -> PublicWebRuntimeConfig:
    return load_runtime_config(local_path=path)


def _read_web_payload(path: Path) -> dict[str, Any]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    if "web" in payload and isinstance(payload["web"], dict):
        return dict(payload["web"])
    if "public_web" in payload and isinstance(payload["public_web"], dict):
        return dict(payload["public_web"])
    return dict(payload)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def classify_url(url: str) -> UrlClassification:
    value = url.strip()
    if not value:
        return UrlClassification(kind="unsupported_scheme")
    if "://" not in value:
        parsed_without_slashes = urlparse(value)
        if (
            parsed_without_slashes.scheme
            and len(parsed_without_slashes.scheme) > 1
            and not value.startswith(("/", "./", "../"))
        ):
            return UrlClassification(
                kind="unsupported_scheme",
                scheme=parsed_without_slashes.scheme.lower(),
            )
        return UrlClassification(kind="local_fixture")

    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme == "file":
        return UrlClassification(kind="local_fixture", scheme=scheme)
    if scheme not in {"http", "https"}:
        return UrlClassification(kind="unsupported_scheme", scheme=scheme)

    host = _normalize_host(parsed.hostname)
    if _is_localhost(host):
        return UrlClassification(kind="localhost", scheme=scheme, host=host)
    if _is_private_or_internal_host(host):
        return UrlClassification(kind="private_network", scheme=scheme, host=host)
    return UrlClassification(kind="public_http", scheme=scheme, host=host)


def _allow(
    url: str,
    classification: str,
    *,
    host: str | None = None,
    matched_domain: str | None = None,
) -> PublicWebDecision:
    return PublicWebDecision(
        allow=True,
        decision="allow",
        reason="URL is allowed by public web policy.",
        url=url,
        url_classification=classification,
        host=host,
        matched_domain=matched_domain,
    )


def _block(
    decision: str,
    reason: str,
    url: str,
    classification: str,
    *,
    host: str | None = None,
    matched_domain: str | None = None,
) -> PublicWebDecision:
    return PublicWebDecision(
        allow=False,
        decision=decision,
        reason=reason,
        url=url,
        url_classification=classification,
        host=host,
        matched_domain=matched_domain,
    )


def _normalize_host(host: str | None) -> str | None:
    if host is None:
        return None
    return host.strip("[]").strip(".").lower()


def _is_localhost(host: str | None) -> bool:
    if host is None:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _is_private_or_internal_host(host: str | None) -> bool:
    if host is None:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return (
            "." not in host
            or host.endswith(".local")
            or host.endswith(".lan")
            or host.endswith(".home")
            or host.endswith(".corp")
            or host.endswith(".internal")
        )
    return (
        address.is_private
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        or address.is_multicast
    )


def _matched_allowed_domain(host: str | None, allowed_domains: list[str]) -> str | None:
    if host is None:
        return None
    normalized_host = host.strip(".").lower()
    for domain in allowed_domains:
        normalized_domain = str(domain).strip().strip(".").lower()
        if not normalized_domain:
            continue
        if normalized_host == normalized_domain or normalized_host.endswith(
            f".{normalized_domain}"
        ):
            return normalized_domain
    return None
