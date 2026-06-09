from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .schemas import DEMO_INFERENCE_ROUTES, DEMO_NODES, InferenceRoute, NodePricing, normalize_inference_routes, normalize_nodes


@dataclass(frozen=True)
class NodePricingResult:
    nodes: list[NodePricing]
    source: str
    warnings: list[str]


@dataclass(frozen=True)
class InferenceRouteResult:
    routes: list[InferenceRoute]
    source: str
    warnings: list[str]


class MongoDbMcpClient:
    """Small MongoDB MCP boundary with direct Mongo and deterministic demo fallbacks."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        database: str | None = None,
        collection: str | None = None,
        find_tool: str | None = None,
        timeout_seconds: float = 6,
    ) -> None:
        self.url = (url or os.getenv("MONGODB_MCP_URL") or "").strip()
        self.token = (token or os.getenv("MONGODB_MCP_TOKEN") or "").strip()
        self.database = database or os.getenv("MONGODB_MCP_DATABASE") or os.getenv("MONGODB_DB") or "capix_compute_db"
        self.collection = collection or os.getenv("MONGODB_MCP_NODES_COLLECTION") or os.getenv("MONGODB_NODES_COLLECTION") or "nodes"
        self.inference_collection = os.getenv("MONGODB_MCP_INFERENCE_COLLECTION") or os.getenv("MONGODB_INFERENCE_COLLECTION") or "inference_routes"
        self.find_tool = find_tool or os.getenv("MONGODB_MCP_FIND_TOOL") or "find"
        self.timeout_seconds = timeout_seconds
        self.mongo_uri = (os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "").strip()

    def get_node_pricing(self) -> NodePricingResult:
        warnings: list[str] = []
        if self.url:
            try:
                raw_nodes = self._call_find_tool()
                return NodePricingResult(normalize_nodes(raw_nodes), "mongodb-mcp", [])
            except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
                warnings.append(f"MongoDB MCP unavailable. {error}")

        if self.mongo_uri:
            try:
                raw_nodes = self._call_direct_mongo()
                return NodePricingResult(normalize_nodes(raw_nodes), "mongodb-direct", warnings)
            except (OSError, ValueError, ImportError) as error:
                warnings.append(f"Direct MongoDB unavailable. {error}")

        if not self.url:
            warnings.append("MongoDB MCP URL not configured.")
        if not self.mongo_uri:
            warnings.append("MONGO_URI not configured.")
        return NodePricingResult(self._market_nodes(), "market-seed", [*warnings, "Using bundled market-depth compute catalog."])

    def get_inference_routes(self) -> InferenceRouteResult:
        warnings: list[str] = []
        if self.url:
            try:
                raw_routes = self._call_find_tool(collection=self.inference_collection)
                return InferenceRouteResult(normalize_inference_routes(raw_routes), "mongodb-mcp", [])
            except (OSError, ValueError, urllib.error.URLError, TimeoutError) as error:
                warnings.append(f"MongoDB MCP unavailable. {error}")

        if self.mongo_uri:
            try:
                raw_routes = self._call_direct_mongo(collection=self.inference_collection)
                return InferenceRouteResult(normalize_inference_routes(raw_routes), "mongodb-direct", warnings)
            except (OSError, ValueError, ImportError) as error:
                warnings.append(f"Direct MongoDB unavailable. {error}")

        if not self.url:
            warnings.append("MongoDB MCP URL not configured.")
        if not self.mongo_uri:
            warnings.append("MONGO_URI not configured.")
        return InferenceRouteResult(self._market_inference_routes(), "market-seed", [*warnings, "Using bundled market-depth inference catalog."])

    @staticmethod
    def _market_nodes() -> list[NodePricing]:
        try:
            from .catalogs import compute_market_catalog

            return compute_market_catalog()
        except Exception:
            return DEMO_NODES

    @staticmethod
    def _market_inference_routes() -> list[InferenceRoute]:
        try:
            from .catalogs import inference_market_catalog

            return inference_market_catalog()
        except Exception:
            return DEMO_INFERENCE_ROUTES

    def _call_find_tool(self, collection: str | None = None) -> Any:
        session_id = self._initialize_mcp_session()
        request_id = f"capix-{int(time.time() * 1000)}"
        target_collection = collection or self.collection
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": self.find_tool,
                "arguments": {
                    "database": self.database,
                    "collection": target_collection,
                    "filter": {},
                    "projection": {"_id": 0},
                    "limit": 200,
                },
            },
        }
        return self._extract_nodes_from_mcp_response(self._post_mcp(payload, session_id=session_id))

    def _initialize_mcp_session(self) -> str | None:
        request_id = f"capix-init-{int(time.time() * 1000)}"
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "capix-router-mcp", "version": "0.1.0"},
            },
        }
        _, session_id = self._post_mcp(payload, include_session=True)
        initialized = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        self._post_mcp(initialized, session_id=session_id, expect_response=False)
        return session_id

    def _post_mcp(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
        include_session: bool = False,
        expect_response: bool = True,
    ) -> Any:
        data = json.dumps(payload).encode("utf-8")
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        if session_id:
            headers["mcp-session-id"] = session_id

        request = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
            response_session_id = response.headers.get("mcp-session-id")
        if not expect_response:
            return None
        parsed = self._parse_mcp_response_body(body)
        if include_session:
            return parsed, response_session_id
        return parsed

    def _call_direct_mongo(self, collection: str | None = None) -> Any:
        try:
            from pymongo import MongoClient
        except ImportError as error:
            raise ImportError("pymongo is not installed") from error

        client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=int(self.timeout_seconds * 1000))
        try:
            return list(client[self.database][collection or self.collection].find({}, {"_id": 0}))
        finally:
            client.close()

    @staticmethod
    def _parse_mcp_response_body(body: str) -> Any:
        stripped = body.strip()
        if not stripped:
            return {}
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)

        events: list[str] = []
        current: list[str] = []
        for line in stripped.splitlines():
            if not line:
                if current:
                    events.append("\n".join(current))
                    current = []
                continue
            if line.startswith("data:"):
                current.append(line.removeprefix("data:").strip())
        if current:
            events.append("\n".join(current))
        for event in events:
            parsed = json.loads(event)
            if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                return parsed
        raise ValueError("MongoDB MCP response did not contain a JSON-RPC message")

    @staticmethod
    def _extract_nodes_from_mcp_response(payload: Any) -> Any:
        result = payload.get("result") if isinstance(payload, dict) else payload
        if isinstance(result, dict) and result.get("isError"):
            messages: list[str] = []
            content = result.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        messages.append(item["text"])
            raise ValueError("MongoDB MCP returned an error. " + " ".join(messages))
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("documents", "nodes", "data"):
                if isinstance(result.get(key), list):
                    return result[key]
            content = result.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if isinstance(item.get("json"), list):
                        return item["json"]
                    text = item.get("text")
                    if isinstance(text, str):
                        try:
                            parsed = json.loads(text)
                        except json.JSONDecodeError:
                            try:
                                parsed = MongoDbMcpClient._extract_json_array_from_text(text)
                            except json.JSONDecodeError:
                                continue
                        if isinstance(parsed, list):
                            return parsed
                        if isinstance(parsed, dict):
                            for key in ("documents", "nodes", "data"):
                                if isinstance(parsed.get(key), list):
                                    return parsed[key]
        raise ValueError("MongoDB MCP response did not contain node documents")

    @staticmethod
    def _extract_json_array_from_text(text: str) -> Any:
        start = text.find("[")
        if start < 0:
            raise json.JSONDecodeError("No JSON array found", text, 0)
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
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
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    parsed = json.loads(text[start : index + 1])
                    if isinstance(parsed, list):
                        return parsed
                    break
        raise json.JSONDecodeError("No complete JSON array found", text, start)
