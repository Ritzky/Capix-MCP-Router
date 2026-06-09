from __future__ import annotations

from typing import Any

from .agent import _gemini_configured, _generate_gemini_text, parse_json_object
from .mongodb_mcp_client import MongoDbMcpClient
from .policy import load_runtime_policy
from .prompts import build_inference_split_prompt
from .schemas import (
    HOLD_CAP_CPX,
    InferenceRoute,
)


def split_and_route_prompt(prompt_content: str, paid_route_key: str = "") -> dict[str, Any]:
    prompt_content = sanitize_prompt_content(prompt_content)
    policy = load_runtime_policy(paid_route_key)
    client = MongoDbMcpClient()
    pricing = client.get_inference_routes()
    routes = pricing.routes
    warnings = list(pricing.warnings)
    if policy.source != "open-source-skeleton":
        warnings.append(f"Runtime policy loaded from {policy.source}.")

    fallback_used = True
    analysis = (
        f"Smart Inference Route scanned {len(routes)} model-provider routes, broke the prompt "
        "into extraction, planning, synthesis, and verification subtasks, then matched each "
        "subtask to the cheapest reliable surplus route."
    )
    if _gemini_configured():
        try:
            analysis, allocation, gemini_warnings = route_prompt_with_gemini(prompt_content, routes, policy.instructions)
            warnings.extend(gemini_warnings)
            fallback_used = False
        except (ValueError, RuntimeError, KeyError, TypeError) as error:
            warnings.append(f"Gemini inference route unavailable; deterministic fallback used. {error}")
            allocation = deterministic_prompt_allocation(prompt_content, routes)
    else:
        warnings.append("Gemini inference route not configured; deterministic fallback used.")
        allocation = deterministic_prompt_allocation(prompt_content, routes)

    baseline, optimized, savings = estimate_prompt_route_cost(allocation, routes)
    return {
        "routing": {
            "analysis": analysis,
            "allocation": allocation,
            "providers": [route.to_dict() for route in routes],
            "nodes": [route.to_dict() for route in routes],
            "source": pricing.source,
            "fallback_used": fallback_used,
            "warnings": warnings,
            "policy_source": policy.source,
        },
        "unoptimized_gpu_cost_usd": baseline,
        "capix_optimized_cost_usd": optimized,
        "percent_savings": savings,
        "hold_cap_cpx": HOLD_CAP_CPX,
        "settled_cpx": optimized,
        "released_cpx": round(max(0, HOLD_CAP_CPX - optimized), 5),
    }


def route_prompt_with_gemini(prompt_content: str, routes: list[InferenceRoute], policy_instructions: str = "") -> tuple[str, list[dict[str, Any]], list[str]]:
    text = _generate_gemini_text(build_inference_split_prompt(prompt_content, routes, policy_instructions=policy_instructions))
    parsed = parse_json_object(text)
    allocation = validate_prompt_allocation(parsed.get("allocation"), routes)
    analysis = str(parsed.get("analysis") or "Gemini decomposed the prompt and routed each segment across the lowest-cost reliable model sellers.")
    warnings = [str(item) for item in parsed.get("warnings", []) if str(item).strip()]
    return analysis, allocation, warnings


