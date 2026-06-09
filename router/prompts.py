from __future__ import annotations

import json

from .schemas import InferenceRoute, NodePricing


def build_split_prompt(code_content: str, nodes: list[NodePricing], policy_instructions: str = "") -> str:
    numbered_code = "\n".join(f"{index:03d}: {line}" for index, line in enumerate(code_content.splitlines(), start=1))
    node_json = json.dumps([node.to_dict() for node in nodes], indent=2)
    policy = policy_instructions.strip() or "Use the public skeleton routing policy."
    return f"""
You are the CapIX Smart Route planner.

Split this user code between available nodes to save money while preserving execution correctness.

Available nodes:
{node_json}

Runtime policy:
{policy}

Rules:
- Put data cleaning, setup, parsing, IO, formatting, and sequential logs on CPU nodes.
- Put matrix operations, vector math, model training, tensor work, and repeated numeric kernels on GPU nodes.
- Do not invent node IDs.
- Use inclusive line numbers.
- Avoid splitting inside a tightly coupled function unless the route is obviously safe.
- Return raw JSON only. Do not include markdown.

Required JSON shape:
{{
  "analysis": "Short explanation of the split.",
  "allocation": [
    {{
      "node_id": "node-02-cpu",
      "line_start": 1,
      "line_end": 10,
      "task_label": "setup_and_cleaning",
      "reason": "Plain English reason."
    }}
  ],
  "warnings": []
}}

CODE:
{numbered_code}
""".strip()


def build_inference_split_prompt(prompt_content: str, routes: list[InferenceRoute], policy_instructions: str = "") -> str:
    route_json = json.dumps([route.to_dict() for route in routes], indent=2)
    policy = policy_instructions.strip() or "Use the public skeleton routing policy."
    return f"""
You are the CapIX Smart Inference Router.

Strip noisy wrapper text from the buyer prompt, decompose the real request into 3 to 5 execution segments, and route each segment to the best available model seller by price, latency, reliability, and task fit.

Available inference routes:
{route_json}

Runtime policy:
{policy}

Rules:
- Do not route transport wrappers, filenames, wallet receipts, or CapIX UI copy as prompt work.
- Put extraction, classification, schema checks, formatting, and cheap verification on low-cost fast routes.
- Put planning, tool orchestration, code reasoning, and multi-step decomposition on stronger reasoning routes.
- Put final synthesis on the strongest cost-effective synthesis route.
- Do not invent route IDs.
- Keep every reason short, concrete, and judge-readable.
- Return raw JSON only. Do not include markdown.

Required JSON shape:
{{
  "analysis": "Short explanation of how the prompt was stripped, decomposed, and routed.",
  "allocation": [
    {{
      "node_id": "route-or-provider-id",
      "segment_index": 1,
      "task_label": "intent_constraints_extraction",
      "segment_label": "Extract intent, constraints, facts, and output schema.",
      "reason": "Plain English reason tied to price, latency, reliability, or model fit."
    }}
  ],
  "warnings": []
}}

BUYER PROMPT:
{prompt_content}
""".strip()
