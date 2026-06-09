from __future__ import annotations

from dataclasses import dataclass
from typing import Any


UNOPTIMIZED_GPU_COST_USD = 0.80
CAPIX_OPTIMIZED_COST_USD = 0.12
PERCENT_SAVINGS = "85%"
HOLD_CAP_CPX = 1.00
SETTLED_CPX = 0.12
RELEASED_CPX = 0.88
INFERENCE_BASELINE_CPX = 0.088
INFERENCE_OPTIMIZED_CPX = 0.045
INFERENCE_PERCENT_SAVINGS = "49%"
INFERENCE_SETTLED_CPX = 0.045
INFERENCE_RELEASED_CPX = 0.955


@dataclass(frozen=True)
class NodePricing:
    node_id: str
    label: str
    rate_per_min_usd: float
    kind: str
    route_label: str = ""
    runtime_node_id: str = ""
    endpoint_base_url: str = ""
    provider_name: str = ""
    region: str = ""
    capacity: str = ""
    hardware_profile: str = ""
    simulated: bool = False
    hourly_rate_usd: float = 0.0
    source_url: str = ""
    pricing_basis: str = ""
    available_units: int = 0
    memory_gb: int = 0
    last_observed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "rate_per_min_usd": self.rate_per_min_usd,
            "kind": self.kind,
            "route_label": self.route_label,
            "runtime_node_id": self.runtime_node_id,
            "endpoint_base_url": self.endpoint_base_url,
            "provider_name": self.provider_name,
            "region": self.region,
            "capacity": self.capacity,
            "hardware_profile": self.hardware_profile,
            "simulated": self.simulated,
            "hourly_rate_usd": self.hourly_rate_usd,
            "source_url": self.source_url,
            "pricing_basis": self.pricing_basis,
            "available_units": self.available_units,
            "memory_gb": self.memory_gb,
            "last_observed": self.last_observed,
        }


@dataclass(frozen=True)
class InferenceRoute:
    route_id: str
    label: str
    model_id: str
    provider_name: str
    rate_per_request_cpx: float
    latency_ms: int
    reliability: str
    fleet_status: str
    specialty: str
    endpoint_base_url: str = ""
    region: str = "global-router"
    capacity: str = ""
    simulated: bool = False
    input_per_1m_usd: float = 0.0
    output_per_1m_usd: float = 0.0
    source_url: str = ""
    pricing_basis: str = ""
    last_observed: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.route_id,
            "route_id": self.route_id,
            "label": self.label,
            "model_id": self.model_id,
            "provider_name": self.provider_name,
            "rate_per_request_cpx": self.rate_per_request_cpx,
            "latency_ms": self.latency_ms,
            "reliability": self.reliability,
            "fleet_status": self.fleet_status,
            "specialty": self.specialty,
            "endpoint_base_url": self.endpoint_base_url,
            "region": self.region,
            "capacity": self.capacity,
            "kind": "inference",
            "route_label": self.label,
            "simulated": self.simulated,
            "input_per_1m_usd": self.input_per_1m_usd,
            "output_per_1m_usd": self.output_per_1m_usd,
            "source_url": self.source_url,
            "pricing_basis": self.pricing_basis,
            "last_observed": self.last_observed,
        }


@dataclass(frozen=True)
class Allocation:
    node_id: str
    label: str
    line_start: int
    line_end: int
    task_label: str
    reason: str
    segment_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "task_label": self.task_label,
            "reason": self.reason,
            "segment_label": self.segment_label,
        }


@dataclass(frozen=True)
class RoutingResponse:
    analysis: str
    allocation: list[Allocation]
    nodes: list[NodePricing]
    source: str
    fallback_used: bool
    warnings: list[str]
    unoptimized_gpu_cost_usd: float = UNOPTIMIZED_GPU_COST_USD
    capix_optimized_cost_usd: float = CAPIX_OPTIMIZED_COST_USD
    percent_savings: str = PERCENT_SAVINGS

    def to_dict(self) -> dict[str, Any]:
        settled_cpx = round(min(HOLD_CAP_CPX, max(0.01, self.capix_optimized_cost_usd)), 5)
        return {
            "routing": {
                "analysis": self.analysis,
                "allocation": [item.to_dict() for item in self.allocation],
                "nodes": [node.to_dict() for node in self.nodes],
                "source": self.source,
                "fallback_used": self.fallback_used,
                "warnings": self.warnings,
            },
            "unoptimized_gpu_cost_usd": self.unoptimized_gpu_cost_usd,
            "capix_optimized_cost_usd": self.capix_optimized_cost_usd,
            "percent_savings": self.percent_savings,
            "hold_cap_cpx": HOLD_CAP_CPX,
            "settled_cpx": settled_cpx,
            "released_cpx": round(max(0, HOLD_CAP_CPX - settled_cpx), 5),
        }


