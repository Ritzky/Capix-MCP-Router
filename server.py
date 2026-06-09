from __future__ import annotations

import json

from router.agent import split_and_route_job
from router.inference_agent import split_and_route_prompt
from router.mongodb_mcp_client import MongoDbMcpClient

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - lets tests import without FastMCP installed.
    FastMCP = None


class _MissingFastMcp:
    def tool(self):
        def decorator(func):
            return func

        return decorator

    def run(self):
        raise RuntimeError("FastMCP is not installed. Run `pip install -r requirements.txt` first.")


mcp = FastMCP("CapixRouter") if FastMCP else _MissingFastMcp()


@mcp.tool()
def get_node_pricing() -> str:
    """Gets available node rates from MongoDB MCP, direct MongoDB, or the offline market catalog."""
    result = MongoDbMcpClient().get_node_pricing()
    return json.dumps([node.to_dict() for node in result.nodes])


@mcp.tool()
def get_inference_routes() -> str:
    """Gets available inference routes from MongoDB MCP, direct MongoDB, or the offline market catalog."""
    result = MongoDbMcpClient().get_inference_routes()
    return json.dumps([route.to_dict() for route in result.routes])


@mcp.tool()
def split_and_route_job_tool(code_content: str, setup_script: str = "", language: str = "python", bundle_file_name: str = "", paid_route_key: str = "") -> dict:
    """Splits a packaged script between CPU and GPU nodes. Production can require a paid CapIX route key."""
    return split_and_route_job(code_content, setup_script=setup_script, language=language, bundle_file_name=bundle_file_name, paid_route_key=paid_route_key)


@mcp.tool()
def split_and_route_prompt_tool(prompt_content: str, paid_route_key: str = "") -> dict:
    """Splits a complex inference prompt across surplus model-provider routes. Production can require a paid CapIX route key."""
    return split_and_route_prompt(prompt_content, paid_route_key=paid_route_key)


if __name__ == "__main__":
    mcp.run()
