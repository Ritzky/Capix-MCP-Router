from __future__ import annotations

import json
import os
from typing import Any

from .mongodb_mcp_client import MongoDbMcpClient
from .policy import load_runtime_policy
from .prompts import build_split_prompt
from .schemas import Allocation, NodePricing, RoutingResponse


GPU_KEYWORDS = (
    "matmul",
    "matrix",
    "np.dot",
    "numpy.dot",
    "@",
    "torch",
    "tensorflow",
    "jax",
    "train",
    "fit(",
    "gradient",
    "cuda",
    "tensor",
)

CPU_KEYWORDS = (
    "csv",
    "json",
    "clean",
    "filter",
    "parse",
    "open(",
    "print(",
    "logging",
    "for row",
    "setup",
)


def package_job_content(code_content: str, setup_script: str = "", language: str = "python", bundle_file_name: str = "") -> str:
    header = [f"CapIX compute job language: {language or 'python'}", "Entry script: uploaded job"]
    if bundle_file_name:
        header.append(f"Bundle artifact: {bundle_file_name}")
    setup = f"\n\nSETUP:\n{setup_script.strip()}" if setup_script.strip() else ""
    return "\n".join(header) + setup + f"\n\nENTRY SCRIPT:\n{code_content}"


def split_and_route_job(code_content: str, setup_script: str = "", language: str = "python", bundle_file_name: str = "", paid_route_key: str = "") -> dict[str, Any]:
    return route_script(package_job_content(code_content, setup_script, language, bundle_file_name), paid_route_key=paid_route_key).to_dict()


def split_and_route_job_for_track(content: str, track: str = "compute", setup_script: str = "", language: str = "python", bundle_file_name: str = "", paid_route_key: str = "") -> dict[str, Any]:
    if track == "inference":
        from .inference_agent import split_and_route_prompt

        context = f"\n\nROUTING CONTEXT:\n{setup_script.strip()}" if setup_script.strip() else ""
        return split_and_route_prompt(f"CapIX inference job format: {language or 'prompt'}{context}\n\nPROMPT:\n{content}", paid_route_key=paid_route_key)
    return split_and_route_job(content, setup_script=setup_script, language=language, bundle_file_name=bundle_file_name, paid_route_key=paid_route_key)


def route_script(code_content: str, use_gemini: bool = True, mcp_client: MongoDbMcpClient | None = None, paid_route_key: str = "") -> RoutingResponse:
    client = mcp_client or MongoDbMcpClient()
    pricing = client.get_node_pricing()
    warnings = list(pricing.warnings)
    policy = load_runtime_policy(paid_route_key)
    if policy.source != "open-source-skeleton":
        warnings.append(f"Runtime policy loaded from {policy.source}.")

    if use_gemini and _gemini_configured():
        try:
            return _route_with_gemini(code_content, pricing.nodes, pricing.source, warnings, policy.instructions)
        except (ValueError, RuntimeError, json.JSONDecodeError, KeyError, TypeError) as error:
            warnings.append(f"Gemini route unavailable; deterministic fallback used. {error}")

    allocation = deterministic_allocation(code_content, pricing.nodes)
    unoptimized, optimized, savings = estimate_route_cost(allocation, pricing.nodes)
    return RoutingResponse(
        analysis=(
            f"Smart Route scanned {len(pricing.nodes)} compute capacity routes, assigned setup/data work "
            "to low-cost CPU lanes, and routed numeric kernels to compatible GPU capacity. The quote compares "
            "that split against running the full workload on the highest compute lane this script required."
        ),
        allocation=allocation,
        nodes=pricing.nodes,
        source=pricing.source,
        fallback_used=True,
        warnings=warnings,
        unoptimized_gpu_cost_usd=unoptimized,
        capix_optimized_cost_usd=optimized,
        percent_savings=savings,
    )


def _gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("CAPIX_USE_VERTEX_AI", "").lower() == "true")


