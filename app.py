import os
import json
import requests
from pymongo import MongoClient

# 🔐 ENV
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise Exception("MONGO_URI not set")

client = MongoClient(MONGO_URI)
db = client["blazecloud_panel"]

SENSITIVE_FIELDS = {
    "github_token", "token",
    "access_token", "refresh_token", "session"
}

# ---------------- GITHUB CHECK ----------------

def check_github(token):
    if not token:
        return "❌ NOT CONNECTED"

    try:
        res = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5
        )
        if res.status_code == 200:
            return "✅ VALID"
        else:
            return "⚠️ INVALID"
    except:
        return "⚠️ ERROR"

# ---------------- CLEAN ----------------

def clean(doc):
    doc["_id"] = str(doc.get("_id"))

    for k in list(doc.keys()):
        if k in SENSITIVE_FIELDS:
            doc[k] = "HIDDEN"

    return doc

# ---------------- FETCH DATA ----------------

data = {}

# 🔥 USERS (latest first)
users = list(db["users"].find().sort("_id", -1))

users_out = []
for u in users:
    raw_token = u.get("github_token")
    gh_status = check_github(raw_token)

    u_clean = clean(dict(u))
    u_clean["github_status"] = gh_status

    users_out.append(u_clean)

data["users"] = users_out

# 🔥 BOTS (latest first)
bots = list(db["bots"].find().sort("_id", -1))
data["bots"] = [clean(dict(b)) for b in bots]

# 🔥 SERVICES (latest first)
services = list(db["services"].find().sort("_id", -1))
data["services"] = [clean(dict(s)) for s in services]

# ---------------- PRINT ALL AT ONCE ----------------

print("\n===== 🔥 FULL DATABASE DUMP =====\n")

print(json.dumps(data, indent=2))

print("\n===== ✅ END =====\n")

# keep alive for Railway logs
while True:
    pass
