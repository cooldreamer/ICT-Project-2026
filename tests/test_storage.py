"""Tests for persisting and reloading perception-event metadata."""

from robot_ssl.services.storage import DatabaseStore


def test_event_store_can_save_and_load(tmp_path):
    """Check that an event round-trips through SQLite with typed fields.

    Parameters:
        * tmp_path : Pytest-provided temporary directory for the database.

    Returns:
        None.
    """
    store = DatabaseStore(tmp_path / "events.sqlite3")
    store.saveEvent({
        "transcript": "hey robot",
        "azimuth_degrees": 15.0,
        "wakeword_detected": True,
        "addressed_robot": True,
        "attention_score": 1.0,
        "language": "en",
        "voice_traits": {"pitch_median_hz": 140.0},
        "duration_seconds": 1.4,
        "doa_confidence": 0.8,
    })
    history = store.loadRecentEvents(5)
    store.close()
    assert len(history) == 1
    assert history[0]["transcript"] == "hey robot"
    assert history[0]["wakeword_detected"] is True
    assert history[0]["voice_traits"]["pitch_median_hz"] == 140.0


def test_clear_events_removes_transcripts_and_preserves_schema(tmp_path):
    """Check that clearing events deletes their data but keeps the table.

    Parameters:
        * tmp_path : Pytest-provided temporary directory for the database.

    Returns:
        None.
    """
    store = DatabaseStore(tmp_path / "events.sqlite3")
    store.saveEvent({"transcript": "private transcript"})

    store.clearEvents()

    assert store.loadRecentEvents() == []
    assert store.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'perception_events'"
    ).fetchone() == ("perception_events",)
    store.close()
