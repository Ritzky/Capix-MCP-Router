from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from router.catalogs import compute_market_catalog, inference_market_catalog
from router.schemas import DEMO_INFERENCE_ROUTES, DEMO_NODES


def load_nodes_from_snapshot(path: str | None):
    if not path:
        return [node.to_dict() for node in compute_market_catalog()]
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("nodes"), list):
        return payload["nodes"]
    if isinstance(payload, list):
        return payload
    raise SystemExit("Snapshot must be a JSON array or an object with a nodes array.")


def seed_nodes(nodes: list[dict], uri: str, db_name: str = "capix_compute_db", collection_name: str = "nodes", prune: bool = False) -> int:
    try:
        from pymongo import MongoClient
    except ImportError as error:
        raise SystemExit("pymongo is not installed. Run `pip install -r requirements.txt`.") from error

    client = MongoClient(uri)
    collection = client[db_name][collection_name]
    if prune:
        node_ids = [node["node_id"] for node in nodes]
        collection.delete_many({"node_id": {"$nin": node_ids}})
    for node in nodes:
        collection.update_one({"node_id": node["node_id"]}, {"$set": node}, upsert=True)
    return len(nodes)


def seed_inference_routes(routes: list[dict], uri: str, db_name: str = "capix_compute_db", collection_name: str = "inference_routes", prune: bool = False) -> int:
    try:
        from pymongo import MongoClient
    except ImportError as error:
        raise SystemExit("pymongo is not installed. Run `pip install -r requirements.txt`.") from error

    client = MongoClient(uri)
    collection = client[db_name][collection_name]
    if prune:
        route_ids = [route["route_id"] for route in routes]
        collection.delete_many({"route_id": {"$nin": route_ids}})
    for route in routes:
        collection.update_one({"route_id": route["route_id"]}, {"$set": route}, upsert=True)
    return len(routes)


def main() -> None:
    uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGODB_DB", "capix_compute_db")
    collection_name = os.getenv("MONGODB_NODES_COLLECTION", "nodes")
    inference_collection_name = os.getenv("MONGODB_INFERENCE_COLLECTION", "inference_routes")

    snapshot_path = sys.argv[sys.argv.index("--snapshot") + 1] if "--snapshot" in sys.argv else None
    prune = "--prune" in sys.argv
    nodes = load_nodes_from_snapshot(snapshot_path)

    if not uri:
        print(json.dumps({"nodes": nodes, "inference_routes": [route.to_dict() for route in inference_market_catalog()]}, indent=2))
        print("MONGO_URI is not set; printed demo nodes instead of writing to MongoDB.")
        return

    count = seed_nodes(nodes, uri, db_name, collection_name, prune=prune)
    inference_count = seed_inference_routes([route.to_dict() for route in inference_market_catalog()], uri, db_name, inference_collection_name, prune=prune)
    print(f"Seeded {count} CapIX demo nodes into {db_name}.{collection_name}.")
    print(f"Seeded {inference_count} CapIX inference routes into {db_name}.{inference_collection_name}.")
    if prune:
        print("Pruned stale route documents not present in the current market catalog.")


if __name__ == "__main__":
    main()
