"""Shared test fixtures. The main concern is isolating the SQLite memory
DB between tests so writes don't bleed across cases."""

import os
import tempfile
import pytest


@pytest.fixture(autouse=True)
def isolated_memory_db(monkeypatch):
    """Point every memory-backed call at a fresh temp DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    monkeypatch.setattr("memory.db.DB_PATH", tmp.name)
    monkeypatch.setattr("memory.repository.get_connection",
                         lambda db_path=tmp.name: _conn(db_path))

    from memory.db import init_db
    init_db(tmp.name)

    yield tmp.name

    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def _conn(db_path):
    """Mirror of memory.db.get_connection with the swapped path."""
    import sqlite3
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        conn = sqlite3.connect(db_path, isolation_level=None, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()
    return _cm()
