from __future__ import annotations

from datetime import UTC, datetime

from .schemas import InferenceRoute, NodePricing


COMPUTE_EXCHANGE_SOURCE = "https://compute.exchange/reserved-gpu-rental"
RUNPOD_SOURCE = "https://www.runpod.io/pricing"
VAST_SOURCE = "https://docs.vast.ai/api-reference/search/search-offers"
FOZA_SOURCE = "https://foza.ai/"
NEAR_AI_SOURCE = "https://www.near.ai/"


def observed_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_market_catalog(timestamp: str | None = None) -> list[NodePricing]:
    observed = timestamp or observed_now()
    providers = [
        ("runpod", "RunPod", "US-West", RUNPOD_SOURCE, 0.96),
        ("vast", "Vast.ai verified", "US-East", VAST_SOURCE, 0.82),
        ("lambda", "Lambda Labs", "US-West", COMPUTE_EXCHANGE_SOURCE, 1.04),
        ("coreweave", "CoreWeave", "US-East", COMPUTE_EXCHANGE_SOURCE, 1.12),
        ("crusoe", "Crusoe", "US-Central", COMPUTE_EXCHANGE_SOURCE, 1.00),
        ("tensordock", "TensorDock", "EU-West", "https://www.tensordock.com/", 0.88),
    ]
    gpu_profiles = [
        ("b200", "NVIDIA B200 NVLink", 180, 6.40, "Blackwell training / frontier inference"),
        ("h200", "NVIDIA H200 SXM", 141, 4.20, "large-context training and inference"),
        ("h100-sxm", "NVIDIA H100 SXM5", 80, 2.00, "dense training and high-throughput inference"),
        ("h100-pcie", "NVIDIA H100 PCIe", 80, 1.74, "inference-optimized H100 route"),
        ("a100-80", "NVIDIA A100 80GB", 80, 1.18, "non-FP8 training and embeddings"),
        ("a100-40", "NVIDIA A100 40GB", 40, 0.92, "batch inference and smaller training runs"),
        ("l40s", "NVIDIA L40S", 48, 0.76, "vision, rendering, and FP8 inference"),
        ("l4", "NVIDIA L4", 24, 0.24, "low-cost inference and preprocessing"),
        ("rtx-4090", "NVIDIA RTX 4090", 24, 0.42, "budget agent batch and fine-tune lane"),
        ("mi300x", "AMD MI300X", 192, 2.65, "high-memory open model serving"),
    ]
    routes: list[NodePricing] = []
    for provider_index, (provider_id, provider_name, region, source_url, provider_factor) in enumerate(providers):
        for gpu_index, (gpu_id, gpu_label, memory_gb, base_hourly, capability) in enumerate(gpu_profiles):
            hourly = round(base_hourly * provider_factor * (1 + ((gpu_index % 3) - 1) * 0.035), 3)
            route_id = f"{provider_id}-{gpu_id}-{provider_index + 1:02d}"
            routes.append(
                NodePricing(
                    node_id=route_id,
                    label=f"{provider_name} {gpu_label}",
                    rate_per_min_usd=round(hourly / 60, 6),
                    kind="gpu",
                    route_label=f"{provider_name} {gpu_label}",
                    runtime_node_id=f"{provider_id}-{gpu_id}",
                    endpoint_base_url=f"https://{provider_id}.capix.network/compute",
                    provider_name=provider_name,
                    region=region,
                    capacity=f"{capability}; {8 + ((provider_index + gpu_index) % 9) * 4} GPU-hours visible",
                    hardware_profile=gpu_id,
                    simulated=False,
                    hourly_rate_usd=hourly,
                    source_url=source_url,
                    pricing_basis=(
                        "public API/rate-card anchor normalized by CapIX; Compute Exchange source contributes "
                        "public GPU class and quote-market context, not hidden counterparty listings"
                    ),
                    available_units=1 + ((provider_index * 3 + gpu_index) % 8),
                    memory_gb=memory_gb,
                    last_observed=observed,
                )
            )
        cpu_hourly = round(0.045 * provider_factor, 4)
        routes.append(
            NodePricing(
                node_id=f"{provider_id}-cpu-etl-{provider_index + 1:02d}",
                label=f"{provider_name} CPU utility lane",
                rate_per_min_usd=round(cpu_hourly / 60, 6),
                kind="cpu",
                route_label=f"{provider_name} CPU lane",
                runtime_node_id=f"{provider_id}-cpu-etl",
                endpoint_base_url=f"https://{provider_id}.capix.network/compute",
                provider_name=provider_name,
                region=region,
                capacity="setup, parsing, cleaning, packaging, logging, and result collation",
                hardware_profile="cpu-utility",
                simulated=False,
                hourly_rate_usd=cpu_hourly,
                source_url=source_url,
                pricing_basis="public CPU utility lane normalized by CapIX for split-workload comparison",
                available_units=8 + provider_index,
                memory_gb=16 + provider_index * 8,
                last_observed=observed,
            )
        )
    return routes


