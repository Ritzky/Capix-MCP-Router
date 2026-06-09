# CapIX Router MCP

Open-source Smart Route layer for CapIX. It uses MongoDB MCP as the hosted node and pricing registry, then asks Gemini to split a workload between cheaper CPU capacity and higher-power GPU capacity.

This repository is intentionally separate from the private CapIX protocol app. It does not contain wallet settlement, treasury keys, host-agent credentials, admin routes, or production delivery code.

## What It Does

- Reads available compute node pricing and inference provider lanes from MongoDB MCP.
- Splits uploaded code into CPU/GPU allocations, or complex prompts into routed inference subtasks.
- Uses Gemini for planning when `GEMINI_API_KEY` is configured.
- Falls back to deterministic routing when Gemini or MongoDB MCP is unavailable.
- Returns a quote calculated from the active route book: highest-required-compute baseline versus the optimized CPU/GPU or model-provider split.
- Compares compute savings against running the whole script on the highest compute lane the script actually required.
- Exposes an optional JSON HTTP endpoint for the private CapIX app at `/smart-route`.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m compileall .
pytest -q
```

Optional Google Agent Builder / ADK layer:

```bash
pip install -r requirements-agent-builder.txt
python -m agent_builder.demo
```

For a short judging video path, see [DEMO_RECORDING_GUIDE.md](DEMO_RECORDING_GUIDE.md).

Run the optional FastMCP wrapper:

```bash
python server.py
```

Run the private-app JSON bridge used by Vercel:

```bash
CAPIX_ROUTER_PORT=8788 python http_server.py
```

## Hosted Deployment

The recommended hackathon deployment is two hosted services:

```text
Private CapIX app on Vercel
  -> POST CAPIX_ROUTER_URL/smart-route
  -> CapIX Router service on Google Cloud Run
  -> MongoDB MCP HTTP service on Google Cloud Run
  -> MongoDB Atlas capix_compute_db
```

This keeps the browser away from MongoDB, Gemini, private policy, and MCP credentials. The Vercel app only calls the router. The router calls the MongoDB MCP server. If you want the demo to prove MCP usage, set `MONGODB_MCP_URL` on the router and do not set `MONGO_URI` on the router service.

### 1. Seed MongoDB Atlas

Seed the public-safe route books first:

```bash
export MONGO_URI="<atlas-driver-connection-string>"
python3 seed_nodes.py --prune
```

Expected collections:

```text
capix_compute_db.nodes             66 compute routes
capix_compute_db.inference_routes  60 inference routes
```

Smoke check:

```bash
python - <<'PY'
from router.mongodb_mcp_client import MongoDbMcpClient
client = MongoDbMcpClient()
print(client.get_node_pricing().source, len(client.get_node_pricing().nodes))
print(client.get_inference_routes().source, len(client.get_inference_routes().routes))
PY
```

If only `MONGO_URI` is set locally, the source should be `mongodb-direct`. After the MCP server is hosted and `MONGODB_MCP_URL` is set, the source should become `mongodb-mcp`.

### 2. Deploy MongoDB MCP To Cloud Run

Create Google Secret Manager entries. Use your real values locally; do not commit them:

```bash
printf '%s' "$MONGO_URI" | gcloud secrets create capix-mongo-uri --data-file=-
printf '%s' "$GEMINI_API_KEY" | gcloud secrets create capix-gemini-api-key --data-file=-
printf '%s' "$CAPIX_ROUTER_TOKEN" | gcloud secrets create capix-router-token --data-file=-
printf '%s' "$CAPIX_PRIVATE_POLICY_TOKEN" | gcloud secrets create capix-private-policy-token --data-file=-
```

If a secret already exists, update it instead:

```bash
printf '%s' "$MONGO_URI" | gcloud secrets versions add capix-mongo-uri --data-file=-
```

Build the official MongoDB MCP server container:

```bash
export PROJECT_ID="<google-cloud-project-id>"
export REGION="us-central1"
export REPOSITORY="capix"

gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format=docker \
  --location="$REGION" \
  --description="CapIX router images"

gcloud auth configure-docker "$REGION-docker.pkg.dev"

docker build \
  -f Dockerfile.mongodb-mcp \
  -t "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-mongodb-mcp:latest" .

docker push "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-mongodb-mcp:latest"
```

Deploy it:

```bash
gcloud run deploy capix-mongodb-mcp \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-mongodb-mcp:latest" \
  --set-env-vars="MDB_MCP_TRANSPORT=http,MDB_MCP_READ_ONLY=true,MDB_MCP_HTTP_HOST=0.0.0.0,MDB_MCP_HTTP_BODY_RESPONSE_TYPE=json" \
  --set-secrets="MDB_MCP_CONNECTION_STRING=capix-mongo-uri:latest" \
  --allow-unauthenticated
```

The service URL will look like:

```text
https://capix-mongodb-mcp-xxxxx-uc.a.run.app
```

The MCP endpoint used by the router is:

```text
https://capix-mongodb-mcp-xxxxx-uc.a.run.app/mcp
```

Security note: for a public hackathon demo, keep the MongoDB Atlas user read-only and scoped only to `capix_compute_db`. For a stricter deployment, put the MCP service behind Cloud Run IAM or an API gateway and teach the router to mint Google identity tokens before calling it.

### 3. Deploy CapIX Router To Cloud Run

Build the router container:

```bash
docker build \
  -f Dockerfile \
  -t "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-router-mcp:latest" .

docker push "$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-router-mcp:latest"
```

Deploy it with MCP enabled:

```bash
gcloud run deploy capix-router-mcp \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/capix-router-mcp:latest" \
  --set-env-vars="MONGODB_MCP_URL=https://capix-mongodb-mcp-xxxxx-uc.a.run.app/mcp,MONGODB_MCP_FIND_TOOL=find,MONGODB_MCP_DATABASE=capix_compute_db,MONGODB_MCP_NODES_COLLECTION=nodes,MONGODB_MCP_INFERENCE_COLLECTION=inference_routes,CAPIX_REQUIRE_PAID_ROUTE_KEY=true,CAPIX_PRIVATE_POLICY_URL=https://capix.network/api/router/private-policy,CAPIX_USE_VERTEX_AI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=gemini-2.5-flash" \
  --set-secrets="CAPIX_ROUTER_TOKEN=capix-router-token:latest,CAPIX_PRIVATE_POLICY_TOKEN=capix-private-policy-token:latest" \
  --allow-unauthenticated
```

For the Google Cloud demo, prefer `CAPIX_USE_VERTEX_AI=true` and omit `GEMINI_API_KEY`; Cloud Run will call Gemini through Vertex AI with its service identity. Keep `GEMINI_API_KEY` only for local developer runs. Do not set `MONGO_URI` on this router service if the goal is to demonstrate MCP. `MONGO_URI` is only a fallback.

Smoke check:

```bash
export ROUTER_URL="https://capix-router-mcp-xxxxx-uc.a.run.app"
export CAPIX_ROUTER_TOKEN="<same-token>"

curl "$ROUTER_URL/health"

curl "$ROUTER_URL/nodes" \
  -H "authorization: Bearer $CAPIX_ROUTER_TOKEN" \
  | python -m json.tool | head -80
```

The `/nodes` response should show:

```json
{
  "source": "mongodb-mcp"
}
```

If it says `mongodb-direct`, remove `MONGO_URI` from the router service. If it says `market-seed`, the router cannot reach MongoDB MCP.

### 4. Connect The Private CapIX App

Set these on the private Vercel project:

```text
CAPIX_USE_SMART_ROUTER=true
CAPIX_ROUTER_URL=https://capix-router-mcp-xxxxx-uc.a.run.app/smart-route
CAPIX_ROUTER_TOKEN=<same-token-as-router>
CAPIX_ROUTER_KEY_SECRET=<private-route-key-derivation-secret>
CAPIX_PRIVATE_POLICY_TOKEN=<same-private-policy-token-used-by-router>
```

Redeploy Vercel after setting env vars:

```bash
npx vercel deploy --prod
```

The private app flow becomes:

```text
Buy Smart Route
  -> Phantom pays 0.01 CPX router deposit
  -> /api/router/smart-route mints a short-lived route key
  -> Vercel calls hosted CapIX Router
  -> hosted Router calls MongoDB MCP
  -> Gemini returns the CPU/GPU or model-provider allocation
