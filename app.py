import os
from pymongo import MongoClient
from datetime import datetime
import json

# 🔐 ENV
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("MONGO_URI not set")

client = MongoClient(MONGO_URI)
db = client["blazecloud_panel"]

collections = ["users", "bots", "services"]

SENSITIVE_FIELDS = {
    "github_token", "password", "token",
    "access_token", "refresh_token", "session"
}

def clean(doc):
    doc["_id"] = str(doc.get("_id"))

    for k in list(doc.keys()):
        if k in SENSITIVE_FIELDS:
            doc[k] = "HIDDEN"

    return doc

print("\n===== 🔥 DATABASE DUMP START =====\n")

for name in collections:
    col = db[name]
    print(f"\n📦 COLLECTION: {name.upper()}\n")

    docs = list(col.find().limit(20))  # limit for safety

    if not docs:
        print("No data\n")
        continue

    for d in docs:
        print(json.dumps(clean(d), indent=2))
        print("-" * 40)

print("\n===== ✅ DATABASE DUMP END =====\n")

# keep app alive (important for Railway)
while True:
    pass
