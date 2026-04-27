"""
API database connection — reads DATABASE_URL from environment.
"""

import os
import psycopg2
import psycopg2.extras


def get_conn():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
