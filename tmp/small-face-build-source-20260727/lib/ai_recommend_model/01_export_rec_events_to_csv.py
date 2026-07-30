import csv
from datetime import datetime, timezone, timedelta
from google.cloud import firestore

PROJECT_ID = "seolleyeon"
COLLECTION = "recEvents"
OUT = "events.csv"

# 예: 최근 120일만 export
LOOKBACK_DAYS = 120
now = datetime.now(timezone.utc)
start = now - timedelta(days=LOOKBACK_DAYS)

db = firestore.Client(project=PROJECT_ID)

q = db.collection(COLLECTION).where("eventTime", ">=", start)

rows = []
for doc in q.stream():
    d = doc.to_dict() or {}
    user_id = d.get("userId")
    item_id = d.get("candidateUserId")
    event = d.get("type")
    ts = d.get("eventTime")
    if not user_id or not item_id or not event or not ts:
        continue
    # ts is datetime
    if isinstance(ts, datetime):
        ts = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        continue
    rows.append([str(user_id), str(item_id), str(event), ts])

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["user_id", "item_id", "event", "ts"])
    w.writerows(rows)

print(f"exported {len(rows)} rows to {OUT}")