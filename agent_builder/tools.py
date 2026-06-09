from __future__ import annotations

from typing import Any

from router.agent import split_and_route_job
from router.inference_agent import split_and_route_prompt
from router.mongodb_mcp_client import MongoDbMcpClient


def inspect_compute_route_book(limit: int = 12) -> dict[str, Any]:
    """Return public-safe compute routes from MongoDB MCP/direct Mongo/fallback."""
    result = MongoDbMcpClient().get_node_pricing()
    nodes = [node.to_dict() for node in result.nodes[: max(1, min(limit, 100))]]
    return {
        "source": result.source,
        "count": len(result.nodes),
        "warnings": result.warnings,
        "nodes": nodes,
    }


def inspect_inference_route_book(limit: int = 12) -> dict[str, Any]:
    """Return public-safe inference routes from MongoDB MCP/direct Mongo/fallback."""
    result = MongoDbMcpClient().get_inference_routes()
    routes = [route.to_dict() for route in result.routes[: max(1, min(limit, 100))]]
    return {
        "source": result.source,
        "count": len(result.routes),
        "warnings": result.warnings,
        "routes": routes,
    }


def route_compute_package(
    entry_script: str,
    setup_script: str = "",
    language: str = "python",
    bundle_file_name: str = "",
) -> dict[str, Any]:
    """Route a compute package and return best-path allocation plus savings math."""
    return split_and_route_job(
        entry_script,
        setup_script=setup_script,
        language=language,
        bundle_file_name=bundle_file_name,
    )


def route_inference_prompt(prompt: str, routing_context: str = "", language: str = "prompt") -> dict[str, Any]:
    """Split a complex prompt across surplus inference routes."""
    context = f"CapIX inference job format: {language}\n"
    if routing_context.strip():
        context += f"\nROUTING CONTEXT:\n{routing_context.strip()}\n"
    return split_and_route_prompt(f"{context}\nPROMPT:\n{prompt}")


def build_controlled_execution_plan(routing_response: dict[str, Any]) -> dict[str, Any]:
    """Summarize what the private app should execute for the demo video."""
    routing = routing_response.get("routing") if isinstance(routing_response, dict) else {}
    allocation = routing.get("allocation") if isinstance(routing, dict) else []
    lanes = []
    if isinstance(allocation, list):
        for item in allocation:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("node_id") or "route")
            task = str(item.get("segment_label") or item.get("task_label") or "routed segment")
            role = "gpu" if "gpu" in f"{label} {task}".lower() else "cpu"
            lanes.append({"role": role, "target": label, "task": task})
    return {
        "execution_boundary": "Only the private CapIX app can call Oracle Node Agents or handle wallet settlement.",
        "demo_modes": {
            "basic": "safe marked Python demo can execute on the Oracle CPU lane",
            "standard": "controlled output.txt proves route handoff without arbitrary code execution",
            "complex": "controlled output.txt keeps training-heavy demo reliable for video capture",
        },
        "lanes": lanes,
    }
