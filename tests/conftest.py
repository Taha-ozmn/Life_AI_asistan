import pytest

import app as chatbot_app


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_nutricoach.db")
    monkeypatch.setitem(chatbot_app.app.config, "DB_PATH", db_path)
    monkeypatch.setattr(chatbot_app, "_db_initialized", False)
