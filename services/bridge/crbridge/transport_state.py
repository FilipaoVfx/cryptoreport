"""Small durable transport journal. No tokens or source document bodies here."""
import json
import os
from pathlib import Path
import sqlite3


class TransportState:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        os.chmod(path, 0o600)
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS uploads (
            folder TEXT NOT NULL, name TEXT NOT NULL, file_id TEXT NOT NULL,
            sha256 TEXT NOT NULL, state TEXT NOT NULL,
            PRIMARY KEY(folder,name));
        ''')

    def get(self, key, default=None):
        row = self.db.execute('SELECT value FROM kv WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        with self.db:
            self._put(key, value)

    def _put(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO kv VALUES (?,?)', (key,json.dumps(value,allow_nan=False)))

    def upload(self, folder, name):
        row = self.db.execute('SELECT file_id,sha256,state FROM uploads WHERE folder=? AND name=?', (folder,name)).fetchone()
        return dict(zip(('file_id','sha256','state'),row)) if row else None

    def reserve_upload(self, folder, name, identifier, sha):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO uploads VALUES (?,?,?,?,?)',(folder,name,identifier,sha,'pending'))
        return self.upload(folder,name)

    def uploaded(self, folder, name, identifier, sha):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO uploads VALUES (?,?,?,?,?)',(folder,name,identifier,sha,'confirmed'))

    def close(self):
        self.db.close()
