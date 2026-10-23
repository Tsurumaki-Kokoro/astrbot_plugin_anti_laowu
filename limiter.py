"""Persistent admission limiter, independent of AstrBot for deterministic tests."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import sqlite3
import time


def number(c, name, default, low=0, high=86400):
    try:
        v = float(c.get(name, default))
        return max(low, min(high, v)) if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def ids(v):
    return frozenset(str(x).strip() for x in v if str(x).strip()) if isinstance(v, (list, tuple)) else frozenset()


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    target_ids: frozenset = frozenset({"2290769087"})
    group_ids: frozenset = frozenset()
    cooldown_seconds: float = 180
    max_rounds: int = 2
    reset_after_seconds: float = 600
    pause_seconds: float = 300
    allow_probability: float = 1
    exempt_admins: bool = False
    exempt_commands: frozenset = frozenset({"点歌", "网易点歌", "QQ点歌", "歌词"})
    log_decisions: bool = True

    @classmethod
    def from_config(cls, c):
        return cls(
            enabled=bool(c.get("enabled", True)),
            target_ids=ids(c.get("target_qq_ids", ["2290769087"])),
            group_ids=ids(c.get("group_ids", [])),
            cooldown_seconds=number(c, "cooldown_seconds", 180),
            max_rounds=int(number(c, "max_consecutive_rounds", 2, 0, 1000)),
            reset_after_seconds=number(c, "conversation_reset_seconds", 600, 1),
            pause_seconds=number(c, "pause_seconds", 300),
            allow_probability=number(c, "allow_probability", 1, 0, 1),
            exempt_admins=bool(c.get("exempt_admins", False)),
            exempt_commands=ids(c.get("exempt_commands", ["点歌", "网易点歌", "QQ点歌", "歌词"])),
            log_decisions=bool(c.get("log_decisions", True)),
        )


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    wait_seconds: float = 0
    rounds: int = 0
    admission_id: str = ""


class Limiter:
    def __init__(self, path, clock=time.time, rng=random.random):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS states (
            key TEXT PRIMARY KEY, last_allowed REAL NOT NULL,
            rounds INTEGER NOT NULL, paused_until REAL NOT NULL,
            admission_id TEXT NOT NULL, last_response REAL)""")
        self.db.commit()
        self.clock, self.rng = clock, rng

    def check(self, key, s):
        now = self.clock()
        key = json.dumps(key, ensure_ascii=True, separators=(",", ":"))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT last_allowed, rounds, paused_until FROM states WHERE key=?", (key,)).fetchone()
            last, rounds, paused = row if row else (None, 0, 0)
            if last is not None and now < last:
                return self._finish(Decision(False, "clock_rollback", last-now, rounds))
            if paused > now:
                return self._finish(Decision(False, "conversation_pause", paused-now, rounds))
            if last is not None and now-last < s.cooldown_seconds:
                return self._finish(Decision(False, "cooldown", s.cooldown_seconds-(now-last), rounds))
            if (paused > 0 and now >= paused) or (last is not None and now-last >= s.reset_after_seconds):
                rounds = 0
            if self.rng() >= s.allow_probability:
                return self._finish(Decision(False, "probability", rounds=rounds))
            rounds += 1
            paused = now+s.pause_seconds if s.max_rounds and rounds >= s.max_rounds else 0
            admission = f"{key}:{now}:{random.getrandbits(128):032x}"
            self.db.execute("""INSERT INTO states VALUES (?, ?, ?, ?, ?, NULL)
                ON CONFLICT(key) DO UPDATE SET last_allowed=excluded.last_allowed,
                rounds=excluded.rounds, paused_until=excluded.paused_until,
                admission_id=excluded.admission_id""", (key, now, rounds, paused, admission))
            return self._finish(Decision(True, "admitted", rounds=rounds, admission_id=admission))
        except BaseException:
            self.db.rollback()
            raise

    def _finish(self, d):
        self.db.commit()
        return d

    def record_response(self, admission):
        # Callback telemetry, not a delivery receipt. Never refunds admission quota.
        with self.db:
            self.db.execute("UPDATE states SET last_response=? WHERE admission_id=?", (self.clock(), admission))

    def close(self):
        self.db.close()