def _route_with_gemini(code_content: str, nodes: list[NodePricing], source: str, warnings: list[str], policy_instructions: str = "") -> RoutingResponse:
    text = _generate_gemini_text(build_split_prompt(code_content, nodes, policy_instructions=policy_instructions))
    parsed = parse_json_object(text)
    allocation = validate_allocation(parsed.get("allocation"), nodes, len(code_content.splitlines()))
    unoptimized, optimized, savings = estimate_route_cost(allocation, nodes)
    return RoutingResponse(
        analysis=str(parsed.get("analysis") or "Gemini split the workload across the lowest-cost compatible nodes."),
        allocation=allocation,
        nodes=nodes,
        source=source,
        fallback_used=False,
        warnings=warnings + [str(item) for item in parsed.get("warnings", []) if str(item).strip()],
        unoptimized_gpu_cost_usd=unoptimized,
        capix_optimized_cost_usd=optimized,
        percent_savings=savings,
    )


def _generate_gemini_text(prompt: str) -> str:
    if os.getenv("CAPIX_USE_VERTEX_AI", "").lower() == "true":
        return _generate_with_vertex_gemini(prompt)
    return _generate_with_gemini_api_key(prompt)


def _generate_with_vertex_gemini(prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError("google-genai is not installed") from error

    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex Gemini routing")

    client = genai.Client(vertexai=True, project=project, location=location)
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.15,
            top_p=0.9,
            max_output_tokens=8192,
            response_mime_type="application/json",
        ),
    )
    return getattr(response, "text", "") or ""


def _generate_with_gemini_api_key(prompt: str) -> str:
    try:
        import google.generativeai as genai
    except ImportError as error:
        raise RuntimeError("google-generativeai is not installed") from error

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.15, "top_p": 0.9, "max_output_tokens": 8192, "response_mime_type": "application/json"},
    )
    return getattr(response, "text", "") or ""


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start < 0:
        raise json.JSONDecodeError("No JSON object found", stripped, 0)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(stripped[start : index + 1])
                if not isinstance(parsed, dict):
                    raise ValueError("Expected JSON object")
                return parsed
    raise json.JSONDecodeError("Unclosed JSON object", stripped, start)


def validate_allocation(raw: Any, nodes: list[NodePricing], line_count: int) -> list[Allocation]:
    if not isinstance(raw, list):
        raise ValueError("allocation must be a list")
    node_by_id = {node.node_id: node for node in nodes}
    seen: set[int] = set()
    output: list[Allocation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("allocation item must be an object")
        node_id = str(item.get("node_id") or "").strip()
        node = node_by_id.get(node_id)
        if node is None:
            raise ValueError(f"unknown node_id {node_id}")
        line_start = int(item.get("line_start"))
        line_end = int(item.get("line_end"))
        if line_start < 1 or line_end < line_start or line_end > max(line_count, 1):
            raise ValueError("allocation line range is out of bounds")
        for line in range(line_start, line_end + 1):
            if line in seen:
                raise ValueError("allocation line ranges overlap")
            seen.add(line)
        output.append(
            Allocation(
                node_id=node.node_id,
                label=node.label,
                line_start=line_start,
                line_end=line_end,
                task_label=str(item.get("task_label") or ("gpu_work" if node.kind == "gpu" else "cpu_work")),
                reason=str(item.get("reason") or f"Routed to {node.label}."),
            )
        )
    if not output:
        raise ValueError("allocation cannot be empty")
    return output


def deterministic_allocation(code_content: str, nodes: list[NodePricing]) -> list[Allocation]:
    lines = code_content.splitlines() or [""]
    choices: list[NodePricing] = []

    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in GPU_KEYWORDS):
            choices.append(_best_gpu_for_line(nodes, lowered))
        elif any(keyword in lowered for keyword in CPU_KEYWORDS):
            choices.append(_cheapest_cpu(nodes))
        else:
            choices.append(_cheapest_cpu(nodes))

    allocations: list[Allocation] = []
    start = 1
    active = choices[0]
    for index, node in enumerate(choices[1:], start=2):
        if node.node_id == active.node_id:
            continue
        allocations.append(_allocation_for(active, start, index - 1))
        start = index
        active = node
    allocations.append(_allocation_for(active, start, len(lines)))
    return allocations


