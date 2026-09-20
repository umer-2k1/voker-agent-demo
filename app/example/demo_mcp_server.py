"""Local stdio MCP server used by the Voker observability demo."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Demo Operations MCP")


@mcp.tool()
def company_policy(topic: str) -> str:
    """Return a policy snippet. Topic 'explode' intentionally raises an MCP error."""
    if topic.lower() == "explode":
        raise RuntimeError("policy service is unavailable: planned MCP failure")
    policies = {"refund": "Refunds are allowed within 30 days with an order number.", "privacy": "Never expose customer email addresses in public notes.", "shipping": "Express shipping is not guaranteed during carrier incidents."}
    return policies.get(topic.lower(), f"No policy exists for '{topic}'.")


@mcp.tool()
def incident_status(service: str) -> str:
    """Get a deterministic demo service status."""
    states = {"payments": "degraded", "warehouse": "operational", "inventory": "investigating latency"}
    return f"{service}: {states.get(service.lower(), 'unknown service')}"


@mcp.tool()
def append_customer_note(customer_id: str, note: str) -> str:
    """Pretend to save a support note; IDs starting FAIL intentionally fail."""
    if customer_id.upper().startswith("FAIL"):
        raise RuntimeError("CRM write rejected: planned MCP error")
    return f"Saved note for {customer_id}: {note[:80]}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
