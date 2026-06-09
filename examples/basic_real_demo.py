# capix-real-demo
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
