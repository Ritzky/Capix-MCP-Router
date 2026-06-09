from __future__ import annotations

import json

from .tools import build_controlled_execution_plan, route_compute_package, route_inference_prompt


BASIC_REAL_DEMO = """# capix-real-demo
orders = [
    {"region": "us-west", "status": "complete", "amount": "120.50"},
    {"region": "us-east", "status": "pending", "amount": "44.10"},
    {"region": "eu-west", "status": "complete", "amount": "88.00"},
]

clean_rows = []
for row in orders:
    if row["status"] == "complete":
        clean_rows.append(float(row["amount"]))

total = sum(clean_rows)
average = total / len(clean_rows)
print(f"CapIX real Oracle CPU demo complete rows={len(clean_rows)} total={total:.2f} avg={average:.2f}")
"""


STANDARD_SPLIT_DEMO = """import numpy as np

raw_rows = [{"status": "complete", "amount": "120.50"}, {"status": "pending", "amount": "44.10"}]
clean_rows = []
for row in raw_rows:
    if row["status"] == "complete":
        clean_rows.append(float(row["amount"]))

matrix_a = np.random.rand(1024, 1024)
matrix_b = np.random.rand(1024, 1024)
score = 0.0
for _ in range(20):
    score += float(np.dot(matrix_a, matrix_b).mean())

print(score, len(clean_rows))
"""


INFERENCE_PROMPT_DEMO = """Build an agent workflow for a support automation launch. Extract major incident themes, decide which checks need a cheap model versus a stronger reasoning model, draft the operator plan, and return a concise launch-review report."""


def main() -> None:
    compute = route_compute_package(STANDARD_SPLIT_DEMO, setup_script="numpy==2.1.3", language="python")
    inference = route_inference_prompt(INFERENCE_PROMPT_DEMO)
    print(json.dumps({
        "compute": compute,
        "controlled_execution_plan": build_controlled_execution_plan(compute),
        "inference": inference,
    }, indent=2))


if __name__ == "__main__":
    main()