```

### 5. End-To-End Demo Test

From the private app, open:

```text
https://capix.network/buy?track=compute
```

Then:

1. Choose `Smart Route`.
2. Load `Standard split demo`.
3. Pay the `0.01 CPX & Route` deposit.
4. Confirm the receipt source is the hosted router and the allocation shows CPU/GPU lanes.
5. Run the demo handoff or download `output.txt`.

For the Google video, also show this terminal proof:

```bash
curl "$ROUTER_URL/nodes" -H "authorization: Bearer $CAPIX_ROUTER_TOKEN" \
  | python -m json.tool
```

The judging line is:

> MongoDB MCP is the route registry tool layer. Gemini plans the split. CapIX gates access with CPX before the private router key is issued.

## MongoDB MCP Boundary

The router expects MongoDB MCP to expose a tool capable of reading:

```json
{
  "database": "capix_compute_db",
  "collection": "nodes",
  "filter": {},
  "projection": { "_id": 0 }
}
```

The tool name defaults to `find` and can be changed with `MONGODB_MCP_FIND_TOOL`.

For inference routing, the same tool reads:

```json
{
  "database": "capix_compute_db",
  "collection": "inference_routes",
  "filter": {},
  "projection": { "_id": 0 }
}
```

If the MCP endpoint is not configured or unavailable, the router can read MongoDB directly through `MONGO_URI`. If neither is available, a bundled offline market catalog is used so the hackathon demo remains reliable while clearly reporting fallback status.

If `MONGO_URI` is configured but `MONGODB_MCP_URL` is not, the router reads `capix_compute_db.nodes` directly from MongoDB. That keeps demos working while the official MongoDB MCP HTTP service is being deployed.

Start the official MongoDB MCP server in HTTP mode:

```bash
export MDB_MCP_CONNECTION_STRING="$MONGO_URI"
export MDB_MCP_TRANSPORT=http
export MDB_MCP_READ_ONLY=true
export MDB_MCP_HTTP_PORT=8794
export MDB_MCP_HTTP_BODY_RESPONSE_TYPE=json
npx -y mongodb-mcp-server@latest
```

The default HTTP client URL is:

```text
http://127.0.0.1:8794/mcp
```

If the MCP server runs on an OCI VM for remote access, bind it only behind a protected reverse proxy:

```bash
export MDB_MCP_CONNECTION_STRING="$MONGO_URI"
export MDB_MCP_TRANSPORT=http
export MDB_MCP_READ_ONLY=true
export MDB_MCP_HTTP_HOST=127.0.0.1
export MDB_MCP_HTTP_PORT=8794
npx -y mongodb-mcp-server@latest
```

Then set:

```text
MONGODB_MCP_URL=https://router.capix.network/mcp
```

Keep the Atlas connection string quoted in shell commands. If the password contains reserved URI characters, use the Atlas-provided driver connection string or URL-encode the password before starting `mongodb-mcp-server`.

### Atlas Integrated AI Key

Atlas model/API keys are not MongoDB login credentials and are not used by the private CapIX wallet or settlement flow.

Use the Atlas integrated AI key only on the MCP host when enabling MongoDB MCP Vector Search / automatic embedding tools:

```bash
export MDB_MCP_VOYAGE_API_KEY="<atlas-integrated-ai-model-key>"
```

CapIX Smart Route code splitting still uses:

```bash
export GEMINI_API_KEY="<gemini-api-key>"
```

So the split is:

- `MONGO_URI` or `MDB_MCP_CONNECTION_STRING`: reads the `capix_compute_db.nodes` route registry.
- `MDB_MCP_VOYAGE_API_KEY`: optional Atlas integrated AI embedding/vector-search support.
- `GEMINI_API_KEY`: Smart Route CPU/GPU job planner.

Do not set `MDB_MCP_PREVIEW_FEATURES` by default in the demo service. The currently tested `mongodb-mcp-server@latest` build rejected `search` as a preview flag locally, while still accepting `MDB_MCP_VOYAGE_API_KEY`. Add preview flags only when the MCP server version you deploy explicitly requires them.

### Connect An AI Client

For a local AI client that supports MCP over stdio, use this shape and keep it outside the public repo:

```json
{
  "mcpServers": {
    "capix-mongodb": {
      "command": "npx",
      "args": ["-y", "mongodb-mcp-server@latest"],
      "env": {
        "MDB_MCP_CONNECTION_STRING": "<atlas-mongodb-connection-string>",
        "MDB_MCP_READ_ONLY": "true",
        "MDB_MCP_VOYAGE_API_KEY": "<atlas-integrated-ai-model-key>"
      }
    }
  }
}
```

For the hosted CapIX router, keep the official MCP server behind the private router service and point the router at:

```text
MONGODB_MCP_URL=https://router.capix.network/mcp
```

## OCI Autonomous DB Link

OCI Autonomous Database remains the private CapIX ledger/source-of-truth layer for wallet-bound sessions, CPX allocation records, lease metadata, and admin state. MongoDB is the public-safe MCP route registry.

Do not point MongoDB MCP at OCI Autonomous Database directly. Oracle Autonomous DB speaks Oracle SQL/TCPS; MongoDB MCP expects MongoDB. The bridge is a one-way sanitized sync:

```text
OCI Autonomous DB / private CapIX state
  -> /api/router/compute-snapshot
  -> pull_capix_snapshot.py
  -> MongoDB capix_compute_db.nodes
  -> MongoDB MCP / CapIX Router
  -> Gemini route split
