from agent_builder.demo import BASIC_REAL_DEMO, STANDARD_SPLIT_DEMO
from agent_builder.tools import build_controlled_execution_plan, inspect_compute_route_book, inspect_inference_route_book, route_compute_package


def test_agent_builder_compute_tool_routes_standard_demo():
    response = route_compute_package(STANDARD_SPLIT_DEMO, setup_script="numpy==2.1.3", language="python")
    assert response["routing"]["allocation"]
    assert response["unoptimized_gpu_cost_usd"] > response["capix_optimized_cost_usd"]
    assert response["percent_savings"].endswith("%")


def test_agent_builder_route_book_tools_return_depth():
    compute = inspect_compute_route_book(limit=5)
    inference = inspect_inference_route_book(limit=5)
    assert compute["count"] >= 2
    assert inference["count"] >= 3
    assert len(compute["nodes"]) <= 5
    assert len(inference["routes"]) <= 5


def test_controlled_execution_plan_mentions_demo_modes():
    response = route_compute_package(BASIC_REAL_DEMO, language="python")
    plan = build_controlled_execution_plan(response)
    assert "basic" in plan["demo_modes"]
    assert "private CapIX app" in plan["execution_boundary"]
