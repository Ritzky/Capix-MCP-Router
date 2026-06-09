from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime policy injected by the private CapIX app after a paid deposit."""

    instructions: str
    source: str


SKELETON_POLICY = RuntimePolicy(
    instructions=(
        "Use the open-source CapIX skeleton policy: route setup, parsing, cleaning, logging, "
        "and result collation to CPU capacity; route matrix, tensor, model-training, and "
        "repeated numeric kernels to GPU capacity. Do not expose private marketplace weights."
    ),
    source="open-source-skeleton",
)


def require_paid_route_key() -> bool:
    return os.getenv("CAPIX_REQUIRE_PAID_ROUTE_KEY", "false").lower() == "true"


def paid_route_key_from_headers(headers: object, body: dict[str, object]) -> str:
    header_value = ""
    if hasattr(headers, "get"):
        header_value = str(headers.get("x-capix-paid-route-key", "") or "").strip()
    body_value = str(body.get("paid_route_key") or body.get("paidRouteKey") or "").strip()
    return header_value or body_value


def assert_paid_route_key(paid_route_key: str) -> None:
    if require_paid_route_key() and not paid_route_key:
        raise PermissionError("CapIX Smart Route requires a paid route key minted by the private app after CPX deposit.")


def load_runtime_policy(paid_route_key: str = "") -> RuntimePolicy:
    """Fetch proprietary routing guidance only when the private app grants a paid key.

    The public repository deliberately keeps the default policy conservative and generic.
    Production deployments can set CAPIX_PRIVATE_POLICY_URL and CAPIX_PRIVATE_POLICY_TOKEN;
    the private CapIX app then returns route weights, prompt clauses, or scorer hints for
    the paid route key without committing those rules to the open-source repo.
    """

    assert_paid_route_key(paid_route_key)
    url = os.getenv("CAPIX_PRIVATE_POLICY_URL", "").strip()
    token = os.getenv("CAPIX_PRIVATE_POLICY_TOKEN", "").strip()
    if not url or not paid_route_key:
        return SKELETON_POLICY

    payload = json.dumps({"paid_route_key": paid_route_key}).encode("utf-8")
    headers = {"content-type": "application/json", "x-capix-paid-route-key": paid_route_key}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=4) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return SKELETON_POLICY

    instructions = str(parsed.get("instructions") or parsed.get("policy") or "").strip()
    if not instructions:
        return SKELETON_POLICY
    return RuntimePolicy(instructions=instructions[:4000], source="private-paid-policy")
