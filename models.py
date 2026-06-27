#!/usr/bin/env python3
"""
SQLAlchemy ORM models for Toolforge Manager.

The `Tool` model mirrors the existing `tools` table in MySQL/MariaDB.
All schema changes should be made here and applied via Flask-Migrate:

    flask db migrate -m "describe change"
    flask db upgrade
"""

import datetime
from extensions import db


class Tool(db.Model):
    """Catalogue entry for a Toolforge-deployable tool."""

    __tablename__ = "tools"

    id             = db.Column(db.String(64),  primary_key=True)
    name           = db.Column(db.String(128), nullable=False)
    tool           = db.Column(db.String(64),  nullable=False)
    repo           = db.Column(db.String(255), nullable=False)
    git_url        = db.Column(db.String(512), nullable=False)
    branch         = db.Column(db.String(64),  default="main")
    entry_file     = db.Column(db.String(128), default="app.py")
    app_var_name   = db.Column(db.String(64),  default="app")
    python_version = db.Column(db.String(32),  default="python3.11")
    language       = db.Column(db.String(64),  nullable=True)
    description    = db.Column(db.Text,        nullable=True)
    url            = db.Column(db.String(255), nullable=True)
    live           = db.Column(db.SmallInteger, default=0)
    status         = db.Column(db.String(32),  default="unknown")
    last_deploy    = db.Column(db.DateTime,    nullable=True)
    sort_order     = db.Column(db.Integer,     default=0)
    owner          = db.Column(db.String(64),  default="")
    tagsy       = db.Column(db.String(255), nullable=True)  # ← new column

    def to_dict(self):
        """Return a JSON-serialisable dict (matches the existing API shape)."""
        ld = self.last_deploy
        return {
            "id":             self.id,
            "name":           self.name,
            "owner":          self.owner,
            "tool":           self.tool,
            "repo":           self.repo,
            "git_url":        self.git_url,
            "branch":         self.branch,
            "entry_file":     self.entry_file,
            "app_var_name":   self.app_var_name,
            "python_version": self.python_version,
            "language":       self.language,
            "description":    self.description,
            "url":            self.url,
            "live":           bool(self.live),
            "status":         self.status,
            "lastDeploy":     (ld.isoformat() + "Z") if isinstance(ld, datetime.datetime) else ld,
        }

    def __repr__(self):
        return f"<Tool {self.id!r} [{self.status}]>"
