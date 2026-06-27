#!/usr/bin/env python3
"""
Deployr — local database layer (MariaDB / MySQL wire-compatible).

Holds the catalogue of deployable tools ("payloads"). Connection details
come from environment variables with sane local defaults:

    DEPLOYR_DB_HOST   (default 127.0.0.1)
    DEPLOYR_DB_PORT   (default 3306)
    DEPLOYR_DB_USER   (default root)
    DEPLOYR_DB_PASS   (default "")
    DEPLOYR_DB_NAME   (default deployr)

init_db() creates the database + table on first run and seeds it if empty.
"""
import os
import re
import datetime
import pymysql
from pymysql.cursors import DictCursor

# Columns a client is allowed to write (id is handled separately).
_WRITABLE = [
    "name", "tool", "repo", "git_url", "branch", "entry_file", "app_var_name",
    "python_version", "language", "description", "url", "live", "status",
    "last_deploy", "sort_order",
]

DB_CONF = {
    "host": os.environ.get("DEPLOYR_DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DEPLOYR_DB_PORT", "3306")),
    "user": os.environ.get("DEPLOYR_DB_USER", "root"),
    "password": os.environ.get("DEPLOYR_DB_PASS", ""),
}
DB_NAME = os.environ.get("DEPLOYR_DB_NAME", "deployr")

# Columns returned to the frontend (last_deploy is mapped to lastDeploy).
_COLUMNS = [
    "id", "name", "tool", "repo", "git_url", "branch", "entry_file",
    "app_var_name", "python_version", "language", "description", "url",
    "live", "status", "last_deploy", "sort_order",
]

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tools (
    id            VARCHAR(64)  PRIMARY KEY,
    name          VARCHAR(128) NOT NULL,
    tool          VARCHAR(64)  NOT NULL,
    repo          VARCHAR(255) NOT NULL,
    git_url       VARCHAR(512) NOT NULL,
    branch        VARCHAR(64)  DEFAULT 'main',
    entry_file    VARCHAR(128) DEFAULT 'app.py',
    app_var_name  VARCHAR(64)  DEFAULT 'app',
    python_version VARCHAR(32) DEFAULT 'python3.11',
    language      VARCHAR(64),
    description   TEXT,
    url           VARCHAR(255),
    live          TINYINT(1)   DEFAULT 0,
    status        VARCHAR(32)  DEFAULT 'unknown',
    last_deploy   DATETIME     NULL,
    sort_order    INT          DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

# ── Seed payloads (moved out of frontend/data.js) ──────────────────────
SEED = [
    {
        "id": "pdf-image-identifier", "name": "PDF Image Identifier", "tool": "picstalker",
        "repo": "Ro-shni/PDF-IMAGE-IDENTIFIER",
        "git_url": "https://github.com/Ro-shni/PDF-IMAGE-IDENTIFIER.git", "branch": "main",
        "entry_file": "app.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python · Flask",
        "description": "Classifies PDF pages as Image, Text, or Image+Text and uploads to Wikimedia Commons.",
        "url": "https://picstalker.toolforge.org/", "live": 1, "status": "unknown",
        "last_deploy": "2026-06-25 14:02:00", "sort_order": 1,
    },
    {
        "id": "citation-hunt", "name": "Citation Hunt", "tool": "citation-hunt",
        "repo": "wikimedia/citation-hunt",
        "git_url": "https://github.com/wikimedia/citation-hunt.git", "branch": "main",
        "entry_file": "app.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python · Flask",
        "description": "Surfaces unsourced Wikipedia snippets that need citations.",
        "url": "https://citationhunt.toolforge.org/", "live": 0, "status": "running",
        "last_deploy": "2026-06-20 09:15:00", "sort_order": 2,
    },
    {
        "id": "commons-uploader", "name": "Commons Batch Uploader", "tool": "commons-uploader",
        "repo": "Ro-shni/commons-uploader",
        "git_url": "https://github.com/Ro-shni/commons-uploader.git", "branch": "main",
        "entry_file": "server.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python",
        "description": "Bulk-uploads freely licensed media to Wikimedia Commons with OAuth.",
        "url": "https://commons-uploader.toolforge.org/", "live": 0, "status": "stopped",
        "last_deploy": "2026-06-12 18:40:00", "sort_order": 3,
    },
    {
        "id": "wikitrends", "name": "WikiTrends", "tool": "wikitrends",
        "repo": "Ro-shni/wikitrends",
        "git_url": "https://github.com/Ro-shni/wikitrends.git", "branch": "develop",
        "entry_file": "wsgi.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python · Flask",
        "description": "Dashboards for trending article pageviews across language editions.",
        "url": "https://wikitrends.toolforge.org/", "live": 0, "status": "running",
        "last_deploy": "2026-06-24 11:30:00", "sort_order": 4,
    },
    {
        "id": "lexeme-forms", "name": "Lexeme Forms", "tool": "lexeme-forms",
        "repo": "wikimedia/lexeme-forms",
        "git_url": "https://github.com/wikimedia/lexeme-forms.git", "branch": "main",
        "entry_file": "app.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python · Flask",
        "description": "Guided creation of Wikidata lexeme forms from templates.",
        "url": "https://lexeme-forms.toolforge.org/", "live": 0, "status": "stopped",
        "last_deploy": "2026-05-30 08:00:00", "sort_order": 5,
    },
    {
        "id": "depictor", "name": "Depictor", "tool": "depictor",
        "repo": "Ro-shni/depictor",
        "git_url": "https://github.com/Ro-shni/depictor.git", "branch": "main",
        "entry_file": "app.py", "app_var_name": "app", "python_version": "python3.11",
        "language": "Python · Flask",
        "description": "Crowdsources structured-data depicts statements for Commons images.",
        "url": "https://depictor.toolforge.org/", "live": 0, "status": "deploying",
        "last_deploy": "2026-06-26 07:45:00", "sort_order": 6,
    },
]


def _connect(with_db=True):
    conf = dict(DB_CONF, cursorclass=DictCursor, autocommit=True)
    if with_db:
        conf["database"] = DB_NAME
    return pymysql.connect(**conf)


def init_db():
    """Create database + table and seed it if empty. Idempotent."""
    # 1. ensure database exists
    root = pymysql.connect(**DB_CONF, autocommit=True)
    try:
        with root.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        root.close()

    # 2. ensure table + seed
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE)
            cur.execute("SELECT COUNT(*) AS n FROM tools")
            if cur.fetchone()["n"] == 0:
                _seed(cur)
    finally:
        conn.close()


