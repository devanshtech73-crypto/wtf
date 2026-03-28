from flask import jsonify
from pymongo import MongoClient
import os

@app.route("/db")
def debug_db():
    # 🔐 optional: protect with a secret key
    if os.getenv("ADMIN_TOKEN") and \
       (request.headers.get("x-admin-token") != os.getenv("ADMIN_TOKEN")):
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    client = MongoClient(os.getenv("MONGO_URI"))
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

    data = {}

    for name in collections:
        col = db[name]
        data[name] = [clean(d) for d in col.find().limit(50)]  # limit for safety

    return jsonify({"ok": True, "data": data})
