"""CrewAI integration for the OpenTerms protocol.

Provides permission-aware tools for CrewAI agents that check
openterms.json before interacting with domains.

Two tools:

1. OpenTermsCheckTool — agent calls this to check what it's allowed to do
2. OpenTermsGuardTool — wraps another tool with a permission gate
"""

from crewai_openterms.tools import OpenTermsCheckTool, OpenTermsGuardTool
from crewai_openterms.client import OpenTermsClient

__all__ = [
    "OpenTermsCheckTool",
    "OpenTermsGuardTool",
    "OpenTermsClient",
]
