# crewai-openterms

Permission-aware CrewAI tools for checking OpenTerms before an agent acts.

## Install

    pip install crewai-openterms

## Canonical actions

The package documents and checks only these OpenTerms permission keys:

- `read_content`
- `scrape_data`
- `api_access`
- `create_account`
- `make_purchases`
- `post_content`
- `allow_training`

## Default behavior

The guard is fail-closed by default.

| Result | Default behavior |
|---|---|
| `allowed` | Proceed |
| `denied` | Block |
| `null` | Block |
| `not_specified` | Block |
| `no_openterms_json` | Block |
| low confidence | Block or escalate |
| conditional result | Block or escalate unless conditions are verified |

During public alpha, many domains do not publish `openterms.json`. That is expected, but it blocks by default. To allow permissive fallback, pass `fail_closed=False` explicitly.

## OpenTermsCheckTool

Use this when an agent needs a structured permission check.

    from crewai import Agent, Task, Crew
    from crewai_openterms import OpenTermsCheckTool

    checker = OpenTermsCheckTool()

    researcher = Agent(
        role="Web Researcher",
        goal="Gather information from websites while respecting their terms",
        backstory=(
            "Before accessing a website, check its OpenTerms permissions "
            "using the openterms_check tool."
        ),
        tools=[checker],
    )

    task = Task(
        description="Check whether github.com allows read_content and scrape_data.",
        expected_output="A summary of permitted actions on github.com.",
        agent=researcher,
    )

    crew = Crew(agents=[researcher], tasks=[task])
    result = crew.kickoff()

## OpenTermsGuardTool

Use this when an agent should receive a go or no-go decision before acting.

    from crewai import Agent, Task, Crew
    from crewai_openterms import OpenTermsGuardTool

    guard = OpenTermsGuardTool(fail_closed=True)  # default

    researcher = Agent(
        role="Permission-aware researcher",
        goal="Use websites only when OpenTerms permits the intended action",
        backstory=(
            "Before taking action on a website, use openterms_guard. "
            "If it blocks or escalates, do not proceed."
        ),
        tools=[guard],
    )

    task = Task(
        description="Check whether example.com permits scrape_data before scraping.",
        expected_output="A go or no-go decision.",
        agent=researcher,
    )

    crew = Crew(agents=[researcher], tasks=[task])
    result = crew.kickoff()

Permissive fallback must be explicit:

    guard = OpenTermsGuardTool(fail_closed=False)

## OpenTermsGuardedTool

Use this pattern when OpenTerms should mechanically control whether a downstream tool executes.

    from crewai.tools import BaseTool
    from crewai_openterms import OpenTermsGuardedTool


    class FetchPageTool(BaseTool):
        name: str = "fetch_page"
        description: str = "Fetch a page after permission is granted."

        def _run(self, url: str, **kwargs):
            return f"Fetched {url}"


    fetch_page = FetchPageTool()

    guarded_fetch = OpenTermsGuardedTool(
        wrapped_tool=fetch_page,
        action="read_content",
        fail_closed=True,  # default
    )

    result = guarded_fetch._run(url="https://example.com/page")

`OpenTermsGuardedTool` blocks the wrapped tool by default unless the OpenTerms check returns allowed. `fail_closed=False` is the only permissive fallback.

## Discovery integration

When a domain's `openterms.json` includes a `discovery` block, the guard can surface MCP server URLs and API spec URLs in the allowed response.

Example:

    ALLOWED: acme-corp.com permits 'api_access'. You may proceed. MCP servers available: https://acme-corp.com/mcp/sse. API specs available: https://api.acme-corp.com/v1/openapi.json.

## Notes on openterms-py

The package uses `openterms-py` when installed through the SDK extra or development dependencies. If the SDK is unavailable, the client falls back to direct `openterms.json` fetch behavior.

## Links

- [OpenTerms Protocol](https://openterms.com)
- [Specification](https://openterms.com/docs)
- [JSON Schema](https://openterms.com/schema)
- [openterms-py SDK](https://github.com/jstibal/openterms-py)
- [LangChain integration](https://github.com/jstibal/langchain-openterms)
