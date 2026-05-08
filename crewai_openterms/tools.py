"""CrewAI tools for checking and enforcing OpenTerms permissions."""

import json
from typing import Any, Optional, Type
from urllib.parse import urlparse

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from crewai_openterms.client import OpenTermsClient


CANONICAL_ACTIONS = (
    "read_content",
    "scrape_data",
    "api_access",
    "create_account",
    "make_purchases",
    "post_content",
    "allow_training",
)


def _canonical_actions_text() -> str:
    return ", ".join(CANONICAL_ACTIONS)


class CheckInput(BaseModel):
    """Input for OpenTermsCheckTool."""

    domain: str = Field(description="The domain to check, for example github.com.")
    action: str = Field(
        description=(
            "The canonical permission key to check. Valid values: "
            + _canonical_actions_text()
            + "."
        )
    )


class GuardInput(BaseModel):
    """Input for OpenTermsGuardTool."""

    url: str = Field(description="The URL or domain the agent wants to interact with.")
    action: str = Field(
        default="read_content",
        description=(
            "The canonical permission key to check before proceeding. Valid values: "
            + _canonical_actions_text()
            + "."
        ),
    )


class GuardedInput(BaseModel):
    """Input for OpenTermsGuardedTool."""

    url: str = Field(description="The URL or domain passed to the wrapped tool.")


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc

    parsed = urlparse(f"https://{url}")
    return parsed.netloc or url


def _unsupported_action(domain: str, action: str) -> dict:
    return {
        "domain": domain,
        "action": action,
        "allowed": False,
        "reason": (
            f"Unsupported OpenTerms action '{action}'. "
            f"Valid actions are: {_canonical_actions_text()}."
        ),
    }


def _result_confidence(result: dict) -> Optional[str]:
    confidence = result.get("confidence")
    if isinstance(confidence, str):
        return confidence.lower()

    nested = result.get("result")
    if isinstance(nested, dict):
        nested_confidence = nested.get("confidence")
        if isinstance(nested_confidence, str):
            return nested_confidence.lower()

    return None


def _is_conditional(result: dict) -> bool:
    raw = result.get("raw")
    if isinstance(raw, dict):
        return True

    value = result.get("value")
    if isinstance(value, dict):
        return True

    nested = result.get("result")
    if isinstance(nested, dict) and isinstance(nested.get("value"), dict):
        return True

    reason = str(result.get("reason", "")).lower()
    return "condition" in reason or "conditions" in reason


def _decision(result: dict, fail_closed: bool = True) -> tuple[bool, str, str]:
    allowed = result.get("allowed")

    if result.get("action") not in CANONICAL_ACTIONS:
        return False, "BLOCKED", result.get("reason", "Unsupported OpenTerms action.")

    if _result_confidence(result) == "low":
        return (
            False,
            "ESCALATE",
            "OpenTerms returned low confidence. Block or escalate by default.",
        )

    if _is_conditional(result):
        return (
            False,
            "ESCALATE",
            "OpenTerms returned a conditional permission. Verify conditions before proceeding.",
        )

    if allowed is True:
        return True, "ALLOWED", result.get("reason", "Permission allowed.")

    if allowed is False:
        return False, "DENIED", result.get("reason", "Permission denied.")

    if fail_closed:
        return (
            False,
            "BLOCKED",
            result.get(
                "reason",
                "No explicit permission found. Fail-closed default blocks this action.",
            ),
        )

    return (
        True,
        "UNRESOLVED",
        result.get(
            "reason",
            "No explicit permission found. Permissive fallback was explicitly enabled.",
        ),
    )


class OpenTermsCheckTool(BaseTool):
    """Return a structured OpenTerms permission check for a domain and action."""

    name: str = "openterms_check"
    description: str = (
        "Check whether a canonical OpenTerms action is allowed for a domain. "
        "Valid actions are: "
        + _canonical_actions_text()
        + "."
    )
    args_schema: Type[BaseModel] = CheckInput
    client: Optional[Any] = None

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any):
        if "client" not in kwargs or kwargs["client"] is None:
            kwargs["client"] = OpenTermsClient()
        super().__init__(**kwargs)

    def _run(self, domain: str, action: str, **kwargs: Any) -> str:
        if action not in CANONICAL_ACTIONS:
            result = _unsupported_action(domain, action)
        else:
            result = self.client.check(domain, action)

        return json.dumps({"check": result}, indent=2)


