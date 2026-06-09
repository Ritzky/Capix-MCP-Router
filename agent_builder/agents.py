from __future__ import annotations

import os
from functools import cached_property

from .tools import (
    build_controlled_execution_plan,
    inspect_compute_route_book,
    inspect_inference_route_book,
    route_compute_package,
    route_inference_prompt,
)

try:
    from google.adk.agents import LlmAgent
    from google.adk.models import Gemini
    from google.genai import Client
except ImportError as error:  # pragma: no cover - ADK is optional for router tests.
    LlmAgent = None  # type: ignore[assignment]
    Gemini = object  # type: ignore[assignment,misc]
    Client = None  # type: ignore[assignment]
    ADK_IMPORT_ERROR = error
else:
    ADK_IMPORT_ERROR = None


class GlobalGemini(Gemini):  # type: ignore[misc]
    """Pin Gemini model calls to Vertex AI global for Agent Engine demos."""

    @cached_property
    def api_client(self):  # type: ignore[no-untyped-def]
        kwargs = {"vertexai": True, "location": "global"}
        api_key = os.getenv("GOOGLE_CLOUD_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            kwargs["api_key"] = api_key
        return Client(**kwargs)


def _model() -> GlobalGemini:
    return GlobalGemini(model=os.getenv("CAPIX_ADK_MODEL", "gemini-2.5-flash"))


def _require_adk() -> None:
    if LlmAgent is None:
        raise RuntimeError("google-adk is not installed. Install requirements-agent-builder.txt to run ADK agents.") from ADK_IMPORT_ERROR


def build_agents():
    """Build the CapIX compute/inference router agents for Google Agent Builder."""
    _require_adk()

    compute_agent = LlmAgent(
        name="CapIX_Compute_Router_Agent",
        model=_model(),
        description="Routes uploaded compute packages across MongoDB-backed CPU/GPU capacity.",
        instruction=(
            "You are the CapIX Compute Router. Use the tools to inspect route supply, split uploaded scripts, "
            "and explain savings versus running the full workload on the highest compute lane the script required. "
            "Do not claim private wallet settlement or Oracle execution happened; the private CapIX app handles that."
        ),
        tools=[inspect_compute_route_book, route_compute_package, build_controlled_execution_plan],
    )

    inference_agent = LlmAgent(
        name="CapIX_Inference_Router_Agent",
        model=_model(),
        description="Routes complex prompts across MongoDB-backed surplus inference capacity.",
        instruction=(
            "You are the CapIX Inference Router. Use the tools to inspect model-provider routes, decompose prompts, "
            "and rank lanes by price, latency, reliability, and capacity. Keep copy concise and demo-safe."
        ),
        tools=[inspect_inference_route_book, route_inference_prompt],
    )

    root_agent = LlmAgent(
        name="CapIX_Router_Agent",
        model=_model(),
        description="Coordinates compute and inference routing for CapIX Smart Route demos.",
        instruction=(
            "Decide whether the user needs compute package routing or inference prompt routing. "
            "Use the specialist tools, return JSON-compatible route summaries, and keep the user in control. "
            "Never expose secrets, treasury details, private host credentials, or private API tokens."
        ),
        sub_agents=[compute_agent, inference_agent],
        tools=[inspect_compute_route_book, inspect_inference_route_book],
    )

    return root_agent, compute_agent, inference_agent


if LlmAgent is not None:
    root_agent, compute_router_agent, inference_router_agent = build_agents()
else:  # pragma: no cover - gives Agent Builder a clear import failure when dependencies are missing.
    root_agent = None
    compute_router_agent = None
    inference_router_agent = None
