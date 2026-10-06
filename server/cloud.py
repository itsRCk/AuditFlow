"""Managed SQL and private Blob adapters; local disk is only a warm cache."""

import hashlib
import mimetypes
import os
import uuid
from pathlib import Path


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.columns = [column[0] for column in cursor.description or ()]

    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(zip(self.columns, row)) if row is not None else None

    def fetchall(self):
        return [Row(zip(self.columns, row)) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Database:
    def __init__(self, url, token):
        import libsql

        self.db = libsql.connect(url, auth_token=token, timeout=20)

    def execute(self, sql, parameters=()):
        return Cursor(self.db.execute(sql, parameters))

    def executescript(self, sql):
        return self.db.executescript(sql.replace("PRAGMA journal_mode=WAL;", ""))

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        self.db.close()


class Files:
    def __init__(self, root: Path):
        from vercel.blob import BlobClient

        self.root = root
        self.client = BlobClient(token=os.environ["BLOB_READ_WRITE_TOKEN"])

    def save(self, path: Path):
        key = path.relative_to(self.root).as_posix()
        self.client.put(
            key,
            path.read_bytes(),
            access="private",
            content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            overwrite=True,
        )

    def load(self, key: str, digest: str | None = None) -> Path:
        # Only server-generated file keys are accepted, never arbitrary URLs.
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("Invalid stored document location.")
        path = self.root / key
        if not path.exists():
            result = self.client.get(key, access="private")
            if result is None or result.status_code != 200:
                raise RuntimeError("The stored document is temporarily unavailable.")
            if digest and hashlib.sha256(result.content).hexdigest() != digest:
                raise RuntimeError("The stored document failed its integrity check.")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}-{uuid.uuid4().hex}.download")
            temporary.write_bytes(result.content)
            temporary.replace(path)
        return path
