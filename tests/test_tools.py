"""Tests for crewai-openterms integration."""

import json

from crewai.tools import BaseTool

from crewai_openterms.tools import (
    CANONICAL_ACTIONS,
    OpenTermsCheckTool,
    OpenTermsGuardTool,
    OpenTermsGuardedTool,
)


class FakeClient:
    def __init__(self, responses=None, discovery=None):
        self.responses = responses or {}
        self.discovery_response = discovery

    def check(self, domain, action):
        payload = dict(
            self.responses.get(
                action,
                {
                    "domain": domain,
                    "action": action,
                    "allowed": None,
                    "reason": "No openterms.json found.",
                },
            )
        )
        payload.setdefault("domain", domain)
        payload.setdefault("action", action)
        return payload

    def discover(self, domain):
        return self.discovery_response


class DummyWrappedTool(BaseTool):
    name: str = "dummy_wrapped_tool"
    description: str = "Dummy wrapped tool for tests."
    called: bool = False

    def _run(self, url: str, **kwargs):
        self.called = True
        return f"WRAPPED EXECUTED: {url}"


DISCOVERY = {
    "mcp_servers": [{"url": "https://example.com/mcp/sse"}],
    "api_specs": [{"url": "https://api.example.com/v1/openapi.json"}],
}


def default_client(discovery=DISCOVERY):
    return FakeClient(
        responses={
            "read_content": {"allowed": True, "reason": "Permission allowed."},
            "scrape_data": {"allowed": False, "reason": "Permission denied."},
            "api_access": {"allowed": True, "reason": "Permission allowed."},
            "create_account": {"allowed": None, "reason": "Permission not specified."},
            "make_purchases": {"allowed": False, "reason": "Permission denied."},
            "post_content": {"allowed": True, "reason": "Permission allowed."},
            "allow_training": {"allowed": False, "reason": "Permission denied."},
        },
        discovery=discovery,
    )


def test_check_allowed():
    tool = OpenTermsCheckTool(client=default_client())
    result = json.loads(tool._run(domain="example.com", action="read_content"))
    assert result["check"]["allowed"] is True


def test_check_denied():
    tool = OpenTermsCheckTool(client=default_client())
    result = json.loads(tool._run(domain="example.com", action="scrape_data"))
    assert result["check"]["allowed"] is False


def test_check_unspecified():
    tool = OpenTermsCheckTool(client=default_client())
    result = json.loads(tool._run(domain="example.com", action="create_account"))
    assert result["check"]["allowed"] is None


def test_check_no_file():
    tool = OpenTermsCheckTool(client=FakeClient())
    result = json.loads(tool._run(domain="example.com", action="read_content"))
    assert result["check"]["allowed"] is None


def test_only_canonical_actions_are_documented():
    assert set(CANONICAL_ACTIONS) == {
        "read_content",
        "scrape_data",
        "api_access",
        "create_account",
        "make_purchases",
        "post_content",
        "allow_training",
    }


def test_guard_allowed_returns_proceed():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "ALLOWED" in result


def test_guard_allowed_includes_discovery():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "mcp" in result.lower()
    assert "api specs" in result.lower()


def test_guard_denied_returns_stop():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="https://example.com/data", action="scrape_data")
    assert "DENIED" in result
    assert "Do not proceed" in result


def test_guard_no_file_blocks_by_default():
    tool = OpenTermsGuardTool(client=FakeClient())
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "BLOCKED" in result


def test_guard_no_file_permissive_requires_explicit_opt_in():
    tool = OpenTermsGuardTool(client=FakeClient(), fail_closed=False)
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "UNRESOLVED" in result
    assert "fail_closed=False" in result


def test_guard_not_specified_blocks_by_default():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="https://example.com/page", action="create_account")
    assert "BLOCKED" in result


def test_guard_low_confidence_escalates():
    client = FakeClient(
        responses={
            "read_content": {
                "allowed": True,
                "confidence": "low",
                "reason": "Low confidence.",
            }
        }
    )
    tool = OpenTermsGuardTool(client=client)
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "ESCALATE" in result


def test_guard_conditional_escalates():
    client = FakeClient(
        responses={
            "post_content": {
                "allowed": True,
                "raw": {"allowed": True, "conditions": "Only after consent."},
                "reason": "Permission allowed with conditions.",
            }
        }
    )
    tool = OpenTermsGuardTool(client=client)
    result = tool._run(url="https://example.com/page", action="post_content")
    assert "ESCALATE" in result


def test_guard_bare_domain():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="example.com", action="read_content")
    assert "ALLOWED" in result


def test_guard_default_action():
    tool = OpenTermsGuardTool(client=default_client())
    result = tool._run(url="https://example.com/page")
    assert "ALLOWED" in result


def test_guard_no_discovery_block():
    tool = OpenTermsGuardTool(client=default_client(discovery=None))
    result = tool._run(url="https://example.com/page", action="read_content")
    assert "ALLOWED" in result
    assert "mcp" not in result.lower()


def test_guarded_wrapper_blocks_downstream_tool_when_denied():
    wrapped = DummyWrappedTool()
    tool = OpenTermsGuardedTool(
        client=default_client(), wrapped_tool=wrapped, action="scrape_data"
    )
    result = tool._run(url="https://example.com/data")
    assert "DENIED" in result
    assert wrapped.called is False


def test_guarded_wrapper_runs_downstream_tool_when_allowed():
    wrapped = DummyWrappedTool()
    tool = OpenTermsGuardedTool(
        client=default_client(), wrapped_tool=wrapped, action="read_content"
    )
    result = tool._run(url="https://example.com/page")
    assert "WRAPPED EXECUTED" in result
    assert wrapped.called is True


def test_guarded_wrapper_blocks_missing_file_by_default():
    wrapped = DummyWrappedTool()
    tool = OpenTermsGuardedTool(
        client=FakeClient(), wrapped_tool=wrapped, action="read_content"
    )
    result = tool._run(url="https://example.com/page")
    assert "BLOCKED" in result
    assert wrapped.called is False


def test_guarded_wrapper_permissive_mode_is_explicit():
    wrapped = DummyWrappedTool()
    tool = OpenTermsGuardedTool(
        client=FakeClient(),
        wrapped_tool=wrapped,
        action="read_content",
        fail_closed=False,
    )
    result = tool._run(url="https://example.com/page")
    assert "WRAPPED EXECUTED" in result
    assert wrapped.called is True