```

The private CapIX app can use OCI Autonomous DB by setting:

```text
CAPIX_DB_USER=ADMIN
CAPIX_DB_PASSWORD=<autonomous-db-admin-password>
CAPIX_DB_DSN=capixdb_high
CAPIX_ATP_WALLET_PATH=<unzipped-wallet-directory>
```

The router only receives the sanitized node snapshot, not Oracle wallet files, admin credentials, treasury keys, SSH keys, or bearer tokens.

## Market Route Books

`seed_nodes.py --prune` writes the current market-depth catalog into MongoDB:

- `capix_compute_db.nodes`: 66 compute routes, including 60 GPU lanes and 6 CPU utility lanes.
- `capix_compute_db.inference_routes`: 60 inference routes, spanning 6 provider groups and 10 model classes.

The router computes savings from those active rows. Compute compares the optimized split against running the full script on the highest compute lane the script actually required. Inference compares routed subtasks against sending every subtask through the highest-cost premium route.

## Demo Scripts

`examples/` includes three judging-ready scripts:

- `basic_real_demo.py`: safe marked Python script that the private Oracle Node Agent is allowed to execute for real on the CPU lane.
- `demo_script.py`: standard CPU/GPU split with data cleaning plus NumPy matrix work.
- `complex_training_mock.py`: training-style package used for controlled execution proof and `output.txt` generation.

## One-Time CapIX Compute Sync

The private CapIX app can export a public-safe compute route snapshot once, then this repo uploads that snapshot into MongoDB. The same seed command also writes the bundled inference route book into `capix_compute_db.inference_routes`. After that, MongoDB MCP or direct MongoDB is the router's data source.

From the private app:

```bash
cd ../capix-protocol
node scripts/export-smart-router-compute.mjs
```

Then from this public router repo:

```bash
cd ../capix-router-mcp
MONGO_URI="mongodb://localhost:27017/" python3 seed_nodes.py --snapshot examples/capix_compute_snapshot.json
```

Or pull from the private CapIX API and seed MongoDB in one step:

```bash
CAPIX_SNAPSHOT_URL="https://capix.network/api/router/compute-snapshot" \
CAPIX_ROUTER_SYNC_TOKEN="<private-sync-token>" \
MONGO_URI="mongodb://localhost:27017/" \
python3 pull_capix_snapshot.py
```

The snapshot intentionally contains only demo route metadata: route IDs, public demo endpoint URLs, region, simulated hardware profile, rates, and sanitized listing summaries. It does not contain private SSH keys, wallet secrets, admin tokens, treasury keys, bearer tokens, or host credentials.

## Paid Route Key Boundary

This repository is the open-source router skeleton. It exposes the MCP shape, MongoDB route-book integration, Gemini/Agent Builder entry points, deterministic fallbacks, and testable demo behavior. It intentionally does not contain private CapIX scoring weights, production prompts, settlement policy, or abuse-prevention rules.

For production hosting, set:

```text
CAPIX_REQUIRE_PAID_ROUTE_KEY=true
CAPIX_PRIVATE_POLICY_URL=https://capix.network/api/router/private-policy
CAPIX_PRIVATE_POLICY_TOKEN=<private-service-token>
```

The private CapIX app should take a CPX deposit first, mint a short-lived paid route key, then call this router with:

```text
x-capix-paid-route-key: <ephemeral-key>
```

or:

```json
{
  "paid_route_key": "<ephemeral-key>"
}
```

When the key is present, the router can request private runtime policy from `CAPIX_PRIVATE_POLICY_URL`. When the key is missing and `CAPIX_REQUIRE_PAID_ROUTE_KEY=true`, `/smart-route` returns `402` and does not route the job. In local tests, the key is optional so judges can run the public repo without private CapIX credentials.

## Private CapIX Integration

The private app should call this router from a server-side API route only. Browsers should never call MongoDB MCP or Gemini directly.

Recommended private API:

```text
POST /api/router/smart-route
```

The private app remains responsible for Phantom authorization, CPX settlement display, compute delivery, and inference delivery.

Recommended Vercel env:

```text
CAPIX_USE_SMART_ROUTER=true
CAPIX_ROUTER_URL=https://router.capix.network/smart-route
CAPIX_ROUTER_TOKEN=<same-token-as-router>
CAPIX_ROUTER_KEY_SECRET=<private-key-derivation-secret>
```

The private app sends a packaged job from its server-side API route:

```json
{
  "track": "compute",
  "language": "python",
  "code_content": "entry script text",
  "setup_script": "requirements.txt or setup commands",
  "bundle_file_name": "optional-job.zip",
  "cpx_usd": 0.05,
  "paid_route_key": "ephemeral-key-derived-after-CPX-deposit"
}
```

The demo story should read as:

- Compute: CapIX reads the MongoDB route book, accepts an entry script plus setup/requirements text, routes setup and cleaning to CPU lanes, routes numeric kernels to compatible GPU lanes, compares against running the full package on the highest compute lane the script required, then returns the optimized quote.
- Inference: MongoDB MCP exposes surplus provider lanes, the router breaks a complex prompt into extraction, planning, synthesis, and verification subtasks, then ranks providers by price, latency, reliability, and capacity.
- Execution: the private app owns wallet authorization and Oracle Node Agent delivery. The basic marked Python demo can run for real on the Oracle CPU lane. Standard and complex demos use controlled `output.txt` generation after real routing so video capture stays reliable and arbitrary uploaded code is not executed on public demo hosts.

## Google Agent Builder

`agent_builder/` contains an optional ADK wrapper for two agents:

- `CapIX_Compute_Router_Agent`: inspects MongoDB-backed compute routes, splits packages across CPU/GPU lanes, and explains cost savings.
- `CapIX_Inference_Router_Agent`: inspects MongoDB-backed inference routes, decomposes prompts, and selects provider lanes by price, latency, reliability, and capacity.

The ADK layer imports only public-safe router tools. It does not know private settlement keys, treasury routes, admin APIs, Oracle SSH credentials, or host-agent tokens.
