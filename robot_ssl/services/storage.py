"""SQLite storage for metadata/transcripts; raw microphone audio is not persisted."""
from __future__ import annotations
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class DatabaseStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS perception_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                transcript TEXT,
                azimuth_degrees REAL,
                wakeword_detected INTEGER NOT NULL,
                addressed_robot INTEGER NOT NULL,
                attention_score REAL,
                language TEXT,
                voice_traits_json TEXT NOT NULL,
                duration_seconds REAL,
                doa_confidence REAL
            )
        """)
        self.connection.commit()

    def save_event(self, event: dict[str, Any]) -> None:
        with self.lock:
            self.connection.execute("""
                INSERT INTO perception_events (
                    transcript, azimuth_degrees, wakeword_detected, addressed_robot,
                    attention_score, language, voice_traits_json, duration_seconds, doa_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.get("transcript", ""),
                event.get("azimuth_degrees"),
                int(bool(event.get("wakeword_detected"))),
                int(bool(event.get("addressed_robot"))),
                event.get("attention_score", 0.0),
                event.get("language"),
                json.dumps(event.get("voice_traits", {}), ensure_ascii=False),
                event.get("duration_seconds"),
                event.get("doa_confidence"),
            ))
            self.connection.commit()


    def load_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        """Load recent event metadata from storage (newest first)."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        with self.lock:
            cursor = self.connection.execute("""
                SELECT timestamp_utc, transcript, azimuth_degrees, wakeword_detected,
                       addressed_robot, attention_score, language, voice_traits_json,
                       duration_seconds, doa_confidence
                FROM perception_events ORDER BY id DESC LIMIT ?
            """, (int(limit),))
            rows = cursor.fetchall()
        keys = [
            "timestamp_utc", "transcript", "azimuth_degrees", "wakeword_detected",
            "addressed_robot", "attention_score", "language", "voice_traits_json",
            "duration_seconds", "doa_confidence",
        ]
        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(zip(keys, row))
            event["wakeword_detected"] = bool(event["wakeword_detected"])
            event["addressed_robot"] = bool(event["addressed_robot"])
            try:
                event["voice_traits"] = json.loads(event.pop("voice_traits_json"))
            except (TypeError, json.JSONDecodeError):
                event["voice_traits"] = {}
            events.append(event)
        return events

    def close(self) -> None:
        with self.lock:
            self.connection.close()
