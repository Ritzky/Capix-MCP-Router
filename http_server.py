from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from router.agent import split_and_route_job_for_track
from router.mongodb_mcp_client import MongoDbMcpClient
from router.policy import paid_route_key_from_headers


def router_token() -> str:
    return (os.getenv("CAPIX_ROUTER_TOKEN") or os.getenv("ROUTER_TOKEN") or "").strip()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("cache-control", "no-store")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class CapixRouterHandler(BaseHTTPRequestHandler):
    server_version = "CapIXRouterHTTP/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib handler API.
        if os.getenv("CAPIX_ROUTER_ACCESS_LOG", "false").lower() == "true":
            super().log_message(format, *args)

    def _authorized(self) -> bool:
        expected = router_token()
        if not expected:
            return True
        header = self.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        return token == expected

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON object body is required.")
        return parsed

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        path = urlparse(self.path).path
        if path == "/health":
            return json_response(self, 200, {"ok": True, "service": "capix-router-mcp"})
        if path == "/nodes":
            if not self._authorized():
                return json_response(self, 401, {"error": "Unauthorized router request."})
            result = MongoDbMcpClient().get_node_pricing()
            inference = MongoDbMcpClient().get_inference_routes()
            return json_response(self, 200, {
                "nodes": [node.to_dict() for node in result.nodes],
                "inference_routes": [route.to_dict() for route in inference.routes],
                "source": result.source if result.source == inference.source else {"compute": result.source, "inference": inference.source},
                "warnings": [*result.warnings, *inference.warnings],
            })
        return json_response(self, 404, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        path = urlparse(self.path).path
        if path not in {"/smart-route", "/route"}:
            return json_response(self, 404, {"error": "Not found."})
        if not self._authorized():
            return json_response(self, 401, {"error": "Unauthorized router request."})
        try:
            body = self._json_body()
            track = "inference" if body.get("track") == "inference" else "compute"
            content = str(body.get("prompt_content") or body.get("prompt") or body.get("code_content") or body.get("script") or "")
            if not content.strip():
                return json_response(self, 400, {"error": "prompt_content, code_content, prompt, or script is required."})
            setup_script = str(body.get("setup_script") or body.get("requirements_text") or "")
            language = str(body.get("language") or ("prompt" if track == "inference" else "python"))
            bundle_file_name = str(body.get("bundle_file_name") or "")
            paid_route_key = paid_route_key_from_headers(self.headers, body)
            return json_response(self, 200, split_and_route_job_for_track(
                content,
                track,
                setup_script=setup_script,
                language=language,
                bundle_file_name=bundle_file_name,
                paid_route_key=paid_route_key,
            ))
        except PermissionError as error:
            return json_response(self, 402, {"error": str(error)})
        except Exception as error:  # pragma: no cover - keeps the demo service readable in production logs.
            return json_response(self, 500, {"error": str(error)})


def main() -> None:
    host = os.getenv("CAPIX_ROUTER_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("CAPIX_ROUTER_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), CapixRouterHandler)
    print(f"CapIX Router HTTP server listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
