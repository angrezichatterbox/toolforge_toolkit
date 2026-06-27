import json
import urllib.request

from flask import Blueprint, request, jsonify

import db

tools_bp = Blueprint("tools", __name__)

# Initialise the local catalogue DB once, at import. Degrade gracefully if the
# database is unavailable so the rest of the API keeps working.
try:
    db.init_db()
    DB_OK = True
    print(f"[deployr] DB connected: {db.DB_CONF['host']}:{db.DB_CONF['port']}/{db.DB_NAME}")
except Exception as _db_err:  # pragma: no cover
    DB_OK = False
    print(f"[deployr] DB unavailable ({_db_err}); /api/tools will return empty.")


def _enrich_from_github(owner, repo):
    """Best-effort metadata pull from the public GitHub API (unauthenticated)."""
    if not owner or not repo:
        return {}
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"User-Agent": "Deployr", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = {}
        if data.get("description"):
            out["description"] = data["description"]
        if data.get("language"):
            out["language"] = data["language"]
        if data.get("default_branch"):
            out["branch"] = data["default_branch"]
        if data.get("name"):
            out["name"] = data["name"].replace("-", " ").replace("_", " ").title()
        return out
    except Exception as e:
        print(f"[deployr] GitHub enrich failed for {owner}/{repo}: {e}")
        return {}


@tools_bp.route("/api/tools", methods=["GET"])
def list_tools_endpoint():
    """Returns the catalogue of deployable tools from the local database."""
    if not DB_OK:
        return jsonify({"tools": [], "error": "database unavailable"})
    try:
        return jsonify({"tools": db.list_tools()})
    except Exception as e:
        return jsonify({"tools": [], "error": str(e)}), 500


@tools_bp.route("/api/tools/inspect", methods=["POST"])
def inspect_tool_endpoint():
    """Parse a pasted git URL into a tool record (with GitHub enrichment) — not saved."""
    if not DB_OK:
        return jsonify({"success": False, "message": "database unavailable"}), 503
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"success": False, "message": "Missing 'url'."}), 400
    derived = db.derive_from_url(url)
    if derived.get("_host") == "github":
        derived.update(_enrich_from_github(derived.get("_owner"), derived.get("_repo")))
    derived["id"] = db.ensure_unique_id(derived.get("tool") or derived.get("id"))
    derived["tool"] = derived["id"]
    derived["url"] = f"https://{derived['tool']}.toolforge.org/"
    for k in ("_host", "_owner", "_repo"):
        derived.pop(k, None)
    return jsonify({"success": True, "tool": derived})


@tools_bp.route("/api/tools", methods=["POST"])
def create_tool_endpoint():
    """Add (or update by id) a tool in the catalogue."""
    if not DB_OK:
        return jsonify({"success": False, "message": "database unavailable"}), 503
    data = request.json or {}
    if not data.get("git_url"):
        return jsonify({"success": False, "message": "Missing 'git_url'."}), 400
    # Always derive a complete base from the URL, then overlay any client values,
    # so required fields (repo, url, …) are never missing.
    base = db.derive_from_url(data["git_url"])
    for k in ("_host", "_owner", "_repo"):
        base.pop(k, None)
    merged = {**base, **{k: v for k, v in data.items() if v not in (None, "")}}
    if not data.get("id"):
        merged["id"] = db.ensure_unique_id(merged.get("tool") or merged["id"])
    try:
        stored = db.upsert_tool(merged)
        return jsonify({"success": True, "tool": stored})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@tools_bp.route("/api/tools/<tid>", methods=["DELETE"])
def delete_tool_endpoint(tid):
    """Remove a tool from the catalogue."""
    if not DB_OK:
        return jsonify({"success": False, "message": "database unavailable"}), 503
    try:
        ok = db.delete_tool(tid)
        return jsonify({"success": ok, "message": "deleted" if ok else "not found"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
