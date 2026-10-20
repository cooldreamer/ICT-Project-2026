from robot_ssl.services.storage import DatabaseStore


def test_event_store_can_save_and_load(tmp_path):
    store = DatabaseStore(tmp_path / "events.sqlite3")
    store.save_event({
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
    history = store.load_recent_events(5)
    store.close()
    assert len(history) == 1
    assert history[0]["transcript"] == "hey robot"
    assert history[0]["wakeword_detected"] is True
    assert history[0]["voice_traits"]["pitch_median_hz"] == 140.0