DEMO_NODES = [
    NodePricing("node-01-gpu", "Route Node 1 - GPU lane", 0.004, "gpu", "Node 1", "oci-demo-1", "https://agent-1.capix.network", "OCI Demo Edge", "eu-amsterdam-1", "GPU-style numeric workload lane routed onto Oracle demo node 1", "gpu-mock", True),
    NodePricing("node-02-cpu", "Route Node 2 - CPU lane", 0.0001, "cpu", "Node 2", "oci-demo-2", "https://agent-2.capix.network", "OCI Demo Edge", "eu-amsterdam-1", "CPU setup, parsing, cleaning, and reporting lane routed onto Oracle demo node 2", "cpu-standard", False),
]

DEMO_INFERENCE_ROUTES = [
    InferenceRoute(
        "route-llama-70b",
        "Llama 70B surplus synthesis lane",
        "Meta Llama-3-70B-Instruct",
        "Surplus 70B Seller Pool",
        0.015,
        14,
        "97.8% rolling",
        "SURPLUS CAPACITY",
        "final synthesis, long-form reasoning, answer composition",
        "https://api.inference.capix.network/v1",
        capacity="2M routed tokens/day",
    ),
    InferenceRoute(
        "route-mixtral-8x22b",
        "Mixtral cluster-overflow planning lane",
        "Mistral-Mixtral-8x22B",
        "Cluster Overflow Seller Pool",
        0.022,
        22,
        "96.4% rolling",
        "CLUSTER OVERFLOW",
        "tool planning, code reasoning, multi-step decomposition",
        "https://api.inference.capix.network/v1",
        capacity="50k requests/week",
    ),
    InferenceRoute(
        "route-phi-3-medium",
        "Phi idle-fleet extraction lane",
        "Microsoft Phi-3-Medium",
        "Idle Node Fleet",
        0.004,
        8,
        "98.2% rolling",
        "IDLE NODE FLEET",
        "classification, extraction, summarization, format checks",
        "https://api.inference.capix.network/v1",
        capacity="low-latency microtasks",
    ),
]



