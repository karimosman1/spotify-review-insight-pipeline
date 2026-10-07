"""Shared helpers: CSV reading, source hashing, env loading, append-only JSONL storage.

Standard library only so offline replay and checks work in a clean environment.
"""

import csv
import hashlib
import json
import os
import threading
from pathlib import Path

FIELDS = ("review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp")
ROOT = Path(__file__).resolve().parent.parent


def canonical(value):
    # Same serialization as reference/check_submission.py so row hashes match the grader.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False)


def row_sha(row):
    return hashlib.sha256(canonical([row[k] for k in FIELDS]).encode("utf-8")).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_source_rows(path):
    """Yield rows with only the six source fields. Extra columns (e.g. golden labels) are dropped
    here so they can never reach a model prompt."""
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, strict=True)
        missing = [k for k in FIELDS if k not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing source columns {missing}")
        for row in reader:
            if None in row or any(row[k] is None for k in FIELDS):
                raise ValueError(f"{path}: malformed CSV row near review_id={row.get('review_id')}")
            yield {k: row[k] for k in FIELDS}


def load_env(path=ROOT / ".env"):
    """Minimal .env loader (KEY=VALUE lines). Never logs values."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


class JsonlLog:
    """Append-only JSONL file. Each append is one write + fsync, so a crash loses at most the
    line being written; readers skip a truncated trailing line."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def append(self, *objs):
        data = "".join(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n" for o in objs)
        with self.lock, self.path.open("a", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    def read(self):
        return read_jsonl(self.path)


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            break  # truncated final line from an interrupted write
    return out


def write_json(path, value):
    """Atomic write: temp file then rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, path)