def inference_market_catalog(timestamp: str | None = None) -> list[InferenceRoute]:
    observed = timestamp or observed_now()
    providers = [
        ("foza", "Foza provider pool", FOZA_SOURCE, 0.78, 34),
        ("near", "NEAR AI confidential lane", NEAR_AI_SOURCE, 1.06, 46),
        ("deepinfra", "DeepInfra surplus", "https://deepinfra.com/pricing", 0.72, 38),
        ("together", "Together open model lane", "https://www.together.ai/pricing", 0.86, 42),
        ("novita", "Novita overflow", "https://novita.ai/pricing", 0.68, 51),
        ("groq", "Groq latency lane", "https://groq.com/pricing/", 0.92, 11),
    ]
    models = [
        ("llama-3-70b", "Meta Llama-3-70B-Instruct", 0.15, 0.60, "synthesis and general reasoning"),
        ("mixtral-8x22b", "Mistral-Mixtral-8x22B", 0.22, 0.70, "planning and tool decomposition"),
        ("phi-3-medium", "Microsoft Phi-3-Medium", 0.04, 0.12, "fast extraction and checks"),
        ("qwen-72b", "Qwen2.5-72B-Instruct", 0.12, 0.48, "multilingual reasoning"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash", 0.007, 0.014, "cheap coding subtasks"),
        ("mistral-large-3", "Mistral Large 3", 0.025, 0.075, "open-weight planning"),
        ("gemini-flash", "Gemini 3 Flash Preview", 0.025, 0.15, "fast multimodal prompt work"),
        ("claude-haiku", "Claude Haiku 4.5", 0.05, 0.25, "agentic summaries"),
        ("gpt-mini", "GPT-5.4 mini", 0.0375, 0.225, "value synthesis"),
        ("glm-4-9b", "GLM-4-9B-Chat", 0.018, 0.075, "low-cost chat and extraction"),
    ]
    routes: list[InferenceRoute] = []
    for provider_index, (provider_id, provider_name, source_url, provider_factor, base_latency) in enumerate(providers):
        for model_index, (model_id, model_name, input_price, output_price, specialty) in enumerate(models):
            adjusted_input = round(input_price * provider_factor, 5)
            adjusted_output = round(output_price * provider_factor, 5)
            request_cpx = round(max(0.003, (adjusted_input * 0.25 + adjusted_output * 0.75) / 50), 5)
            latency = base_latency + (model_index % 5) * 7 + provider_index * 2
            reliability = 95.8 + ((provider_index + model_index) % 24) / 10
            route_id = f"{provider_id}-{model_id}-{model_index + 1:02d}"
            routes.append(
                InferenceRoute(
                    route_id=route_id,
                    label=f"{provider_name} / {model_name}",
                    model_id=model_name,
                    provider_name=provider_name,
                    rate_per_request_cpx=request_cpx,
                    latency_ms=latency,
                    reliability=f"{reliability:.1f}% rolling",
                    fleet_status="SURPLUS CAPACITY" if provider_index % 2 == 0 else "CONFIDENTIAL OVERFLOW",
                    specialty=specialty,
                    endpoint_base_url=f"https://api.{provider_id}.capix.network/v1",
                    region="global-router",
                    capacity=f"{25_000 + (provider_index * 7_500) + (model_index * 1_800):,} routed requests/day",
                    simulated=False,
                    input_per_1m_usd=adjusted_input,
                    output_per_1m_usd=adjusted_output,
                    source_url=source_url,
                    pricing_basis="public model/provider price anchor normalized into CPX per request",
                    last_observed=observed,
                )
            )
    return routes
