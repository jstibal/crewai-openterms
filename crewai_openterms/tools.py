"""CrewAI tools for checking and enforcing openterms.json permissions."""

import json
from typing import Any, Optional, Type
from urllib.parse import urlparse

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from crewai_openterms.client import OpenTermsClient


# --- Input schemas ---


class CheckInput(BaseModel):
    """Input for OpenTermsCheckTool."""
    domain: str = Field(description="The domain to check (e.g., 'github.com').")
    action: str = Field(
        description=(
            "The permission to check. Common values: read_content, "
            "scrape_data, api_access, create_account, make_purchases, "
            "post_content, execute_code."
        )
    )


class GuardInput(BaseModel):
    """Input for OpenTermsGuardTool."""
    url: str = Field(description="The URL or domain the agent wants to interact with.")
    action: str = Field(
        default="read_content",
        description="The permission to check before proceeding.",
    )


# --- Tools ---


class OpenTermsCheckTool(BaseTool):
    """Check what an AI agent is permitted to do on a website.

    Returns a JSON result with the permission decision, reason,
    and an ORS receipt for audit logging.

    Usage in a CrewAI agent:
        agent = Agent(
            role="researcher",
            tools=[OpenTermsCheckTool()],
            ...
        )
    """

    name: str = "openterms_check"
    description: str = (
        "Check what actions are permitted on a website by reading its "
        "openterms.json file. Input requires a domain (e.g., 'github.com') "
        "and an action (e.g., 'read_content', 'scrape_data', 'api_access'). "
        "Returns whether the action is allowed, denied, or unspecified, "
        "plus a receipt for audit purposes."
    )
    args_schema: Type[BaseModel] = CheckInput
    client: Optional[OpenTermsClient] = None

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any):
        if "client" not in kwargs or kwargs["client"] is None:
            kwargs["client"] = OpenTermsClient()
        super().__init__(**kwargs)

    def _run(self, domain: str, action: str, **kwargs: Any) -> str:
        result = self.client.check(domain, action)
        receipt = self.client.receipt(domain, action, result)
        return json.dumps({"check": result, "receipt": receipt}, indent=2)


class OpenTermsGuardTool(BaseTool):
    """Check permissions before interacting with a URL.

    Unlike OpenTermsCheckTool (which just reports), this tool returns
    a clear go/no-go decision with instructions for the agent.

    If the domain denies the action, the agent gets a message telling
    it to stop. If allowed or unspecified, the agent gets clearance
    to proceed.

    Usage:
        agent = Agent(
            role="web_researcher",
            tools=[OpenTermsGuardTool(), ScrapeWebsiteTool()],
            backstory="Always use openterms_guard before scraping any site.",
            ...
        )
    """

    name: str = "openterms_guard"
    description: str = (
        "Before interacting with any website, use this tool to check "
        "whether the action is permitted. Input: a URL and the intended "
        "action (default: 'read_content'). If the site denies the action, "
        "you MUST stop and not proceed with that action on that domain."
    )
    args_schema: Type[BaseModel] = GuardInput
    client: Optional[OpenTermsClient] = None
    strict: bool = False

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, **kwargs: Any):
        if "client" not in kwargs or kwargs["client"] is None:
            kwargs["client"] = OpenTermsClient()
        super().__init__(**kwargs)

    def _extract_domain(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc
        # Treat as bare domain
        parsed = urlparse(f"https://{url}")
        return parsed.netloc or url

    def _run(self, url: str, action: str = "read_content", **kwargs: Any) -> str:
        domain = self._extract_domain(url)
        result = self.client.check(domain, action)

        if result["allowed"] is False:
            return (
                f"DENIED: {domain} does not permit '{action}'. "
                f"Reason: {result['reason']} "
                f"Do NOT proceed with this action on {domain}."
            )

        if result["allowed"] is None and self.strict:
            return (
                f"BLOCKED: No openterms.json found for {domain} and strict "
                f"mode is enabled. Cannot verify permission for '{action}'. "
                f"Do NOT proceed."
            )

        if result["allowed"] is None:
            return (
                f"PROCEED WITH CAUTION: No explicit permission for '{action}' "
                f"found on {domain}. No openterms.json exists or the action "
                f"is not addressed. Proceed at your own discretion."
            )

        # Allowed
        discovery = self.client.discover(domain)
        discovery_note = ""
        if discovery:
            mcp = discovery.get("mcp_servers", [])
            apis = discovery.get("api_specs", [])
            if mcp:
                urls = [s["url"] for s in mcp]
                discovery_note += f" MCP servers available: {', '.join(urls)}."
            if apis:
                urls = [s["url"] for s in apis]
                discovery_note += f" API specs available: {', '.join(urls)}."

        return (
            f"ALLOWED: {domain} permits '{action}'. "
            f"You may proceed.{discovery_note}"
        )
