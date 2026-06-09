from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from seed_nodes import seed_nodes


def env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def pull_snapshot(url: str, token: str) -> dict:
    headers = {"accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("nodes"), list):
        raise SystemExit("CapIX snapshot API did not return an object with a nodes array.")
    return payload


def main() -> None:
    url = env("CAPIX_SNAPSHOT_URL", "http://localhost:3000/api/router/compute-snapshot")
    token = env("CAPIX_ROUTER_SYNC_TOKEN")
    mongo_uri = env("MONGO_URI")
    db_name = env("MONGODB_DB", "capix_compute_db")
    collection_name = env("MONGODB_NODES_COLLECTION", "nodes")
    output_path = Path(env("CAPIX_SNAPSHOT_OUT", "examples/capix_compute_snapshot.json"))
    dry_run = "--dry-run" in sys.argv

    snapshot = pull_snapshot(url, token)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")

    if dry_run or not mongo_uri:
        print(json.dumps(snapshot["nodes"], indent=2))
        print(f"Wrote snapshot to {output_path}. MONGO_URI not set or --dry-run used; MongoDB was not changed.")
        return

    count = seed_nodes(snapshot["nodes"], mongo_uri, db_name, collection_name)
    print(f"Pulled CapIX snapshot from {url}, wrote {output_path}, and seeded {count} route nodes into {db_name}.{collection_name}.")


if __name__ == "__main__":
    main()