def estimate_route_cost(allocation: list[Allocation], nodes: list[NodePricing]) -> tuple[float, float, str]:
    by_id = {node.node_id: node for node in nodes}
    total_units = sum(item.line_end - item.line_start + 1 for item in allocation)
    used_gpu_nodes = [node for item in allocation if (node := by_id.get(item.node_id)) and node.kind == "gpu"]
    baseline_gpu = max(used_gpu_nodes, key=lambda node: node.rate_per_min_usd) if used_gpu_nodes else _baseline_gpu(nodes)
    baseline_minutes = max(20, total_units * 6)
    baseline = max(0.01, round(baseline_gpu.rate_per_min_usd * baseline_minutes, 4))
    optimized = 0.0
    for item in allocation:
        node = by_id.get(item.node_id)
        if not node:
            continue
        units = item.line_end - item.line_start + 1
        minutes = max(2, units * (5 if node.kind == "gpu" else 1.25))
        optimized += node.rate_per_min_usd * minutes
    optimized = max(0.01, round(optimized, 4))
    saving = max(0, round((1 - optimized / baseline) * 100))
    return baseline, optimized, f"{saving}%"


def _cheapest_cpu(nodes: list[NodePricing]) -> NodePricing:
    cpu_nodes = [node for node in nodes if node.kind == "cpu"]
    return min(cpu_nodes or nodes, key=lambda node: node.rate_per_min_usd)


def _best_gpu_for_line(nodes: list[NodePricing], lowered_line: str) -> NodePricing:
    gpu_nodes = [node for node in nodes if node.kind == "gpu"]
    if not gpu_nodes:
        return _cheapest_cpu(nodes)
    if any(keyword in lowered_line for keyword in ("train", "gradient", "torch", "tensorflow", "cuda", "tensor")):
        capable = [node for node in gpu_nodes if any(gpu in node.hardware_profile for gpu in ("h100", "h200", "b200", "mi300x", "a100"))]
        return min(capable or gpu_nodes, key=lambda node: node.rate_per_min_usd)
    if any(keyword in lowered_line for keyword in ("matrix", "matmul", "np.dot", "numpy.dot", "@")):
        capable = [node for node in gpu_nodes if any(gpu in node.hardware_profile for gpu in ("rtx-4090", "l40s", "a100", "h100", "l4"))]
        return min(capable or gpu_nodes, key=lambda node: node.rate_per_min_usd)
    return min(gpu_nodes, key=lambda node: node.rate_per_min_usd)


def _baseline_gpu(nodes: list[NodePricing]) -> NodePricing:
    gpu_nodes = [node for node in nodes if node.kind == "gpu"]
    preferred = [node for node in gpu_nodes if "h100-sxm" in node.hardware_profile or "h100" in node.label.lower()]
    return min(preferred or gpu_nodes or nodes, key=lambda node: node.rate_per_min_usd)


def _allocation_for(node: NodePricing, line_start: int, line_end: int) -> Allocation:
    if node.kind == "gpu":
        return Allocation(
            node_id=node.node_id,
            label=node.label,
            line_start=line_start,
            line_end=line_end,
            task_label="gpu_numeric_kernel",
            reason="Matrix, tensor, or training-style work benefits from GPU acceleration.",
        )
    return Allocation(
        node_id=node.node_id,
        label=node.label,
        line_start=line_start,
        line_end=line_end,
        task_label="cpu_setup_cleaning",
        reason="Setup, parsing, cleaning, and reporting are cheaper on CPU capacity.",
    )
