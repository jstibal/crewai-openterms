# crewai-openterms

Permission-aware AI agents for CrewAI. Checks a domain's [openterms.json](https://openterms.com) before your agent acts, so it knows what it's allowed to do.

## Install

```bash
pip install crewai-openterms
```

## Two tools

### OpenTermsCheckTool

A tool the agent calls to check permissions and get a structured result.

```python
from crewai import Agent, Task, Crew
from crewai_openterms import OpenTermsCheckTool

checker = OpenTermsCheckTool()

researcher = Agent(
    role="Web Researcher",
    goal="Gather information from websites while respecting their terms",
    backstory=(
        "You are a thorough researcher. Before accessing any website, "
        "you always check its openterms.json permissions using the "
        "openterms_check tool."
    ),
    tools=[checker],
)

task = Task(
    description=(
        "Check whether github.com allows read_content and scrape_data. "
        "Report the results."
    ),
    expected_output="A summary of what actions are permitted on github.com.",
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[task])
result = crew.kickoff()
```

### OpenTermsGuardTool

A gate that returns clear go/no-go instructions. When a domain allows the action, the response also includes any discovered MCP servers and API specs from the site's `discovery` block.

```python
from crewai import Agent, Task, Crew
from crewai_tools import ScrapeWebsiteTool
from crewai_openterms import OpenTermsGuardTool

guard = OpenTermsGuardTool()
scraper = ScrapeWebsiteTool()

researcher = Agent(
    role="Compliant Web Scraper",
    goal="Scrape websites for data, but only when permitted",
    backstory=(
        "Before scraping any site, you MUST use openterms_guard to check "
        "whether scraping is allowed. If the tool returns DENIED, do not "
        "proceed. If it returns ALLOWED, you may use the scrape tool."
    ),
    tools=[guard, scraper],
)

task = Task(
    description=(
        "Scrape pricing information from example.com. "
        "First check if scraping is permitted."
    ),
    expected_output="Pricing data or an explanation of why it could not be retrieved.",
    agent=researcher,
)

crew = Crew(agents=[researcher], tasks=[task])
result = crew.kickoff()
```

## Strict mode

By default, if a domain has no openterms.json, the guard returns "PROCEED WITH CAUTION." In strict mode, it blocks instead:

```python
guard = OpenTermsGuardTool(strict=True)
```

## Discovery integration

When a domain's openterms.json includes a `discovery` block (v0.3.0), the guard tool surfaces MCP server URLs and API spec URLs in its response. This lets the agent know not just whether it can interact, but how:

```
ALLOWED: acme-corp.com permits 'api_access'. You may proceed.
MCP servers available: https://acme-corp.com/mcp/sse.
API specs available: https://api.acme-corp.com/v1/openapi.json.
```

## Multi-agent example

```python
from crewai import Agent, Task, Crew
from crewai_openterms import OpenTermsCheckTool, OpenTermsGuardTool

# Compliance agent checks permissions first
compliance = Agent(
    role="Compliance Officer",
    goal="Verify that all web interactions are permitted",
    tools=[OpenTermsCheckTool()],
    backstory="You check openterms.json for every domain before any agent acts.",
)

# Research agent does the actual work
researcher = Agent(
    role="Researcher",
    goal="Gather data from permitted sources",
    tools=[OpenTermsGuardTool()],
    backstory=(
        "You research topics online. Always use openterms_guard before "
        "accessing any site. If denied, skip that site and try another."
    ),
)

check_task = Task(
    description="Check permissions for github.com, stripe.com, and reddit.com for read_content and scrape_data.",
    expected_output="Permission matrix for all three domains.",
    agent=compliance,
)

research_task = Task(
    description="Using only permitted domains, gather information about API pricing trends.",
    expected_output="Summary of API pricing trends from permitted sources.",
    agent=researcher,
    context=[check_task],
)

crew = Crew(
    agents=[compliance, researcher],
    tasks=[check_task, research_task],
)

result = crew.kickoff()
```

## Links

- [OpenTerms Protocol](https://openterms.com)
- [Specification](https://openterms.com/docs)
- [JSON Schema](https://openterms.com/schema)
- [openterms-py SDK](https://github.com/jstibal/openterms-py)
- [LangChain integration](https://github.com/jstibal/langchain-openterms)