def _seed(cur):
    cols = ", ".join(SEED[0].keys())
    placeholders = ", ".join(["%s"] * len(SEED[0]))
    sql = f"INSERT INTO tools ({cols}) VALUES ({placeholders})"
    cur.executemany(sql, [tuple(row.values()) for row in SEED])


def list_tools():
    """Return all tools as JSON-ready dicts (last_deploy → lastDeploy ISO)."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLUMNS)} FROM tools ORDER BY sort_order, name")
            rows = cur.fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        ld = r.pop("last_deploy", None)
        r["lastDeploy"] = ld.isoformat() + "Z" if isinstance(ld, datetime.datetime) else ld
        r["live"] = bool(r.get("live"))
        r.pop("sort_order", None)
        out.append(r)
    return out


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


def ensure_unique_id(base):
    """Return base, or base-2 / base-3 … if the id already exists."""
    base = slugify(base)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM tools")
            existing = {r["id"] for r in cur.fetchall()}
    finally:
        conn.close()
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def upsert_tool(data):
    """Insert (or update by id) a tool. Returns the stored record."""
    tid = slugify(data.get("id") or data.get("tool") or data.get("repo") or "tool")
    fields = {k: data[k] for k in _WRITABLE if k in data}
    if "sort_order" not in fields:
        fields["sort_order"] = _next_sort_order()

    cols = ["id"] + list(fields.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f"{k}=VALUES({k})" for k in fields.keys())
    sql = (
        f"INSERT INTO tools ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, [tid] + list(fields.values()))
    finally:
        conn.close()
    return get_tool(tid)


def get_tool(tid):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {', '.join(_COLUMNS)} FROM tools WHERE id=%s", (tid,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        return None
    ld = r.pop("last_deploy", None)
    r["lastDeploy"] = ld.isoformat() + "Z" if isinstance(ld, datetime.datetime) else ld
    r["live"] = bool(r.get("live"))
    r.pop("sort_order", None)
    return r


def delete_tool(tid):
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tools WHERE id=%s", (tid,))
            return cur.rowcount > 0
    finally:
        conn.close()


def _next_sort_order():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM tools")
            return cur.fetchone()["n"]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    tools = list_tools()
    print(f"deployr DB ready · {len(tools)} tools seeded:")
    for t in tools:
        print(f"  · {t['id']:24} tools.{t['tool']:18} [{t['status']}]")
