"""
SQLite persistence for conversations and messages (per browser device_id in session).
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from typing import Any

from flask import current_app


def _db_path() -> str:
    return current_app.config["DB_PATH"]


def _connect() -> sqlite3.Connection:
    path = _db_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_device
                ON conversations(device_id, updated_at DESC);
            CREATE TABLE IF NOT EXISTS daily_logs (
                device_id TEXT NOT NULL,
                day TEXT NOT NULL,
                water_ml INTEGER NOT NULL DEFAULT 0,
                steps INTEGER NOT NULL DEFAULT 0,
                mood INTEGER,
                note TEXT NOT NULL DEFAULT '',
                hydration_extra TEXT NOT NULL DEFAULT '',
                workout_minutes INTEGER NOT NULL DEFAULT 0,
                workout_detail TEXT NOT NULL DEFAULT '',
                nutrition_breakfast TEXT NOT NULL DEFAULT '',
                nutrition_lunch TEXT NOT NULL DEFAULT '',
                nutrition_dinner TEXT NOT NULL DEFAULT '',
                nutrition_snacks TEXT NOT NULL DEFAULT '',
                vitality INTEGER,
                updated_at REAL NOT NULL,
                PRIMARY KEY (device_id, day)
            );
            """
        )
        _migrate_daily_logs(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_daily_logs(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_logs'"
    )
    if not cur.fetchone():
        return
    info = conn.execute("PRAGMA table_info(daily_logs)").fetchall()
    names = {row[1] for row in info}
    alters = [
        ("hydration_extra", "TEXT NOT NULL DEFAULT ''"),
        ("workout_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ("workout_detail", "TEXT NOT NULL DEFAULT ''"),
        ("nutrition_breakfast", "TEXT NOT NULL DEFAULT ''"),
        ("nutrition_lunch", "TEXT NOT NULL DEFAULT ''"),
        ("nutrition_dinner", "TEXT NOT NULL DEFAULT ''"),
        ("nutrition_snacks", "TEXT NOT NULL DEFAULT ''"),
        ("vitality", "INTEGER"),
    ]
    for col, decl in alters:
        if col not in names:
            conn.execute(f"ALTER TABLE daily_logs ADD COLUMN {col} {decl}")

    if "water_ml" not in names:
        conn.execute("ALTER TABLE daily_logs ADD COLUMN water_ml INTEGER NOT NULL DEFAULT 0")
        if "water_glasses" in names:
            conn.execute("UPDATE daily_logs SET water_ml = water_glasses * 250")


def create_conversation(device_id: str, title: str = "") -> str:
    cid = str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO conversations (id, device_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            (cid, device_id, title or "Yeni sohbet", now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return cid


def list_conversations(device_id: str, limit: int = 50) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
            FROM conversations c
            WHERE c.device_id = ?
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (device_id, limit),
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_conversation(device_id: str, conversation_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT id, device_id, title, created_at, updated_at FROM conversations WHERE id = ? AND device_id = ?",
            (conversation_id, device_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_messages(device_id: str, conversation_id: str) -> list[dict[str, Any]]:
    conv = get_conversation(device_id, conversation_id)
    if not conv:
        return []
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def touch_conversation(conversation_id: str) -> None:
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        conn.commit()
    finally:
        conn.close()


def persist_message(conversation_id: str, role: str, content: str) -> None:
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
            (conversation_id, role, content[:200000], now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        conn.commit()
    finally:
        conn.close()


def persist_turn(device_id: str, conversation_id: str | None, user_text: str, assistant_text: str) -> None:
    if not conversation_id or not device_id:
        return
    if not get_conversation(device_id, conversation_id):
        return
    persist_message(conversation_id, "user", user_text)
    persist_message(conversation_id, "assistant", assistant_text)


def maybe_autotitle_from_user(conversation_id: str, device_id: str, user_text: str) -> None:
    conv = get_conversation(device_id, conversation_id)
    if not conv:
        return
    title = (conv.get("title") or "").strip()
    if title and title != "Yeni sohbet":
        return
    snippet = " ".join(user_text.split())[:48].strip() or "Sohbet"
    conn = _connect()
    try:
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND device_id = ?",
            (snippet, time.time(), conversation_id, device_id),
        )
        conn.commit()
    finally:
        conn.close()


def rename_conversation(device_id: str, conversation_id: str, title: str) -> bool:
    title = (title or "").strip()[:120]
    if not title:
        return False
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND device_id = ?",
            (title, time.time(), conversation_id, device_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _water_ml_from_row(row: dict[str, Any] | None) -> int:
    """Eski `water_glasses` (≈250 ml) veya yeni `water_ml` alanından ml değeri."""
    if not row:
        return 0
    try:
        if row.get("water_ml") is not None:
            return max(0, int(row["water_ml"]))
    except (TypeError, ValueError):
        pass
    try:
        g = int(row.get("water_glasses") or 0)
    except (TypeError, ValueError):
        g = 0
    return max(0, g * 250)


def get_daily_log(device_id: str, day: str) -> dict[str, Any] | None:
    if not device_id or not day:
        return None
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT * FROM daily_logs WHERE device_id = ? AND day = ?",
            (device_id, day),
        )
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["water_ml"] = _water_ml_from_row(d)
        return d
    finally:
        conn.close()


def _clip_note(text: str | None, max_len: int = 2000) -> str:
    if not text:
        return ""
    return str(text).strip()[:max_len]


def upsert_daily_log(
    device_id: str,
    day: str,
    *,
    water_ml: int | None = None,
    steps: int | None = None,
    mood: int | None = None,
    note: str | None = None,
    hydration_extra: str | None = None,
    workout_minutes: int | None = None,
    workout_detail: str | None = None,
    nutrition_breakfast: str | None = None,
    nutrition_lunch: str | None = None,
    nutrition_dinner: str | None = None,
    nutrition_snacks: str | None = None,
    vitality: int | None = None,
) -> dict[str, Any]:
    now = time.time()
    prev = get_daily_log(device_id, day)
    w = _water_ml_from_row(prev) if prev else 0
    s = int(prev["steps"]) if prev else 0
    m = prev.get("mood") if prev else None
    n = (prev.get("note") or "") if prev else ""
    hx = (prev.get("hydration_extra") or "") if prev else ""
    wm = int(prev["workout_minutes"]) if prev else 0
    wd = (prev.get("workout_detail") or "") if prev else ""
    nb = (prev.get("nutrition_breakfast") or "") if prev else ""
    nl = (prev.get("nutrition_lunch") or "") if prev else ""
    nd = (prev.get("nutrition_dinner") or "") if prev else ""
    ns = (prev.get("nutrition_snacks") or "") if prev else ""
    vit = prev.get("vitality") if prev else None

    if water_ml is not None:
        w = max(0, min(int(water_ml), 20_000))
    if steps is not None:
        s = max(0, min(int(steps), 200_000))
    if mood is not None:
        m = max(1, min(int(mood), 5))
    if note is not None:
        n = _clip_note(note)
    if hydration_extra is not None:
        hx = _clip_note(hydration_extra, 1500)
    if workout_minutes is not None:
        wm = max(0, min(int(workout_minutes), 600))
    if workout_detail is not None:
        wd = _clip_note(workout_detail)
    if nutrition_breakfast is not None:
        nb = _clip_note(nutrition_breakfast, 1200)
    if nutrition_lunch is not None:
        nl = _clip_note(nutrition_lunch, 1200)
    if nutrition_dinner is not None:
        nd = _clip_note(nutrition_dinner, 1200)
    if nutrition_snacks is not None:
        ns = _clip_note(nutrition_snacks, 1200)
    if vitality is not None:
        vit = max(1, min(int(vitality), 5))

    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO daily_logs (
                device_id, day, water_ml, steps, mood, note,
                hydration_extra, workout_minutes, workout_detail,
                nutrition_breakfast, nutrition_lunch, nutrition_dinner, nutrition_snacks,
                vitality, updated_at
            )
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_id, day) DO UPDATE SET
                water_ml = excluded.water_ml,
                steps = excluded.steps,
                mood = excluded.mood,
                note = excluded.note,
                hydration_extra = excluded.hydration_extra,
                workout_minutes = excluded.workout_minutes,
                workout_detail = excluded.workout_detail,
                nutrition_breakfast = excluded.nutrition_breakfast,
                nutrition_lunch = excluded.nutrition_lunch,
                nutrition_dinner = excluded.nutrition_dinner,
                nutrition_snacks = excluded.nutrition_snacks,
                vitality = excluded.vitality,
                updated_at = excluded.updated_at
            """,
            (
                device_id,
                day,
                w,
                s,
                m,
                n,
                hx,
                wm,
                wd,
                nb,
                nl,
                nd,
                ns,
                vit,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    row = get_daily_log(device_id, day)
    return row or {
        "day": day,
        "water_ml": w,
        "steps": s,
        "mood": m,
        "note": n,
        "hydration_extra": hx,
        "workout_minutes": wm,
        "workout_detail": wd,
        "nutrition_breakfast": nb,
        "nutrition_lunch": nl,
        "nutrition_dinner": nd,
        "nutrition_snacks": ns,
        "vitality": vit,
        "updated_at": now,
    }


def week_daily_logs(device_id: str, num_days: int = 7) -> list[dict[str, Any]]:
    """Son N gun (bugun en sagda), eksik gunler sifir degerlerle."""
    out: list[dict[str, Any]] = []
    for i in range(num_days - 1, -1, -1):
        t = time.time() - i * 86400
        d = time.strftime("%Y-%m-%d", time.localtime(t))
        row = get_daily_log(device_id, d)
        if row:
            out.append(dict(row))
        else:
            out.append(
                {
                    "day": d,
                    "water_ml": 0,
                    "steps": 0,
                    "mood": None,
                    "note": "",
                    "hydration_extra": "",
                    "workout_minutes": 0,
                    "workout_detail": "",
                    "nutrition_breakfast": "",
                    "nutrition_lunch": "",
                    "nutrition_dinner": "",
                    "nutrition_snacks": "",
                    "vitality": None,
                    "updated_at": None,
                }
            )
    return out


def delete_conversation(device_id: str, conversation_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND device_id = ?",
            (conversation_id, device_id),
        )
        if not cur.fetchone():
            return False
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute(
            "DELETE FROM conversations WHERE id = ? AND device_id = ?",
            (conversation_id, device_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def weekly_summary(device_id: str) -> dict[str, Any]:
    since = time.time() - 7 * 24 * 3600
    conn = _connect()
    try:
        msg_count = conn.execute(
            """
            SELECT COUNT(*) FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.device_id = ? AND m.created_at >= ?
            """,
            (device_id, since),
        ).fetchone()[0]
        conv_count = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE device_id = ? AND created_at >= ?",
            (device_id, since),
        ).fetchone()[0]
        user_msgs = conn.execute(
            """
            SELECT m.content FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.device_id = ? AND m.created_at >= ? AND m.role = 'user'
            """,
            (device_id, since),
        ).fetchall()
    finally:
        conn.close()

    kalori_hits = hedef_hits = 0
    for (text,) in user_msgs:
        t = (text or "").lower()
        if "kalori hesapla" in t:
            kalori_hits += 1
        if "hedef planla" in t:
            hedef_hits += 1

    return {
        "period_days": 7,
        "messages_total": int(msg_count),
        "conversations_started": int(conv_count),
        "kalori_flow_starts": kalori_hits,
        "hedef_flow_starts": hedef_hits,
    }
