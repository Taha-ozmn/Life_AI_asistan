import app as chatbot_app


def test_auth_error_detects_status_code_without_401_in_message():
    class E(Exception):
        status_code = 401

    assert chatbot_app._is_auth_or_key_error(E("bad request")) is True


def test_parse_number_extracts_first_integer():
    assert chatbot_app.parse_number("yasim 28, kilom 70") == 28
    assert chatbot_app.parse_number("sayi yok") is None


def test_calculate_daily_calories_has_floor():
    assert chatbot_app.calculate_daily_calories(100, 30, 120) == 1200


def test_health_endpoint_returns_expected_shape():
    client = chatbot_app.app.test_client()
    response = client.get("/health")
    data = response.get_json()

    assert response.status_code == 200
    assert data["status"] == "ok"
    assert "ai_configured" in data
    assert isinstance(data["ai_configured"], bool)


def _fake_ask_calorie(user_message, prior_messages, extra_system="", max_tokens=350):
    tag = chatbot_app._FLOW_CAL_TAG
    if tag + "ASK_START" in user_message:
        return "Harika! Lutfen yasinizi yazin."
    if tag + "CLARIFY_AGE" in user_message:
        return "Yasinizi sayi olarak yazin."
    if tag + "ASK_WEIGHT" in user_message:
        return "Tesekkurler! Simdi kilonuzu kg cinsinden yazin."
    if tag + "CLARIFY_WEIGHT" in user_message:
        return "Kilo icin sayi yazin."
    if tag + "ASK_HEIGHT" in user_message:
        return "Super! Son olarak boyunuzu cm cinsinden yazin."
    if tag + "CLARIFY_HEIGHT" in user_message:
        return "Boy icin sayi yazin."
    if tag + "PLAN_SUMMARY" in user_message:
        return "Tahmini gunluk kalori ihtiyaciniz: ~2000 kcal. Ogun ve egzersiz ozeti."
    return "fallback-cal"


def test_chat_calorie_flow_happy_path(monkeypatch):
    monkeypatch.setattr(chatbot_app, "ask_openai", _fake_ask_calorie)
    client = chatbot_app.app.test_client()

    r1 = client.post("/chat", json={"message": "kalori hesapla"})
    assert r1.status_code == 200
    assert "yasinizi" in r1.get_json()["reply"].lower()

    r2 = client.post("/chat", json={"message": "25"})
    assert r2.status_code == 200
    assert "kilonuzu" in r2.get_json()["reply"].lower()

    r3 = client.post("/chat", json={"message": "72"})
    assert r3.status_code == 200
    assert "boyunuzu" in r3.get_json()["reply"].lower()

    r4 = client.post("/chat", json={"message": "175"})
    assert r4.status_code == 200
    assert "tahmini gunluk kalori ihtiyaciniz" in r4.get_json()["reply"].lower()


def _fake_ask_goal(user_message, prior_messages, extra_system="", max_tokens=350):
    tag = chatbot_app._FLOW_GOAL_TAG
    if tag + "ASK_START" in user_message:
        return "Hedef planlayalim. Lutfen yasinizi yazin."
    if tag + "CLARIFY_AGE" in user_message:
        return "Yas sayisi iste."
    if tag + "ASK_WEIGHT" in user_message:
        return "Guncel kilonuzu kg olarak yazin."
    if tag + "ASK_HEIGHT" in user_message:
        return "Boyunuzu cm olarak yazin."
    if tag + "ASK_TARGET" in user_message:
        return "Hedef kilonuzu kg olarak yazin."
    if tag + "ASK_ACTIVITY" in user_message:
        return "Aktivite seviyenizi 1-5 veya hafif/orta/yogun olarak yazin."
    if tag + "CLARIFY_ACTIVITY" in user_message:
        return "Aktiviteyi netlestir."
    if tag + "PLAN_SUMMARY" in user_message:
        return "TDEE yaklasik 2200 kcal. Plan ozeti burada."
    return "fallback-goal"


def test_goal_flow_happy_path(monkeypatch):
    monkeypatch.setattr(chatbot_app, "ask_openai", _fake_ask_goal)
    client = chatbot_app.app.test_client()

    r1 = client.post("/chat", json={"message": "hedef planla"})
    assert r1.status_code == 200
    assert "yasinizi" in r1.get_json()["reply"].lower()

    r2 = client.post("/chat", json={"message": "30"})
    assert r2.status_code == 200
    assert "kilonuzu" in r2.get_json()["reply"].lower() or "kilo" in r2.get_json()["reply"].lower()

    r3 = client.post("/chat", json={"message": "80"})
    assert r3.status_code == 200
    assert "boyunuzu" in r3.get_json()["reply"].lower() or "boy" in r3.get_json()["reply"].lower()

    r4 = client.post("/chat", json={"message": "178"})
    assert r4.status_code == 200
    assert "hedef kilonuzu" in r4.get_json()["reply"].lower() or "hedef" in r4.get_json()["reply"].lower()

    r5 = client.post("/chat", json={"message": "72"})
    assert r5.status_code == 200
    assert "aktivite" in r5.get_json()["reply"].lower()

    r6 = client.post("/chat", json={"message": "3"})
    assert r6.status_code == 200
    body = r6.get_json()["reply"].lower()
    assert "tdee" in body or "kcal" in body


