import numpy as np


raw_rows = [
    {"region": "us-west", "status": "complete", "amount": "120.50"},
    {"region": "us-east", "status": "pending", "amount": "44.10"},
    {"region": "eu-west", "status": "complete", "amount": "88.00"},
]

clean_rows = []
for row in raw_rows:
    if row["status"] == "complete":
        clean_rows.append({"region": row["region"], "amount": float(row["amount"])})

matrix_a = np.random.rand(1024, 1024)
matrix_b = np.random.rand(1024, 1024)
score = 0.0
for _ in range(20):
    score += float(np.dot(matrix_a, matrix_b).mean())

print(f"Completed routed workload score={score:.4f} rows={len(clean_rows)}")
