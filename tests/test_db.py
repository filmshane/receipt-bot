from pathlib import Path

from receipt_bot.db import Database


def test_processed_and_pending(tmp_path: Path):
    db = Database(tmp_path / "bot.db")
    assert db.is_processed(1, 10) is False
    db.mark_processed(1, 10)
    assert db.is_processed(1, 10) is True
    db.set_pending(1, {"total": None, "vendor": "A"})
    p = db.get_pending(1)
    assert p["vendor"] == "A"
    db.clear_pending(1)
    assert db.get_pending(1) is None
