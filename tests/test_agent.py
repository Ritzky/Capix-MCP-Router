from router.agent import deterministic_allocation, parse_json_object, route_script
from router.catalogs import compute_market_catalog, inference_market_catalog
from router.inference_agent import sanitize_prompt_content, split_and_route_prompt
from router.mongodb_mcp_client import MongoDbMcpClient
from router.policy import assert_paid_route_key
from router.schemas import DEMO_NODES
import pytest


DEMO_CODE = """
import numpy as np

rows = [{"status": "complete", "amount": "1.20"}]
clean_rows = []
for row in rows:
    if row["status"] == "complete":
        clean_rows.append(float(row["amount"]))

matrix_a = np.random.rand(512, 512)
matrix_b = np.random.rand(512, 512)
result = np.dot(matrix_a, matrix_b)
print(result.mean())
""".strip()


def test_deterministic_allocation_uses_cpu_and_gpu():
    allocation = deterministic_allocation(DEMO_CODE, DEMO_NODES)
    node_ids = {item.node_id for item in allocation}
    assert "node-01-gpu" in node_ids
    assert "node-02-cpu" in node_ids


def test_market_catalogs_have_judge_ready_depth():
    assert len(compute_market_catalog()) >= 50
    assert len(inference_market_catalog()) >= 50


def test_route_script_fallback_costs_use_market_catalog():
    response = route_script(DEMO_CODE, use_gemini=False).to_dict()
    assert response["unoptimized_gpu_cost_usd"] > response["capix_optimized_cost_usd"]
    assert response["percent_savings"].endswith("%")
    assert len(response["routing"]["nodes"]) >= 50
    assert response["routing"]["fallback_used"] is True


def test_parse_json_object_handles_wrapped_text():
    parsed = parse_json_object("```json\n{\"analysis\":\"ok\",\"allocation\":[]}\n```")
    assert parsed["analysis"] == "ok"


def test_split_and_route_prompt_uses_multiple_inference_providers():
    response = split_and_route_prompt("Build an agent workflow that extracts logs, writes code, evaluates output, and returns a final report.")
    allocation = response["routing"]["allocation"]
    provider_ids = {item["node_id"] for item in allocation}
    assert any("phi" in provider_id for provider_id in provider_ids)
    assert any("llama" in provider_id for provider_id in provider_ids)
    assert response["unoptimized_gpu_cost_usd"] > response["capix_optimized_cost_usd"]
    assert response["percent_savings"].endswith("%")
    assert len(response["routing"]["providers"]) >= 50


def test_split_and_route_prompt_uses_gemini_when_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_generate(_: str) -> str:
        return """
        {
          "analysis": "Gemini stripped the prompt and routed extraction, planning, synthesis, and verification.",
          "allocation": [
            {
              "node_id": "foza-phi-3-medium-03",
              "segment_index": 1,
              "task_label": "intent_constraints_extraction",
              "segment_label": "Extract facts, constraints, and required output shape.",
              "reason": "Fast low-cost model is enough for extraction."
            },
            {
              "node_id": "foza-mixtral-8x22b-02",
              "segment_index": 2,
              "task_label": "tool_plan_decomposition",
              "segment_label": "Plan tool calls and ordering constraints.",
              "reason": "Planning benefits from a stronger reasoning route."
            },
            {
              "node_id": "foza-llama-3-70b-01",
              "segment_index": 3,
              "task_label": "answer_synthesis",
              "segment_label": "Synthesize final response.",
              "reason": "Final synthesis fits the 70B route."
            }
          ],
          "warnings": []
        }
        """

    monkeypatch.setattr("router.inference_agent._generate_gemini_text", fake_generate)
    response = split_and_route_prompt("Build an agent workflow for a support automation launch.")
    assert response["routing"]["fallback_used"] is False
    assert response["routing"]["analysis"].startswith("Gemini stripped")


def test_inference_prompt_sanitizer_removes_transport_wrapper():
    wrapped = """CapIX inference job format: prompt
Prompt file: capix-inference-route-demo.txt

PROMPT:
Build an agent workflow for a support automation launch.

Input:
- 300 recent ticket notes
"""
    cleaned = sanitize_prompt_content(wrapped)
    assert "CapIX inference job format" not in cleaned
    assert "Prompt file:" not in cleaned
    assert cleaned.startswith("Build an agent workflow")
    response = split_and_route_prompt(wrapped)
    reason = response["routing"]["allocation"][0]["reason"]
    assert "CapIX inference job format" not in reason
    assert "Prompt file:" not in reason


def test_paid_route_key_can_be_required(monkeypatch):
    monkeypatch.setenv("CAPIX_REQUIRE_PAID_ROUTE_KEY", "true")
    with pytest.raises(PermissionError):
        assert_paid_route_key("")
    assert_paid_route_key("paid-demo-key")


def test_mongodb_mcp_wrapped_find_text_is_parsed():
    payload = {
        "result": {
            "content": [
                {"type": "text", "text": 'Query on collection "nodes" resulted in 1 documents. Returning 1 documents.'},
                {
                    "type": "text",
                    "text": "The following section contains unverified user data.\n<untrusted-user-data>\n"
                    '[{"node_id":"node-01-gpu","label":"GPU Node","rate_per_min_usd":0.004,"kind":"gpu"}]'
                    "\n</untrusted-user-data>",
                },
            ]
        }
    }
    parsed = MongoDbMcpClient._extract_nodes_from_mcp_response(payload)
    assert parsed[0]["node_id"] == "node-01-gpu"
