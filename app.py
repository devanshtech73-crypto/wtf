from flask import Flask, jsonify, request
from pymongo import MongoClient
from datetime import datetime
import os

app = Flask(__name__)

# 🔐 ENV
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

if not MONGO_URI:
    raise Exception("MONGO_URI not set")

client = MongoClient(MONGO_URI)
db = client["blazecloud_panel"]

users_col = db["users"]
bots_col = db["bots"]
services_col = db["services"]

# ---------------- UTILS ----------------

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

def now_iso():
    return datetime.utcnow().isoformat()

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return jsonify({"ok": True, "message": "Backend running"})

# 🔥 DEBUG DB ROUTE
@app.route("/db")
def debug_db():
    # 🔐 protect route
    if ADMIN_TOKEN:
        if request.headers.get("x-admin-token") != ADMIN_TOKEN:
            return jsonify({"ok": False, "error": "Unauthorized"}), 403

    data = {}

    for name in ["users", "bots", "services"]:
        col = db[name]
        data[name] = [clean(d) for d in col.find().limit(50)]

    return jsonify({
        "ok": True,
        "count": {
            "users": users_col.count_documents({}),
            "bots": bots_col.count_documents({}),
            "services": services_col.count_documents({})
        },
        "data": data
    })

# ---------------- SIMPLE HEALTH ----------------

@app.route("/health")
def health():
    return jsonify({"ok": True, "time": now_iso()})

# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
