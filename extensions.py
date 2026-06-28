#!/usr/bin/env python3
"""
Flask extension singletons.

Instantiated here (without an app) so they can be imported by models.py
without causing circular imports. The app binds them via init_app() in app.py.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
