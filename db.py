#!/usr/bin/env python3
"""
Deployr — database layer (SQLAlchemy ORM, MySQL/MariaDB).

All table schema is defined in models.py and managed via Flask-Migrate:

    flask db migrate -m "describe change"
    flask db upgrade

Connection details come from environment variables (set in app.py):
    DEPLOYR_DB_HOST   (default 127.0.0.1)
    DEPLOYR_DB_PORT   (default 3306)
    DEPLOYR_DB_USER   (default liege)
    DEPLOYR_DB_PASS   (default rihaan1810)
    DEPLOYR_DB_NAME   (default deployr)
"""

import os
import re
import datetime

from extensions import db
from models import Tool

# Expose connection info for logging (used by routes/tools.py).
DB_CONF = {
    "host": os.environ.get("DEPLOYR_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DEPLOYR_DB_PORT", "3306")),
    "user": os.environ.get("DEPLOYR_DB_USER", ""),
    "password": os.environ.get("DEPLOYR_DB_PASS", ""),
}
DB_NAME = os.environ.get("DEPLOYR_DB_NAME", "deployr")

# Columns a client is allowed to write (id is handled separately).
_WRITABLE = [
    "name", "tool", "repo", "git_url", "branch", "entry_file", "app_var_name",
    "python_version", "language", "description", "url", "live", "status",
    "last_deploy", "sort_order",
]

# ── Seed payloads ──────────────────────────────────────────────────────
SEED = []


# ── Connectivity check + seeding ───────────────────────────────────────

def init_db():
    """
    Check connectivity and seed the table if empty.

    Table creation is handled by `flask db upgrade` (Flask-Migrate / Alembic).
    This function only seeds initial data — it does NOT create tables.

    Raises if the DB is genuinely unreachable. Warns (but does not raise) if the
    schema is stale (e.g. a pending migration hasn't been applied yet).
    """
    from pymysql.err import OperationalError as PyMySQLOperationalError
    from sqlalchemy.exc import OperationalError as SAOperationalError

    try:
        db.session.execute(db.text("SELECT 1"))
    except (SAOperationalError, PyMySQLOperationalError) as e:
        raise

    try:
        if Tool.query.count() == 0:
            _seed()
    except (SAOperationalError, PyMySQLOperationalError):
        import warnings
        warnings.warn(
            "[deployr] Schema out of date — run `flask db upgrade` to apply "
            "pending migrations. Seeding skipped.",
            stacklevel=2,
        )


def _seed():
    """Insert seed rows via ORM."""
    for row in SEED:
        if not Tool.query.get(row["id"]):
            db.session.add(Tool(**row))
    db.session.commit()


# ── CRUD helpers ───────────────────────────────────────────────────────

def list_tools():
    """Return all tools as JSON-ready dicts, ordered by sort_order then name."""
    tools = Tool.query.order_by(Tool.sort_order, Tool.name).all()
    return [t.to_dict() for t in tools]


def get_tool(tid):
    """Return a single tool dict, or None."""
    t = Tool.query.get(tid)
    return t.to_dict() if t else None


def upsert_tool(data):
    """Insert (or update by id) a tool. Returns the stored record dict."""
    tid = slugify(data.get("id") or data.get("tool") or data.get("repo") or "tool")

    t = Tool.query.get(tid)
    if t is None:
        t = Tool(id=tid)
        if "sort_order" not in data:
            t.sort_order = _next_sort_order()
        db.session.add(t)

    for col in _WRITABLE:
        if col in data:
            setattr(t, col, data[col])

    db.session.commit()
    return t.to_dict()


def delete_tool(tid):
    """Delete a tool by id. Returns True if deleted, False if not found."""
    t = Tool.query.get(tid)
    if t is None:
        return False
    db.session.delete(t)
    db.session.commit()
    return True


def ensure_unique_id(base):
    """Return base slug, or base-2 / base-3 … if the id already exists."""
    base = slugify(base)
    existing = {row.id for row in Tool.query.with_entities(Tool.id).all()}
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _next_sort_order():
    result = db.session.execute(
        db.select(db.func.coalesce(db.func.max(Tool.sort_order), 0) + 1)
    ).scalar()
    return result or 1


# ── URL parsing / metadata derivation ─────────────────────────────────

def slugify(s):
    """Toolforge-friendly slug: lowercase, hyphen-separated, alnum only."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(s or "")).strip("-").lower()
    s = re.sub(r"-+", "-", s)
    return s or "tool"


def derive_from_url(url):
    """Best-effort parse of a git/archive URL into a tool record skeleton."""
    u = (url or "").strip()
    owner = repo = host = None
    m = re.search(r"(github|gitlab)\.com[:/]+([^/]+)/([^/?#]+?)(?:\.git)?/?$", u, re.I)
    if m:
        host, owner, repo = m.group(1).lower(), m.group(2), m.group(3)
    else:
        tail = u.rstrip("/").split("/")[-1] if u else ""
        repo = re.sub(r"\.(git|zip|tar|tar\.gz|tgz)$", "", tail, flags=re.I) or "tool"

    slug = slugify(repo)
    name = re.sub(r"[-_]+", " ", repo).strip().title() if repo else "New Payload"
    full = f"{owner}/{repo}" if owner else (repo or u)
    return {
        "id": slug, "name": name, "tool": slug, "repo": full, "git_url": u,
        "branch": "main", "entry_file": "app.py", "app_var_name": "app",
        "python_version": "python3.11", "language": "", "description": "",
        "url": f"https://{slug}.toolforge.org/", "live": 0, "status": "unknown",
        "_host": host, "_owner": owner, "_repo": repo,
    }


if __name__ == "__main__":
    from app import app
    with app.app_context():
        init_db()
        tools = list_tools()
        print(f"deployr DB ready · {len(tools)} tools:")
        for t in tools:
            print(f"  · {t['id']:24} tools.{t['tool']:18} [{t['status']}]")
