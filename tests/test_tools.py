"""Tests for crewai-openterms integration."""

import json
from typing import Any

import pytest

from crewai_openterms.client import OpenTermsClient
from crewai_openterms.tools import OpenTermsCheckTool, OpenTermsGuardTool


SAMPLE_OPENTERMS = {
    "openterms_version": "0.3.0",
    "service": "example.com",
    "permissions": {
        "read_content": True,
        "scrape_data": False,
        "api_access": {
            "allowed": True,
            "requires_auth": True,
            "max_frequency": "1000/hour",
        },
    },
    "discovery": {
        "mcp_servers": [
            {
                "url": "https://example.com/mcp/sse",
                "transport": "sse",
                "description": "Order tools.",
            }
        ],
        "api_specs": [
            {
                "url": "https://api.example.com/v1/openapi.json",
                "type": "openapi_3",
                "description": "Public API.",
            }
        ],
    },
}


def mock_client(data=None):
    client = OpenTermsClient()
    if data is not None:
        client._cache["example.com"] = {"data": data, "fetched_at": 9999999999}
    return client


# --- CheckTool ---


class TestCheckTool:
    def test_allowed(self):
        tool = OpenTermsCheckTool(client=mock_client(SAMPLE_OPENTERMS))
        result = json.loads(tool._run(domain="example.com", action="read_content"))
        assert result["check"]["allowed"] is True
        assert "receipt" in result

    def test_denied(self):
        tool = OpenTermsCheckTool(client=mock_client(SAMPLE_OPENTERMS))
        result = json.loads(tool._run(domain="example.com", action="scrape_data"))
        assert result["check"]["allowed"] is False

    def test_nested_permission(self):
        tool = OpenTermsCheckTool(client=mock_client(SAMPLE_OPENTERMS))
        result = json.loads(tool._run(domain="example.com", action="api_access"))
        assert result["check"]["allowed"] is True

    def test_unspecified(self):
        tool = OpenTermsCheckTool(client=mock_client(SAMPLE_OPENTERMS))
        result = json.loads(tool._run(domain="example.com", action="make_purchases"))
        assert result["check"]["allowed"] is None

    def test_no_file(self):
        tool = OpenTermsCheckTool(client=mock_client(None))
        result = json.loads(tool._run(domain="example.com", action="read_content"))
        assert result["check"]["allowed"] is None
        assert "No openterms.json" in result["check"]["reason"]

    def test_receipt_has_hash(self):
        tool = OpenTermsCheckTool(client=mock_client(SAMPLE_OPENTERMS))
        result = json.loads(tool._run(domain="example.com", action="scrape_data"))
        assert result["receipt"]["openterms_hash"] != ""
        assert result["receipt"]["domain"] == "example.com"


# --- GuardTool ---


class TestGuardTool:
    def test_allowed_returns_proceed(self):
        tool = OpenTermsGuardTool(client=mock_client(SAMPLE_OPENTERMS))
        result = tool._run(url="https://example.com/page", action="read_content")
        assert "ALLOWED" in result
        assert "proceed" in result.lower()

    def test_allowed_includes_discovery(self):
        tool = OpenTermsGuardTool(client=mock_client(SAMPLE_OPENTERMS))
        result = tool._run(url="https://example.com/page", action="read_content")
        assert "mcp" in result.lower()
        assert "openapi" in result.lower()

    def test_denied_returns_stop(self):
        tool = OpenTermsGuardTool(client=mock_client(SAMPLE_OPENTERMS))
        result = tool._run(url="https://example.com/data", action="scrape_data")
        assert "DENIED" in result
        assert "Do NOT proceed" in result

    def test_no_file_permissive(self):
        tool = OpenTermsGuardTool(client=mock_client(None))
        result = tool._run(url="https://example.com/page", action="read_content")
        assert "PROCEED WITH CAUTION" in result

    def test_no_file_strict(self):
        tool = OpenTermsGuardTool(client=mock_client(None), strict=True)
        result = tool._run(url="https://example.com/page", action="read_content")
        assert "BLOCKED" in result

    def test_bare_domain(self):
        tool = OpenTermsGuardTool(client=mock_client(SAMPLE_OPENTERMS))
        result = tool._run(url="example.com", action="read_content")
        assert "ALLOWED" in result

    def test_default_action(self):
        tool = OpenTermsGuardTool(client=mock_client(SAMPLE_OPENTERMS))
        result = tool._run(url="https://example.com/page")
        assert "ALLOWED" in result

    def test_no_discovery_block(self):
        no_disc = {**SAMPLE_OPENTERMS}
        del no_disc["discovery"]
        tool = OpenTermsGuardTool(client=mock_client(no_disc))
        result = tool._run(url="https://example.com/page", action="read_content")
        assert "ALLOWED" in result
        assert "mcp" not in result.lower()
