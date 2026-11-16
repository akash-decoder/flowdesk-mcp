from typing import Any

from mcp.server.fastmcp import FastMCP

from . import engine

server = FastMCP("Flowdesk")


@server.tool()
def list_workflows() -> list[dict]:
    """List saved workflows, ordered steps, IDs and current revisions."""
    return engine.workflows()


@server.tool()
def create_workflow(definition: engine.Workflow) -> dict:
    """Create a workflow with filter, set, record or deliver steps. Templates use {{field}}."""
    return engine.save(definition)


@server.tool()
def update_workflow(workflow_id: str, revision: int, definition: engine.Workflow) -> dict:
    """Replace a workflow if its saved revision matches the supplied revision."""
    return engine.save(definition, workflow_id, revision)


@server.tool()
def preview_workflow(workflow_id: str, payload: dict[str, Any]) -> dict:
    """Evaluate a sample payload without writing records, runs or deliveries."""
    return engine.run(workflow_id, payload, preview=True)


@server.tool()
def run_workflow(workflow_id: str, payload: dict[str, Any], event_id: str | None = None) -> dict:
    """Run a workflow. An event ID deduplicates retries for the same input."""
    return engine.run(workflow_id, payload, event_id)


@server.tool()
def list_runs(workflow_id: str) -> list[dict]:
    """Return the 50 most recent runs with output and step traces."""
    return engine.history(workflow_id)


@server.tool()
def list_records(workflow_id: str) -> list[dict]:
    """Read the 100 most recent records saved by this workflow."""
    return engine.records(workflow_id)


@server.tool()
def list_deliveries(workflow_id: str) -> list[dict]:
    """Read recent outbound delivery states and receiver status codes."""
    return engine.deliveries(workflow_id)