class OpenTermsGuardTool(BaseTool):
    """Fail-closed OpenTerms guard that returns a go or no-go decision."""

    name: str = "openterms_guard"
    description: str = (
        "Before interacting with a website, use this tool to check whether the "
        "intended canonical OpenTerms action is permitted. Blocks by default on "
        "denied, unknown, not specified, missing openterms.json, conditional, or "
        "low-confidence results."
    )
    args_schema: Type[BaseModel] = GuardInput
    client: Optional[Any] = None
    fail_closed: bool = True

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any):
        if "strict" in kwargs and "fail_closed" not in kwargs:
            kwargs["fail_closed"] = kwargs.pop("strict")
        elif "strict" in kwargs:
            kwargs.pop("strict")

        if "client" not in kwargs or kwargs["client"] is None:
            kwargs["client"] = OpenTermsClient()

        super().__init__(**kwargs)

    def _run(self, url: str, action: str = "read_content", **kwargs: Any) -> str:
        domain = _extract_domain(url)

        if action not in CANONICAL_ACTIONS:
            result = _unsupported_action(domain, action)
        else:
            result = self.client.check(domain, action)

        permitted, label, reason = _decision(result, fail_closed=self.fail_closed)

        if not permitted:
            return (
                f"{label}: OpenTerms did not permit '{action}' on {domain}. "
                f"Reason: {reason} Do not proceed with this action."
            )

        if label == "UNRESOLVED":
            return (
                f"UNRESOLVED: No explicit OpenTerms permission for '{action}' on {domain}. "
                "Permissive fallback was explicitly enabled with fail_closed=False."
            )

        discovery = self.client.discover(domain)
        discovery_note = ""
        if discovery:
            mcp = discovery.get("mcp_servers", []) or []
            apis = discovery.get("api_specs", []) or []
            if mcp:
                urls = [server["url"] for server in mcp if "url" in server]
                if urls:
                    discovery_note += f" MCP servers available: {', '.join(urls)}."
            if apis:
                urls = [spec["url"] for spec in apis if "url" in spec]
                if urls:
                    discovery_note += f" API specs available: {', '.join(urls)}."

        return f"ALLOWED: {domain} permits '{action}'. You may proceed.{discovery_note}"


class OpenTermsGuardedTool(BaseTool):
    """Wrap a downstream CrewAI tool with an OpenTerms permission gate."""

    name: str = "openterms_guarded_tool"
    description: str = (
        "Run an OpenTerms permission check before executing a wrapped CrewAI tool. "
        "Blocks by default unless the check returns allowed."
    )
    args_schema: Type[BaseModel] = GuardedInput
    client: Optional[Any] = None
    wrapped_tool: Any = None
    action: str = "read_content"
    fail_closed: bool = True

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any):
        if "client" not in kwargs or kwargs["client"] is None:
            kwargs["client"] = OpenTermsClient()
        super().__init__(**kwargs)

    def _run(self, url: str, **kwargs: Any) -> str:
        domain = _extract_domain(url)

        if self.action not in CANONICAL_ACTIONS:
            result = _unsupported_action(domain, self.action)
        else:
            result = self.client.check(domain, self.action)

        permitted, label, reason = _decision(result, fail_closed=self.fail_closed)

        if not permitted:
            return (
                f"{label}: OpenTerms did not permit '{self.action}' on {domain}. "
                f"Reason: {reason} Wrapped tool was not executed."
            )

        if self.wrapped_tool is None:
            return (
                f"ALLOWED: {domain} permits '{self.action}'. "
                "No wrapped tool was configured."
            )

        if hasattr(self.wrapped_tool, "_run"):
            return self.wrapped_tool._run(url=url, **kwargs)

        if callable(self.wrapped_tool):
            return self.wrapped_tool(url=url, **kwargs)

        return "BLOCKED: Wrapped tool is not executable."