def validate_prompt_allocation(raw: Any, routes: list[InferenceRoute]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ValueError("allocation must be a list")
    route_by_id = {route.route_id: route for route in routes}
    allocation: list[dict[str, Any]] = []
    seen_segments: set[int] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("allocation item must be an object")
        route_id = str(item.get("node_id") or item.get("route_id") or "").strip()
        route = route_by_id.get(route_id)
        if route is None:
            raise ValueError(f"unknown route_id {route_id}")
        segment_index = int(item.get("segment_index") or item.get("line_start") or index)
        if segment_index < 1 or segment_index > 8 or segment_index in seen_segments:
            raise ValueError("segment index is invalid or duplicated")
        seen_segments.add(segment_index)
        segment_label = str(item.get("segment_label") or item.get("task") or item.get("task_label") or "Route prompt segment.").strip()
        reason = str(item.get("reason") or f"Routed to {route.label}.").strip()
        allocation.append(
            _prompt_segment(
                route,
                segment_index,
                str(item.get("task_label") or f"segment_{segment_index}").strip(),
                segment_label,
                reason,
            )
        )
    if len(allocation) < 3:
        raise ValueError("allocation must include at least 3 routed prompt segments")
    return sorted(allocation, key=lambda item: int(item["line_start"]))


def deterministic_prompt_allocation(prompt_content: str, routes: list[InferenceRoute]) -> list[dict[str, Any]]:
    phi = _route_for(routes, "phi") or _cheapest(routes)
    mixtral = _route_for(routes, "mixtral") or _most_capable(routes)
    llama = _route_for(routes, "llama") or _most_capable(routes)

    trimmed = " ".join(sanitize_prompt_content(prompt_content).split())
    objective = summarize_prompt_objective(trimmed)
    planning_route = mixtral if _needs_planning(trimmed) else phi
    return [
        _prompt_segment(
            phi,
            1,
            "intent_constraints_extraction",
            "Extract task intent, hard constraints, source facts, and required output shape.",
            f"Cheap extraction lane strips noisy context and structures the buyer request around: {objective}",
        ),
        _prompt_segment(
            planning_route,
            2,
            "route_plan_decomposition",
            "Decompose the request into tool calls, model calls, and ordering constraints.",
            "Planning/code-heavy prompts use a stronger reasoning lane; simple prompts stay on the cheapest reliable lane.",
        ),
        _prompt_segment(
            llama,
            3,
            "answer_synthesis",
            "Generate the final response with the richer context assembled by the routed subtasks.",
            "Final synthesis benefits from the higher-quality surplus 70B route.",
        ),
        _prompt_segment(
            phi,
            4,
            "format_safety_check",
            "Check formatting, missing constraints, and response completeness before returning.",
            "Cheap low-latency verification avoids paying premium-model rates for mechanical checks.",
        ),
    ]


def _route_for(routes: list[InferenceRoute], keyword: str) -> InferenceRoute | None:
    lowered = keyword.lower()
    return next((route for route in routes if lowered in route.model_id.lower() or lowered in route.label.lower()), None)


def sanitize_prompt_content(prompt_content: str) -> str:
    """Remove CapIX transport wrappers before routing prompt semantics."""

    text = prompt_content.strip()
    for marker in ("PROMPT:", "Prompt:", "prompt:"):
        index = text.rfind(marker)
        if index >= 0:
            text = text[index + len(marker):].strip()
            break
    lines = []
    skip_context = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if lowered.startswith("capix inference job format") or lowered.startswith("prompt file:"):
            continue
        if lowered.startswith("routing context"):
            skip_context = True
            continue
        if skip_context and not line:
            skip_context = False
            continue
        if skip_context:
            continue
        lines.append(raw_line)
    return "\n".join(lines).strip() or prompt_content.strip()


def summarize_prompt_objective(prompt: str) -> str:
    cleaned = " ".join(prompt.split())
    lower = cleaned.lower()
    if "support" in lower and ("automation" in lower or "ticket" in lower):
        return "support automation triage, incident-theme extraction, operator planning, and launch-review reporting"
    if "agent" in lower and "workflow" in lower:
        return "agent workflow decomposition, cheap checks, strong-model reasoning, and final report synthesis"
    if "eval" in lower or "benchmark" in lower:
        return "evaluation decomposition, batch scoring, verification, and final benchmark summary"
    return cleaned[:140] + ("..." if len(cleaned) > 140 else "")


def _cheapest(routes: list[InferenceRoute]) -> InferenceRoute:
    return min(routes, key=lambda route: route.rate_per_request_cpx)


def _most_capable(routes: list[InferenceRoute]) -> InferenceRoute:
    return max(routes, key=lambda route: route.rate_per_request_cpx)


def _needs_planning(prompt: str) -> bool:
    value = prompt.lower()
    return any(keyword in value for keyword in ("code", "api", "tool", "agent", "workflow", "evaluate", "benchmark", "multi-step", "route"))


def _prompt_segment(route: InferenceRoute, index: int, task_label: str, segment_label: str, reason: str) -> dict[str, Any]:
    return {
        "node_id": route.route_id,
        "label": route.label,
        "line_start": index,
        "line_end": index,
        "task_label": task_label,
        "segment_label": segment_label,
        "reason": reason,
        "model_id": route.model_id,
        "rate_per_request_cpx": route.rate_per_request_cpx,
        "latency_ms": route.latency_ms,
        "reliability": route.reliability,
    }


def estimate_prompt_route_cost(allocation: list[dict[str, Any]], routes: list[InferenceRoute]) -> tuple[float, float, str]:
    by_id = {route.route_id: route for route in routes}
    premium = _most_capable(routes)
    baseline = round(premium.rate_per_request_cpx * max(4, len(allocation)), 5)
    optimized = 0.0
    for item in allocation:
        route = by_id.get(str(item.get("node_id")))
        optimized += route.rate_per_request_cpx if route else premium.rate_per_request_cpx
    optimized = round(max(0.001, optimized), 5)
    saving = max(0, round((1 - optimized / max(baseline, 0.001)) * 100))
    return baseline, optimized, f"{saving}%"