def test_conversation_delete_via_post(monkeypatch):
    def fake_ask_openai(user_message, prior_messages, extra_system="", max_tokens=350):
        return "yanit"

    monkeypatch.setattr(chatbot_app, "ask_openai", fake_ask_openai)
    client = chatbot_app.app.test_client()
    client.post("/chat", json={"message": "sil testi"})

    r = client.get("/api/conversations")
    assert r.status_code == 200
    cid = r.get_json()["current_id"]

    d = client.post(f"/api/conversations/{cid}/delete")
    assert d.status_code == 200
    data = d.get_json()
    assert data.get("ok") is True
    assert data.get("cleared") is True
    assert data.get("conversation_id") != cid


def test_tracking_daily_get_and_post(monkeypatch):
    monkeypatch.setattr(chatbot_app, "ask_openai", lambda *a, **k: "x")
    client = chatbot_app.app.test_client()

    g = client.get("/api/tracking/daily")
    assert g.status_code == 200
    body = g.get_json()
    assert "today" in body and "week" in body
    assert len(body["week"]) == 7

    p = client.post(
        "/api/tracking/daily",
        json={
            "water_ml": 750,
            "steps": 5000,
            "mood": 4,
            "note": "test",
            "vitality": 4,
            "workout_minutes": 30,
            "nutrition_breakfast": "yulaf",
            "hydration_extra": "cay",
        },
    )
    assert p.status_code == 200
    assert p.get_json().get("ok") is True
    log = p.get_json().get("log") or {}
    assert log.get("vitality") == 4
    assert log.get("workout_minutes") == 30
    assert "yulaf" in (log.get("nutrition_breakfast") or "")


def test_ai_insight_tracking_daily(monkeypatch):
    monkeypatch.setattr(chatbot_app, "client", object())
    monkeypatch.setattr(chatbot_app, "ask_openai", lambda *a, **k: "Gunluk AI test.")

    client = chatbot_app.app.test_client()
    r = client.post("/api/ai/insight/tracking/daily", json={"day": "2026-05-05"})
    assert r.status_code == 200
    assert r.get_json().get("insight") == "Gunluk AI test."

    bad = client.post("/api/ai/insight/tracking/daily", json={"day": "invalid"})
    assert bad.status_code == 400


def test_api_conversations_list_and_persist_messages(monkeypatch):
    def fake_ask_openai(user_message, prior_messages, extra_system="", max_tokens=350):
        return "ai-ok"

    monkeypatch.setattr(chatbot_app, "ask_openai", fake_ask_openai)

    client = chatbot_app.app.test_client()
    client.post("/chat", json={"message": "merhaba dunya"})

    r = client.get("/api/conversations")
    assert r.status_code == 200
    data = r.get_json()
    assert "conversations" in data
    assert len(data["conversations"]) >= 1
    cid = data["current_id"]
    assert cid

    detail = client.get(f"/api/conversations/{cid}")
    assert detail.status_code == 200
    msgs = detail.get_json()["messages"]
    assert any(m["role"] == "user" and "merhaba" in m["content"] for m in msgs)


def _fake_ask_reset_scenario(user_message, prior_messages, extra_system="", max_tokens=350):
    tag = chatbot_app._FLOW_CAL_TAG
    if tag + "ASK_START" in user_message:
        return "Lutfen yasinizi yazin."
    if tag + "CLARIFY_AGE" in user_message:
        return "Yas icin sayi yazin."
    return "other"


def test_chat_reset_clears_session_history_and_flow(monkeypatch):
    monkeypatch.setattr(chatbot_app, "ask_openai", _fake_ask_reset_scenario)

    client = chatbot_app.app.test_client()

    client.post("/chat", json={"message": "kalori hesapla"})
    client.post("/chat", json={"message": "merhaba"})

    reset_response = client.post("/chat/reset")
    assert reset_response.status_code == 200
    assert reset_response.get_json()["ok"] is True

    fresh = client.post("/chat", json={"message": "kalori hesapla"})
    assert fresh.status_code == 200
    assert "yasinizi" in fresh.get_json()["reply"].lower()
