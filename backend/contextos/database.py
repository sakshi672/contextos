"""Small transaction boundary for the PostgreSQL implementation."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .settings import database_url


@contextmanager
def connection():
    with psycopg.connect(database_url(), row_factory=dict_row) as db:
        yield db
