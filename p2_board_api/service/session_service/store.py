"""P0 D-08 local JSON repository (no database engine or personal media)."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_FIELDS = ("sitting_sec", "monitoring_sec", "normal_sec", "attention_sec", "unavailable_sec", "alert_count")
_SESSION_FIELDS = ("id", "started_at", "ended_at", "sitting_sec", "monitoring_sec", "normal_sec",
                   "attention_sec", "unavailable_sec", "alert_count")


class Store:
    """settings.json + calibration.json + session_active.json + append-only sessions.jsonl."""
    def __init__(self, path):
        self.memory = str(path) == ":memory:"
        self.root = None if self.memory else Path(path)
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.root, 0o700)
            except OSError:
                pass
        self.lock = threading.RLock()
        self.data = {"settings": {}, "sessions": [], "active": None, "events": []}
        if self.root:
            loaded_settings = self._read_json("settings.json", {})
            self.data["settings"] = loaded_settings.get("settings", {}) if isinstance(loaded_settings, dict) else {}
            self.data["sessions"] = self._read_sessions()
            active = self._read_json("session_active.json", None)
            if active:
                active["ended_at"] = active.get("updated_at") or active["started_at"]
                self._append_session(active)
                self.data["sessions"].append(active)
                self._remove("session_active.json")

    def _read_json(self, name, fallback):
        path = self.root / name
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            try:
                path.replace(path.with_name(f"{path.name}.corrupt-{stamp}"))
            except OSError:
                pass
            return fallback

    def _atomic_json(self, name, payload):
        if self.memory:
            return
        path = self.root / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:  # Windows ACLs control file access on the development host.
            pass

    def _remove(self, name):
        if self.root:
            try:
                (self.root / name).unlink(missing_ok=True)
            except OSError:
                pass

    def _read_sessions(self):
        path = self.root / "sessions.jsonl"
        if not path.exists():
            return []
        rows = []
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if all(k in row for k in _SESSION_FIELDS):
                        rows.append(row)
                except ValueError:
                    continue
        return rows

    def _append_session(self, row):
        if not self.root:
            return
        safe = {k: row.get(k) for k in _SESSION_FIELDS}
        with (self.root / "sessions.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(safe, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def get_settings(self):
        with self.lock:
            return dict(self.data["settings"])

    def set_settings(self, values):
        with self.lock:
            self.data["settings"].update(values)
            self._atomic_json("settings.json", {"schema_version": 1, "settings": self.data["settings"]})

    def create_session(self, sid, started_at):
        with self.lock:
            self.data["active"] = {"id": sid, "started_at": started_at, "updated_at": started_at,
                                    "ended_at": None, **{k: 0 for k in _FIELDS}}
            self._atomic_json("session_active.json", self.data["active"])

    def save_session(self, sid, snap, updated_at, ended_at=None):
        with self.lock:
            row = self.data["active"]
            if row is None or row["id"] != sid:
                row = next((r for r in self.data["sessions"] if r["id"] == sid), None)
            if row is None:
                return
            row.update({k: int(snap[k]) for k in _FIELDS}, updated_at=updated_at)
            if ended_at is not None:
                row["ended_at"] = ended_at
                self._append_session(row)
                self.data["sessions"].append(dict(row))
                self.data["active"] = None
                self._remove("session_active.json")
            else:
                self.data["active"] = row
                self._atomic_json("session_active.json", row)

    def get_session(self, sid):
        with self.lock:
            candidates = self.data["sessions"] + ([self.data["active"]] if self.data["active"] else [])
            return next((dict(r) for r in candidates if r["id"] == sid), None)

    def list_sessions(self, limit, offset):
        with self.lock:
            rows = sorted(self.data["sessions"], key=lambda r: r["started_at"], reverse=True)
            return [dict(r) for r in rows[offset:offset + limit]], len(rows)

    def all_sessions(self):
        """Return ended summaries for calendar aggregation (no media/raw events)."""
        with self.lock:
            return [dict(r) for r in self.data["sessions"]]

    def last_ended(self):
        rows, _ = self.list_sessions(1, 0)
        return rows[0] if rows else None

    def recover_unfinished(self):
        # Recovery is performed once in __init__, using the last durable checkpoint.
        return 0

    def log_event(self, etype, ts, delta):
        if not self.root:
            return
        row = {"type": etype, "ts": ts, "delta": delta}
        with self.lock, (self.root / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