def normalize_node(raw: dict[str, Any]) -> NodePricing:
    node_id = str(raw.get("node_id") or raw.get("nodeId") or raw.get("id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or node_id or "CapIX Node").strip()
    pricing = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {}
    rate = raw.get("rate_per_min_usd") or raw.get("ratePerMinUsd") or pricing.get("rate_per_min_usd") or pricing.get("ratePerMinUsd")
    kind = str(raw.get("kind") or raw.get("type") or raw.get("capability") or "").lower()

    if not node_id:
        raise ValueError("node_id is required")
    rate_float = float(rate)
    if rate_float <= 0:
        raise ValueError("rate_per_min_usd must be positive")
    if kind not in {"cpu", "gpu"}:
        kind = "gpu" if "gpu" in label.lower() else "cpu"
    return NodePricing(
        node_id=node_id,
        label=label,
        rate_per_min_usd=rate_float,
        kind=kind,
        route_label=str(raw.get("route_label") or raw.get("routeLabel") or "").strip(),
        runtime_node_id=str(raw.get("runtime_node_id") or raw.get("runtimeNodeId") or "").strip(),
        endpoint_base_url=str(raw.get("endpoint_base_url") or raw.get("endpointBaseUrl") or "").strip(),
        provider_name=str(raw.get("provider_name") or raw.get("providerName") or "").strip(),
        region=str(raw.get("region") or "").strip(),
        capacity=str(raw.get("capacity") or "").strip(),
        hardware_profile=str(raw.get("hardware_profile") or raw.get("hardwareProfile") or "").strip(),
        simulated=bool(raw.get("simulated")),
        hourly_rate_usd=float(raw.get("hourly_rate_usd") or raw.get("hourlyRateUsd") or round(rate_float * 60, 6)),
        source_url=str(raw.get("source_url") or raw.get("sourceUrl") or "").strip(),
        pricing_basis=str(raw.get("pricing_basis") or raw.get("pricingBasis") or "").strip(),
        available_units=int(raw.get("available_units") or raw.get("availableUnits") or 0),
        memory_gb=int(raw.get("memory_gb") or raw.get("memoryGb") or 0),
        last_observed=str(raw.get("last_observed") or raw.get("lastObserved") or "").strip(),
    )


def normalize_nodes(raw_nodes: Any) -> list[NodePricing]:
    if not isinstance(raw_nodes, list):
        return DEMO_NODES
    nodes: list[NodePricing] = []
    for raw in raw_nodes:
        if isinstance(raw, dict):
            try:
                nodes.append(normalize_node(raw))
            except (TypeError, ValueError):
                continue
    return nodes or DEMO_NODES


def normalize_inference_route(raw: dict[str, Any]) -> InferenceRoute:
    route_id = str(raw.get("route_id") or raw.get("routeId") or raw.get("node_id") or raw.get("id") or "").strip()
    label = str(raw.get("label") or raw.get("name") or route_id or "CapIX Inference Route").strip()
    model_id = str(raw.get("model_id") or raw.get("modelId") or raw.get("model") or label).strip()
    rate = raw.get("rate_per_request_cpx") or raw.get("ratePerRequestCpx") or raw.get("cost_per_request_cpx") or raw.get("askCpxRequest")
    if rate is None:
        rate = 0.015
    latency = raw.get("latency_ms") or raw.get("latencyMs") or raw.get("latency") or 14
    if isinstance(latency, str):
        latency = int("".join(char for char in latency if char.isdigit()) or "14")
    if not route_id:
        raise ValueError("route_id is required")
    rate_float = float(rate)
    if rate_float <= 0:
        raise ValueError("rate_per_request_cpx must be positive")
    return InferenceRoute(
        route_id=route_id,
        label=label,
        model_id=model_id,
        provider_name=str(raw.get("provider_name") or raw.get("providerName") or raw.get("fleet_status") or "CapIX Seller Pool").strip(),
        rate_per_request_cpx=rate_float,
        latency_ms=int(latency),
        reliability=str(raw.get("reliability") or "97.0% rolling").strip(),
        fleet_status=str(raw.get("fleet_status") or raw.get("fleetStatus") or raw.get("status") or "SURPLUS CAPACITY").strip(),
        specialty=str(raw.get("specialty") or raw.get("capacity") or "general inference route").strip(),
        endpoint_base_url=str(raw.get("endpoint_base_url") or raw.get("endpointBaseUrl") or "https://api.inference.capix.network/v1").strip(),
        region=str(raw.get("region") or "global-router").strip(),
        capacity=str(raw.get("capacity") or "").strip(),
        simulated=bool(raw.get("simulated")),
        input_per_1m_usd=float(raw.get("input_per_1m_usd") or raw.get("inputPer1mUsd") or 0),
        output_per_1m_usd=float(raw.get("output_per_1m_usd") or raw.get("outputPer1mUsd") or 0),
        source_url=str(raw.get("source_url") or raw.get("sourceUrl") or "").strip(),
        pricing_basis=str(raw.get("pricing_basis") or raw.get("pricingBasis") or "").strip(),
        last_observed=str(raw.get("last_observed") or raw.get("lastObserved") or "").strip(),
    )


def normalize_inference_routes(raw_routes: Any) -> list[InferenceRoute]:
    if not isinstance(raw_routes, list):
        return DEMO_INFERENCE_ROUTES
    routes: list[InferenceRoute] = []
    for raw in raw_routes:
        if isinstance(raw, dict):
            try:
                routes.append(normalize_inference_route(raw))
            except (TypeError, ValueError):
                continue
    return routes or DEMO_INFERENCE_ROUTES
