import json
import os
import re
import time
import uuid
from datetime import timedelta

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
    session,
    stream_with_context,
)
from openai import APITimeoutError, NotFoundError, OpenAI, RateLimitError

import store

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-in-production")
app.permanent_session_lifetime = timedelta(days=400)

_default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "nutricoach.db")
app.config["DB_PATH"] = os.environ.get("NUTRICOACH_DB", _default_db)

if load_dotenv:
    load_dotenv()

_db_initialized = False


@app.before_request
def _ensure_db_and_session():
    global _db_initialized
    if not _db_initialized:
        store.init_db()
        _db_initialized = True
    if "device_id" not in session:
        session["device_id"] = str(uuid.uuid4())
        session.permanent = True
    did = session["device_id"]
    cid = session.get("current_conversation_id")
    # None veya silinmis id kalirsa cerezde anahtar var diye atlanmasin; DB'deki son sohbete bagla
    if not cid or not store.get_conversation(did, cid):
        latest = store.list_conversations(did, limit=1)
        session["current_conversation_id"] = latest[0]["id"] if latest else None
        session.modified = True


def _openai_model_id():
    return (os.getenv("AI_MODEL") or "gpt-4.1-mini").strip()


def _gemini_model_id():
    # gemini-1.5-flash (kisaltma) bazi API surumlerinde 404 veriyor; 2.0-flash OpenAI uyumlu ucta yaygin.
    return (os.getenv("AI_MODEL") or "gemini-2.0-flash").strip()


def _groq_model_id():
    """Groq OpenAI-uyumlu uc; varsayilan kucuk model daha hizli."""
    return (os.getenv("AI_MODEL") or "llama-3.1-8b-instant").strip()


def _model_candidates() -> list[str]:
    """AI_MODEL + opsiyonel AI_MODEL_FALLBACKS (virgulle ayrilmis)."""
    first = (model_name or "").strip()
    raw_fallbacks = (os.getenv("AI_MODEL_FALLBACKS") or "").strip()
    out: list[str] = []
    if first:
        out.append(first)
    if raw_fallbacks:
        for m in raw_fallbacks.split(","):
            mm = m.strip()
            if mm and mm not in out:
                out.append(mm)
    if provider_name == "gemini":
        # En hafif -> daha tam guc (kota/latency durumuna gore)
        for m in ("gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"):
            if m not in out:
                out.append(m)
    elif provider_name == "openai":
        for m in ("gpt-4.1-mini",):
            if m not in out:
                out.append(m)
    elif provider_name == "groq":
        for m in ("llama-3.1-8b-instant", "llama-3.3-70b-versatile"):
            if m not in out:
                out.append(m)
    return out


def build_ai_client():
    """
    Ortam degiskenleri (.env + python-dotenv):
    - AI_PROVIDER: groq | openai | gemini
    - GROQ_API_KEY: gsk_... (Groq — ucretsiz katman cok hizli; RPM limiti var, sinirsiz degil)
    - GROQ_BASE_URL: bos ise https://api.groq.com/openai/v1
    - OPENAI_API_KEY: sk-... (OpenAI)
    - GEMINI_API_KEY: AIza... (Google AI; veya OPENAI_API_KEY ile ayni AIza anahtari)
    - AI_MODEL: ornek gpt-4.1-mini veya Google dokumantasyonundaki model id (bos ise varsayilan)
    - AI_MAX_OUTPUT_TOKENS: cikti tokeni; bos=512 (hiz); max|unlimited=tavana kadar
    - AI_HISTORY_MESSAGES: modele kac mesaj (all|sayi); bos=all -> AI_MAX_CONTEXT_MESSAGES kadar
    - AI_MAX_CONTEXT_MESSAGES: all ile birlikte DB son satir limiti (varsayilan 48; hiz icin dusuk tut)
    - AI_SESSION_MESSAGES: Flask oturumunda tutulan son mesaj (cerez boyutu; varsayilan 150)
    - AI_REQUEST_TIMEOUT_SECONDS: tek API cagrisi suresi (15-600 sn, varsayilan 180)
    - FLASK_SECRET_KEY, NUTRICOACH_DB (opsiyonel veritabani yolu)
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    provider = (os.getenv("AI_PROVIDER") or "openai").lower().strip()

    if provider == "groq" and groq_key:
        groq_base = (os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1").strip().rstrip("/")
        return OpenAI(api_key=groq_key, base_url=groq_base), _groq_model_id(), "groq"

    if provider == "openai" and openai_key:
        return OpenAI(api_key=openai_key), _openai_model_id(), "openai"

    if provider == "gemini" and gemini_key:
        return (
            OpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            _gemini_model_id(),
            "gemini",
        )

    if openai_key:
        if openai_key.startswith("AIza"):
            return (
                OpenAI(
                    api_key=openai_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                ),
                _gemini_model_id(),
                "gemini",
            )
        return OpenAI(api_key=openai_key), _openai_model_id(), "openai"

    return None, None, None


client, model_name, provider_name = build_ai_client()

SYSTEM_PROMPT = (
    "Sen bir diyetisyen ve fitness koçusun. Kullanicilara anlasilir ve motive edici "
    "cevaplar ver. Kalori, beslenme, egzersiz ve tarif isteklerinde yardimci ol. "
    "Sohbetteki onceki konusmalari, sayilari ve tercihleri hatirla; tutarli kal. "
    "Varsayilan: en fazla 5-8 kisa cumle veya madde listesi; gereksiz giris/cikis yazma. "
    "Kullanici tarif, liste, 'detay', 'uzun anlat' derse o zaman tam uzun yanit ver; "
    "cumleyi yarida kesme."
)

_FLOW_CAL_TAG = "__FLOW_CAL__/"
_FLOW_GOAL_TAG = "__FLOW_GOAL__/"

FLOW_CAL_EXTRA = (
    "Mesajin basinda gizli etiket "
    + _FLOW_CAL_TAG
    + " ile baslayan bir satir vardir; kullaniciya bu etiketi veya dahili kodlari "
    "asla yazma. Etikete uygun tek Turkce yanit ver."
)

FLOW_GOAL_EXTRA = (
    "Mesajin basinda gizli etiket "
    + _FLOW_GOAL_TAG
    + " ile baslayan bir satir vardir; kullaniciya bu etiketi veya dahili kodlari "
    "asla yazma. Etikete uygun tek Turkce yanit ver."
)

TRACKING_AI_EXTRA = (
    "Sen bir diyetisyen ve saglik koçusun. Verilen tablo kullanicinin kendi girdigi "
    "gunluk takip ozetidir. Turkce yaz: kisa giris; su, hareket ve varsa antrenman "
    "dakikalari; beslenme ozetine (ogun notlari) ve ruh hali / yenilenmislik "
    "duzeyine degin; 3 madde uygulanabilir oneri; bir cumle motivasyon. "
    "Tibbi tani koyma; gerekirse uzmana danisin hatirlat."
)

TRACKING_DAILY_AI_EXTRA = (
    "Sen bir diyetisyen ve saglik koçusun. Verilen metin tek bir gunun kullanici "
    "gunluk takip kaydidir. Turkce yaz: kisa bir giris (2-4 cumle); su, adim, "
    "hareket/antrenman, beslenme ve mod/yenilenme hakkinda olumlu ve uygulanabilir "
    "2-4 madde oneri; sonunda tek cumle destek. Tibbi tani koyma; gerekirse uzmana "
    "yonlendir."
)

BMI_AI_EXTRA = (
    "Sen bir diyetisyensin. Verilen boy, kilo ve BMI bilgisine dayanarak Turkce, sicak "
    "ve destekleyici kisa bir bilgilendirme yaz (yaklasik 80-140 kelime). WHO BMI "
    "siniflamasini genel hatlariyla acikla; kisisel tani veya tedavi onerme; "
    "ozel durumda uzman yonlendir."
)


def _max_context_messages_hard_cap() -> int:
    """Modele gonderilebilecek mesaj satiri (user+asistan) ust siniri."""
    # Varsayilan dusuk tutulur (hiz); tam gezin SQLite'da kalir.
    raw = (os.environ.get("AI_MAX_CONTEXT_MESSAGES") or "48").strip()
    try:
        n = int(raw)
        return min(max(n, 16), 800)
    except ValueError:
        return 48


def _max_context_for_api() -> int:
    """Veritabanindan modele giden son mesaj sayisi; tamami DBde kalir."""
    hard = _max_context_messages_hard_cap()
    raw = (os.environ.get("AI_HISTORY_MESSAGES") or "all").strip().lower()
    if raw in ("all", "max", "full", "0", "unlimited"):
        return hard
    try:
        n = int(raw)
        return min(max(n, 4), hard)
    except ValueError:
        return min(48, hard)


def _max_session_stored_messages() -> int:
    """Flask oturumunda tutulan mesaj (buyuk sohbetlerde cerez boyutu icin kirpilir)."""
    raw = (os.environ.get("AI_SESSION_MESSAGES") or "150").strip()
    try:
        n = int(raw)
        return min(max(n, 20), 400)
    except ValueError:
        return 150


def _prior_for_model() -> list:
    """Gercek baglam: SQLite'daki mevcut sohbet gecmisi (ust sinira kadar)."""
    did = session.get("device_id")
    cid = session.get("current_conversation_id")
    if not did or not cid:
        return _get_chat_history()
    rows = store.list_messages(did, cid)
    hist = [{"role": r["role"], "content": r["content"]} for r in rows]
    hist = _normalize_history(hist)
    cap = _max_context_for_api()
    if len(hist) > cap:
        hist = hist[-cap:]
    return hist


# Uzun tarif / liste yanitlari icin (session + DB); asiri buyuk tutma
MAX_MESSAGE_CHARS = 16000

# Gercek anlamda "sinirsiz" yok; saglayici/model ciktiyi yine tavanlar.
# OpenAI tarafinda model basina farklidir; asiri buyuk deger 400 verebilir, API genelde kirpar.
_GEMINI_MAX_OUTPUT_TOKENS = 8192
_OPENAI_CHAT_MAX_OUTPUT_TOKENS = 16384


def _ai_request_timeout_seconds() -> float:
    """Tek tamamlama istegi icin HTTP zaman asimi (429 yeniden denemelerinde her denemede uygulanir)."""
    raw = (os.environ.get("AI_REQUEST_TIMEOUT_SECONDS") or "180").strip()
    try:
        v = float(raw)
        return min(max(v, 15.0), 600.0)
    except ValueError:
        return 180.0


def _provider_output_cap() -> int:
    if provider_name == "gemini":
        return _GEMINI_MAX_OUTPUT_TOKENS
    if provider_name == "openai":
        return _OPENAI_CHAT_MAX_OUTPUT_TOKENS
    if provider_name == "groq":
        return _OPENAI_CHAT_MAX_OUTPUT_TOKENS
    return _GEMINI_MAX_OUTPUT_TOKENS


def _default_max_output_tokens() -> int:
    """Sohbet ciktisi; .env AI_MAX_OUTPUT_TOKENS: sayi veya max|unlimited (tavana kadar)."""
    cap = _provider_output_cap()
    # Daha dusuk varsayilan = daha hizli bitecek yanit; uzun tarif icin .env ile artirin.
    raw = (os.environ.get("AI_MAX_OUTPUT_TOKENS") or "512").strip().lower()
    if raw in ("max", "unlimited", "full", "none"):
        return cap
    try:
        n = int(raw)
        if n <= 0:
            return cap
        return min(max(n, 128), cap)
    except ValueError:
        return min(512, cap)


def _chat_temperature() -> float:
    """.env AI_TEMPERATURE (0.0-2.0); dusuk = biraz daha deterministik, genelde daha cabuk."""
    raw = (os.environ.get("AI_TEMPERATURE") or "0.35").strip()
    try:
        v = float(raw)
        return min(max(v, 0.0), 2.0)
    except ValueError:
        return 0.35

ACTIVITY_FACTORS = {
    "1": 1.2,
    "2": 1.375,
    "3": 1.55,
    "4": 1.725,
    "5": 1.9,
}


def _default_calorie_flow():
    return {"active": False, "age": None, "weight": None, "height": None}


def _default_goal_flow():
    return {
        "active": False,
        "age": None,
        "weight": None,
        "height": None,
        "target_weight": None,
        "activity": None,
    }


def _get_calorie_flow():
    data = session.get("calorie_flow")
    if not isinstance(data, dict):
        return _default_calorie_flow()
    base = _default_calorie_flow()
    base.update({k: data.get(k, base[k]) for k in base})
    return base


def _set_calorie_flow(flow):
    session["calorie_flow"] = flow
    session.modified = True


def _get_goal_flow():
    data = session.get("goal_flow")
    if not isinstance(data, dict):
        return _default_goal_flow()
    base = _default_goal_flow()
    base.update({k: data.get(k, base[k]) for k in base})
    return base


def _set_goal_flow(flow):
    session["goal_flow"] = flow
    session.modified = True


def reset_calorie_state():
    session.pop("calorie_flow", None)
    session.modified = True


def reset_goal_state():
    session.pop("goal_flow", None)
    session.modified = True


def _normalize_history(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[: MAX_MESSAGE_CHARS - 1] + "…"
        out.append({"role": role, "content": text})
    return out


def _get_chat_history():
    return _normalize_history(session.get("chat_history"))


def _set_chat_history(items):
    cap = _max_session_stored_messages()
    trimmed = items[-cap:] if len(items) > cap else items
    session["chat_history"] = trimmed
    session.modified = True


def _ensure_current_conversation_id():
    """Gecerli sohbet yoksa once DB'deki en son sohbeti bagla, hic yoksa yeni olustur.

    Oturumda id None (veya silinmis) olabilir; sadece `if cid` ile yeni sohbet acilirdi.
    Streaming + cerez gecikmesinde de son konusmayi surdurmek icin list_conversations ile hizala.
    """
    did = session.get("device_id")
    if not did:
        return None
    cid = session.get("current_conversation_id")
    if cid and store.get_conversation(did, cid):
        return cid
    latest = store.list_conversations(did, 1)
    if latest:
        cid = latest[0]["id"]
        session["current_conversation_id"] = cid
        session.modified = True
        return cid
    try:
        cid = store.create_conversation(did)
        session["current_conversation_id"] = cid
        session.modified = True
        return cid
    except Exception:
        return None


def append_chat_turn(user_text, assistant_text):
    history = _get_chat_history()
    u = user_text.strip()
    a = assistant_text.strip()
    if not u or not a:
        return
    history.append({"role": "user", "content": u[:MAX_MESSAGE_CHARS]})
    history.append({"role": "assistant", "content": a[:MAX_MESSAGE_CHARS]})
    _set_chat_history(history)
    _ensure_current_conversation_id()
    did = session.get("device_id")
    cid = session.get("current_conversation_id")
    try:
        store.persist_turn(did, cid, u, a)
        store.maybe_autotitle_from_user(cid, did, u)
    except Exception:
        pass


def clear_chat_session():
    session.pop("chat_history", None)
    reset_calorie_state()
    reset_goal_state()


def parse_number(text):
    match = re.search(r"\d+", text)
    if not match:
        return None
    return int(match.group())


def parse_activity_factor(text):
    """Map user text to TDEE multiplier (1–5 or keywords)."""
    msg = text.lower().strip()
    m = re.search(r"[1-5]", msg)
    if m:
        key = m.group(0)
        if key in ACTIVITY_FACTORS:
            return ACTIVITY_FACTORS[key]
    if any(x in msg for x in ("masa", "sedanter", "az hareket", "ofis")):
        return 1.2
    if "hafif" in msg or "yuruyus" in msg:
        return 1.375
    if "orta" in msg:
        return 1.55
    if "yogun" in msg or "agir" in msg or "antrenman" in msg:
        return 1.725
    if "cok" in msg and ("yogun" in msg or "spor" in msg):
        return 1.9
    return None


def calculate_daily_calories(age, weight, height, activity_factor=1.375):
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    tdee = int(bmr * activity_factor)
    return max(tdee, 1200)


def build_plan(calories):
    breakfast = int(calories * 0.3)
    lunch = int(calories * 0.35)
    dinner = int(calories * 0.25)
    snacks = calories - (breakfast + lunch + dinner)

    diet_plan = (
        f"- Kahvalti (~{breakfast} kcal): Yulaf + yogurt + meyve\n"
        f"- Ogle (~{lunch} kcal): Izgara tavuk/balik + bulgur/pirinç + salata\n"
        f"- Aksam (~{dinner} kcal): Sebze yemegi + yogurt + tam tahilli ekmek\n"
        f"- Ara ogun (~{snacks} kcal): Badem/ceviz + kefir veya meyve"
    )

    workout_plan = (
        "- Pazartesi: 30 dk tempolu yuruyus + 2 set squat, push-up, plank\n"
        "- Carsamba: 30 dk yuruyus + 2 set lunge, glute bridge, mountain climber\n"
        "- Cuma: 30 dk yuruyus + 2 set squat, plank, superman\n"
        "- Her gun: 5-10 dk esneme"
    )

    return diet_plan, workout_plan


def handle_calorie_flow(user_message):
    """Sunucu sayilari parse eder; tum kullanici yanitlari modelden uretilir."""
    msg = user_message.lower().strip()
    calorie_state = _get_calorie_flow()
    prior = _prior_for_model()

    def ai(payload: str, max_tokens: int = 400) -> str:
        return ask_openai(payload, prior, extra_system=FLOW_CAL_EXTRA, max_tokens=max_tokens)

    if "kalori hesapla" in msg and not calorie_state["active"]:
        calorie_state["active"] = True
        _set_calorie_flow(calorie_state)
        body = (
            f"{_FLOW_CAL_TAG}ASK_START\n"
            "Kalori hesabi basladi. Kullanicidan yasini (10-100 arasi tam sayi) "
            "istedigini belirten sicak, kisa bir cumle yaz."
            f"\nKullanici mesaji: {user_message}"
        )
        return ai(body, max_tokens=320)

    if not calorie_state["active"]:
        return None

    if calorie_state["age"] is None:
        age = parse_number(msg)
        if age is None or age < 10 or age > 100:
            body = (
                f"{_FLOW_CAL_TAG}CLARIFY_AGE\n"
                f"Yas bekleniyordu. Kullanici yazdi: {user_message!r}\n"
                "Nazikce 10-100 arasi sayi olarak yas iste."
            )
            return ai(body, max_tokens=320)
        calorie_state["age"] = age
        _set_calorie_flow(calorie_state)
        body = (
            f"{_FLOW_CAL_TAG}ASK_WEIGHT\n"
            f"Yas {age} kaydedildi. Kullanicidan kilosunu kg olarak iste, kisa ve net."
        )
        return ai(body, max_tokens=320)

    if calorie_state["weight"] is None:
        weight = parse_number(msg)
        if weight is None or weight < 30 or weight > 250:
            body = (
                f"{_FLOW_CAL_TAG}CLARIFY_WEIGHT\n"
                f"Kilo bekleniyordu. Kullanici yazdi: {user_message!r}\n"
                "30-250 kg arasi sayi iste."
            )
            return ai(body, max_tokens=320)
        calorie_state["weight"] = weight
        _set_calorie_flow(calorie_state)
        body = (
            f"{_FLOW_CAL_TAG}ASK_HEIGHT\n"
            f"Kilo {weight} kg kaydedildi. Kullanicidan boyunu cm olarak iste."
        )
        return ai(body, max_tokens=320)

    if calorie_state["height"] is None:
        height = parse_number(msg)
        if height is None or height < 120 or height > 230:
            body = (
                f"{_FLOW_CAL_TAG}CLARIFY_HEIGHT\n"
                f"Boy bekleniyordu. Kullanici yazdi: {user_message!r}\n"
                "120-230 cm arasi sayi iste."
            )
            return ai(body, max_tokens=320)
        calorie_state["height"] = height

        age, weight = calorie_state["age"], calorie_state["weight"]
        calories = calculate_daily_calories(age, weight, height)
        diet_plan, workout_plan = build_plan(calories)

        body = (
            f"{_FLOW_CAL_TAG}PLAN_SUMMARY\n"
            f"Veri: Yas {age}, kilo {weight} kg, boy {height} cm.\n"
            f"Mifflin-St Jeor + hafif aktivite (x1.375) ile tahmini gunluk ihtiyac: ~{calories} kcal.\n"
            f"Referans ogun bolusumu:\n{diet_plan}\n\nReferans hareket cercevesi:\n{workout_plan}\n\n"
            "Bunlari kullanarak Turkce tam bir mesaj yaz: kalori rakami, gunluk ogun fikirleri ve haftalik "
            "hareket; yaniti eksik veya yarim birakma. Tibbi tani koyma; ozel durumda uzman oner."
        )
        reset_calorie_state()
        return ai(body, max_tokens=1600)

    return None


def handle_goal_flow(user_message):
    """Hedef kilo + aktivite: sayilar sunucuda; tum yanitlar modelden."""
    msg = user_message.lower().strip()
    state = _get_goal_flow()
    prior = _prior_for_model()

    def ai(payload: str, max_tokens: int = 400) -> str:
        return ask_openai(payload, prior, extra_system=FLOW_GOAL_EXTRA, max_tokens=max_tokens)

    if _get_calorie_flow().get("active"):
        return None

    if "hedef planla" in msg and not state["active"]:
        state["active"] = True
        _set_goal_flow(state)
        body = (
            f"{_FLOW_GOAL_TAG}ASK_START\n"
            "Hedef kilo + aktivite plani basladi. Once yas (10-100) iste, kisa ve sicak."
            f"\nKullanici: {user_message}"
        )
        return ai(body, max_tokens=320)

    if not state["active"]:
        return None

    if state["age"] is None:
        age = parse_number(msg)
        if age is None or age < 10 or age > 100:
            body = (
                f"{_FLOW_GOAL_TAG}CLARIFY_AGE\n"
                f"Yas bekleniyordu. Kullanici: {user_message!r}\n"
                "10-100 arasi sayi iste."
            )
            return ai(body, max_tokens=320)
        state["age"] = age
        _set_goal_flow(state)
        body = (
            f"{_FLOW_GOAL_TAG}ASK_WEIGHT\n"
            f"Yas {age} alindi. Guncel kiloyu kg olarak iste."
        )
        return ai(body, max_tokens=320)

    if state["weight"] is None:
        weight = parse_number(msg)
        if weight is None or weight < 30 or weight > 250:
            body = (
                f"{_FLOW_GOAL_TAG}CLARIFY_WEIGHT\n"
                f"Kilo bekleniyordu. Kullanici: {user_message!r}\n"
                "30-250 kg arasi sayi iste."
            )
            return ai(body, max_tokens=320)
        state["weight"] = weight
        _set_goal_flow(state)
        body = (
            f"{_FLOW_GOAL_TAG}ASK_HEIGHT\n"
            f"Kilo {weight} kg alindi. Boyu cm olarak iste."
        )
        return ai(body, max_tokens=320)

    if state["height"] is None:
        height = parse_number(msg)
        if height is None or height < 120 or height > 230:
            body = (
                f"{_FLOW_GOAL_TAG}CLARIFY_HEIGHT\n"
                f"Boy bekleniyordu. Kullanici: {user_message!r}\n"
                "120-230 cm arasi sayi iste."
            )
            return ai(body, max_tokens=320)
        state["height"] = height
        _set_goal_flow(state)
        body = (
            f"{_FLOW_GOAL_TAG}ASK_TARGET\n"
            f"Boy {height} cm alindi. Hedef kiloyu kg olarak iste."
        )
        return ai(body, max_tokens=320)

    if state["target_weight"] is None:
        tw = parse_number(msg)
        if tw is None or tw < 35 or tw > 200:
            body = (
                f"{_FLOW_GOAL_TAG}CLARIFY_TARGET\n"
                f"Hedef kilo bekleniyordu. Kullanici: {user_message!r}\n"
                "35-200 kg arasi hedef iste."
            )
            return ai(body, max_tokens=320)
        state["target_weight"] = tw
        _set_goal_flow(state)
        body = (
            f"{_FLOW_GOAL_TAG}ASK_ACTIVITY\n"
            "Son adim: aktivite. Kullaniciya 1-5 arasi secenekleri veya "
            "'hafif'/'orta'/'yogun' gibi kisa ifadeleri aciklayarak sor; mesaji kisa tut."
        )
        return ai(body, max_tokens=450)

    if state["activity"] is None:
        factor = parse_activity_factor(msg)
        if factor is None:
            body = (
                f"{_FLOW_GOAL_TAG}CLARIFY_ACTIVITY\n"
                f"Aktivite bekleniyordu. Kullanici: {user_message!r}\n"
                "1-5 rakam veya hafif/orta/yogun gibi ifade iste."
            )
            return ai(body, max_tokens=360)
        state["activity"] = factor

        age, w, h, tw = state["age"], state["weight"], state["height"], state["target_weight"]
        tdee = calculate_daily_calories(age, w, h, activity_factor=factor)
        delta_kg = w - tw
        rough_daily = 500
        if abs(delta_kg) < 2:
            hint = (
                "Hedef kilo mevcuta cok yakin; bakim ve TDEE civari denge oner."
            )
        elif delta_kg > 0:
            target_kcal = max(tdee - rough_daily, 1200)
            hint = (
                f"Kilo verme yonu: kabaca {target_kcal}-{tdee} kcal bandi (~{rough_daily} kcal alti) "
                "ornek tempo haftada ~0.3-0.5 kg; protein ve direnc antrenmani vurgula."
            )
        elif delta_kg < 0:
            target_kcal = tdee + rough_daily
            hint = (
                f"Kilo alma yonu: kabaca {tdee}-{target_kcal} kcal bandi (~{rough_daily} kcal ustu); "
                "asiri hizdan kacin, kaliteli besin agirligi artir."
            )
        else:
            hint = "Hedef mevcut kilo ile ayni; TDEE etrafinda denge."

        diet_plan, workout_plan = build_plan(tdee)

        body = (
            f"{_FLOW_GOAL_TAG}PLAN_SUMMARY\n"
            f"Yas {age}, kilo {w} kg, boy {h} cm, hedef {tw} kg, aktivite carpani {factor}.\n"
            f"Tahmini TDEE: ~{tdee} kcal/gun. Kilo farki: {delta_kg:+.1f} kg.\n"
            f"Sunucu ozeti: {hint}\n\n"
            f"Referans ogun bolusumu:\n{diet_plan}\n\nReferans hareket:\n{workout_plan}\n\n"
            "Turkce tam bir mesajda ozetle: TDEE, hedef yonu, gunluk beslenme ve haftalik hareket; "
            "yaniti yarim birakma. Tibbi tani yok; gerekirse uzman yonlendir."
        )
        reset_goal_state()
        return ai(body, max_tokens=1600)

    return None


def ask_openai(user_message, prior_messages, extra_system="", max_tokens=None):
    if max_tokens is None:
        max_tokens = _default_max_output_tokens()
    if client is None:
        raise RuntimeError(
            "API anahtari bulunamadi. OpenAI icin OPENAI_API_KEY=sk-... "
            "veya Google AI Studio icin GEMINI_API_KEY=AIza... ayarlayin."
        )

    system = SYSTEM_PROMPT
    if extra_system:
        system = system + "\n\n" + extra_system

    messages = [{"role": "system", "content": system}]
    for item in prior_messages:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message.strip()})

    # Gecici kota (429) veya yogunluk (503): kisa yeniden deneme (toplam bekleme ~21 sn)
    backoff_seconds = (1.5, 3.0, 6.0, 10.0)
    last_err = None
    models = _model_candidates()
    for midx, model in enumerate(models):
        for attempt in range(len(backoff_seconds) + 1):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=_chat_temperature(),
                    max_tokens=max_tokens,
                    timeout=_ai_request_timeout_seconds(),
                )
                choice0 = completion.choices[0] if completion.choices else None
                msg = choice0.message if choice0 else None
                raw = (getattr(msg, "content", None) or "") if msg else ""
                return str(raw).strip()
            except Exception as err:
                last_err = err
                if _is_model_not_found_error(err) and midx < len(models) - 1:
                    break
                if _is_transient_ai_error(err):
                    if attempt < len(backoff_seconds):
                        time.sleep(backoff_seconds[attempt])
                        continue
                    if midx < len(models) - 1:
                        break
                raise last_err from None
    raise last_err from None


def ask_openai_stream(user_message, prior_messages, extra_system="", max_tokens=None):
    """Modelden gelen metni parca parca uretir (SSE icin)."""
    if max_tokens is None:
        max_tokens = _default_max_output_tokens()
    if client is None:
        raise RuntimeError(
            "API anahtari bulunamadi. OpenAI icin OPENAI_API_KEY=sk-... "
            "veya Google AI Studio icin GEMINI_API_KEY=AIza... ayarlayin."
        )

    system = SYSTEM_PROMPT
    if extra_system:
        system = system + "\n\n" + extra_system

    messages = [{"role": "system", "content": system}]
    for item in prior_messages:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": user_message.strip()})

    backoff_seconds = (1.5, 3.0, 6.0, 10.0)
    last_err = None
    models = _model_candidates()
    for midx, model in enumerate(models):
        for attempt in range(len(backoff_seconds) + 1):
            try:
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=_chat_temperature(),
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=_ai_request_timeout_seconds(),
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
                return
            except Exception as err:
                last_err = err
                if _is_model_not_found_error(err) and midx < len(models) - 1:
                    break
                if _is_transient_ai_error(err):
                    if attempt < len(backoff_seconds):
                        time.sleep(backoff_seconds[attempt])
                        continue
                    if midx < len(models) - 1:
                        break
                raise last_err from None
    raise last_err from None


def _is_auth_or_key_error(exc) -> bool:
    """OpenAI SDK often puts 401 on .status_code, not in str(exc)."""
    code = getattr(exc, "status_code", None)
    if code == 401:
        return True
    text = (str(exc) + repr(exc)).lower()
    return (
        " 401" in str(exc)
        or "error code: 401" in text
        or "invalid_api_key" in text
        or "incorrect api key" in text
        or "authenticationerror" in text
        or "invalid x-api-key" in text
    )


def _is_rate_limit_error(exc) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    t = (str(exc) + repr(exc)).lower()
    if "resource_exhausted" in t:
        return True
    if "too many requests" in t:
        return True
    if "rate_limit" in t or "ratelimit" in t:
        return True
    if "quota" in t and ("exceeded" in t or "exhausted" in t):
        return True
    return False


def _is_503_overload(exc: BaseException) -> bool:
    """Gecici 503 (yuksek talep / UNAVAILABLE) yanitlari."""
    if getattr(exc, "status_code", None) == 503:
        return True
    low = (str(exc) + repr(exc)).lower()
    if "error code: 503" in low:
        return True
    if "503" in low and ("unavailable" in low or "high demand" in low):
        return True
    return False


def _is_transient_ai_error(exc: BaseException) -> bool:
    """Kisa bekleyip yeniden denenebilir: kota (429) veya yogunluk (503)."""
    if _is_rate_limit_error(exc):
        return True
    return _is_503_overload(exc)


def _transient_failure_reply(exc: BaseException) -> str:
    if _is_503_overload(exc):
        return (
            "Yapay zeka servisi su anda cok yogun (503 — gecici). "
            "Sunucu istegi birkac kez otomatik yeniden denedi; yine de olmadiysa:\n\n"
            "1) 1–3 dakika bekleyip **aynı mesajı tekrar gonder**.\n"
            "2) `.env` icinde **AI_MODEL** ile dokumasyondaki baska bir model kimligi dene.\n"
            "3) Bir sure sonra tekrar dene.\n\n"
            "Sunucuyu (.env degisince) yeniden baslat."
        )
    return _rate_limit_reply_for_user()


def _is_model_not_found_error(exc) -> bool:
    if isinstance(exc, NotFoundError):
        return True
    if getattr(exc, "status_code", None) != 404:
        return False
    t = (str(exc) + repr(exc)).lower()
    return "not found" in t or "models/" in t or "not supported" in t


def _model_not_found_reply() -> str:
    return (
        "Secilen **AI_MODEL** bu API ucunda bulunamadi veya desteklenmiyor (404).\n\n"
        "Google AI veya OpenAI dokumantasyonundaki **guncel model kimlikleri** listesinden "
        "bir deger secip `.env` icinde **AI_MODEL=...** olarak yaz.\n\n"
        "Kaydedip sunucuyu yeniden baslat."
    )


def _rate_limit_reply_for_user() -> str:
    if provider_name == "gemini":
        return (
            "Kota veya dakika basina istek limiti doldu (ucretsiz planda sik gorulur).\n\n"
            "Sunucu bu yaniti dondurmeden once istegi birkac kez otomatik yeniden denedi; yine de doluysa:\n\n"
            "Ne yapabilirsin:\n"
            "1) 2–5 dakika bekleyip tekrar dene.\n"
            "2) `.env` icinde **AI_MODEL** ile baska bir model kimligi dene.\n"
            "3) Google AI Studio veya dokumandaki kota / limit sayfalarini kontrol et.\n\n"
            "Sunucuyu (.env degisince) yeniden baslat."
        )
    if provider_name == "groq":
        return (
            "Groq ucretsiz katmaninda **dakika basina istek (RPM)** limiti var; tam sinirsiz degildir.\n\n"
            "Ne yapabilirsin:\n"
            "1) 1–2 dakika bekleyip tekrar dene.\n"
            "2) `.env` icinde **AI_MODEL** ile daha kucuk/hizli bir model dene (or. llama-3.1-8b-instant).\n"
            "3) Groq konsolunda kota/limit sayfasini kontrol et.\n\n"
            "Sinirsiz ve tamamen ucretsiz istiyorsan kendi bilgisayarinda **Ollama** ile yerel model "
            "calistirabilirsin (internet kotasi yok; ekran karti/CPU sinirlarin kalir)."
        )
    return (
        "OpenAI kota / rate limit (429). Bir sure sonra tekrar dene; "
        "billing ve usage limitlerini kontrol et."
    )


def format_provider_error(exc, provider):
    message = str(exc)
    if _is_auth_or_key_error(exc):
        if provider == "gemini":
            return (
                "Google AI API anahtari gecersiz veya yanlis. "
                ".env icinde GEMINI_API_KEY=AIza... degerini Google AI Studio'dan "
                "alinan gercek anahtarla degistirin; uygulamayi yeniden baslatin."
            )
        if provider == "groq":
            return (
                "Groq API anahtari gecersiz veya bos. https://console.groq.com/keys adresinden "
                "anahtar olusturun, `.env` icinde yazin:\n"
                "AI_PROVIDER=groq\n"
                "GROQ_API_KEY=gsk-...\n\n"
                "Sunucuyu yeniden baslatin."
            )
        return (
            "OpenAI API anahtari gecersiz — cogu zaman .env dosyasinda ornek metin "
            "kalmis olur (ornek: sk-buraya-openai-keyini-yaz). "
            "https://platform.openai.com/account/api-keys adresinden yeni bir anahtar "
            "olusturun, .env icinde tek satir olarak yazin:\n"
            "OPENAI_API_KEY=sk-proj-... veya sk-...\n\n"
            "Dosyayi kaydedip sunucuyu (python3 app.py) durdurup tekrar baslatin."
        )
    if "429" in message or "RESOURCE_EXHAUSTED" in message or "quota" in message.lower():
        if provider == "openai":
            return (
                "OpenAI tarafinda kota/rate-limit asildi (429). "
                "OpenAI hesabinda bakiye/billing ve usage limitlerini kontrol edin."
            )
        if provider in ("gemini", "groq"):
            return _rate_limit_reply_for_user()
        return (
            "AI saglayicisinda kota/rate-limit asildi (429). "
            "Google AI Studio projesinde billing/quota ayari yapip tekrar deneyin."
        )
    if _is_model_not_found_error(exc):
        return _model_not_found_reply()
    return f"Bir hata olustu: {message}"


@app.route("/api/ai/insight/tracking", methods=["POST"])
def api_ai_insight_tracking():
    device_id = session.get("device_id")
    if not device_id:
        return jsonify({"error": "no_device"}), 400
    if client is None:
        return jsonify({"error": "no_ai", "message": "API anahtari yapilandirilmamis."}), 503
    week = store.week_daily_logs(device_id, 7)
    def _short(text: str | None, n: int) -> str:
        t = (text or "").strip().replace("\n", " ")
        if len(t) > n:
            return t[: n - 3] + "..."
        return t or "-"

    lines = []
    for row in week:
        mood = row.get("mood")
        vit = row.get("vitality")
        note = _short(row.get("note"), 140)
        hx = _short(row.get("hydration_extra"), 100)
        wm = int(row.get("workout_minutes") or 0)
        wd = _short(row.get("workout_detail"), 100)
        nb = _short(row.get("nutrition_breakfast"), 80)
        nl = _short(row.get("nutrition_lunch"), 80)
        nd = _short(row.get("nutrition_dinner"), 80)
        ns = _short(row.get("nutrition_snacks"), 80)
        w_ml = store._water_ml_from_row(dict(row))
        w_l = round(w_ml / 1000, 2)
        lines.append(
            f"- {row['day']}: su {w_l} L, adim {int(row['steps'])}, "
            f"mod {mood if mood is not None else '-'}, yenilenme {vit if vit is not None else '-'}, "
            f"idman {wm} dk ({wd}), ek icecek: {hx}, "
            f"kahvalti {nb}, ogle {nl}, aksam {nd}, ara {ns}, not: {note}"
        )
    blob = "\n".join(lines)
    if len(blob) > 12000:
        blob = blob[:11997] + "..."
    user_msg = "Son 7 gunluk gunluk takip ozeti (bu cihaz):\n" + blob
    try:
        insight = ask_openai(user_msg, [], extra_system=TRACKING_AI_EXTRA, max_tokens=900)
        if not (insight or "").strip():
            return jsonify(
                {
                    "error": "empty_response",
                    "message": "AI bos yanit dondu. Model veya API anahtarini kontrol edin; tekrar deneyin.",
                }
            ), 502
        return jsonify({"insight": insight})
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "API anahtari" in str(exc):
            return jsonify({"error": "no_ai", "message": str(exc)}), 503
        safe = format_provider_error(exc, provider_name)
        return jsonify({"error": "ai_failed", "message": safe}), 500


@app.route("/api/ai/insight/tracking/daily", methods=["POST"])
def api_ai_insight_tracking_daily():
    device_id = session.get("device_id")
    if not device_id:
        return jsonify({"error": "no_device"}), 400
    if client is None:
        return jsonify({"error": "no_ai", "message": "API anahtari yapilandirilmamis."}), 503
    data = request.get_json(silent=True) or {}
    day = (data.get("day") or time.strftime("%Y-%m-%d", time.localtime())).strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return jsonify({"error": "invalid_day"}), 400

    row = store.get_daily_log(device_id, day)
    if row is None:
        row = {
            "day": day,
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
        }

    def _short(text, n):
        t = (text or "").strip().replace("\n", " ")
        if len(t) > n:
            return t[: n - 3] + "..."
        return t or "-"

    mood = row.get("mood")
    vit = row.get("vitality")
    note = _short(row.get("note"), 400)
    hx = _short(row.get("hydration_extra"), 200)
    wm = int(row.get("workout_minutes") or 0)
    wd = _short(row.get("workout_detail"), 200)
    nb = _short(row.get("nutrition_breakfast"), 150)
    nl = _short(row.get("nutrition_lunch"), 150)
    nd = _short(row.get("nutrition_dinner"), 150)
    ns = _short(row.get("nutrition_snacks"), 150)
    w_ml = store._water_ml_from_row(dict(row))
    w_l = round(w_ml / 1000, 2)
    line = (
        f"Tarih: {row.get('day') or day}\n"
        f"- Su: {w_l} L, adim: {int(row.get('steps') or 0)}, "
        f"mod: {mood if mood is not None else '-'}, yenilenme: {vit if vit is not None else '-'}\n"
        f"- Idman: {wm} dk — {wd}\n"
        f"- Ek icecek notu: {hx}\n"
        f"- Kahvalti: {nb}, ogle: {nl}, aksam: {nd}, ara ogun: {ns}\n"
        f"- Gunluk not: {note}"
    )
    if len(line) > 8000:
        line = line[:7997] + "..."
    user_msg = "Tek gunluk takip kaydi (bu cihaz):\n" + line
    try:
        insight = ask_openai(user_msg, [], extra_system=TRACKING_DAILY_AI_EXTRA, max_tokens=650)
        if not (insight or "").strip():
            return jsonify(
                {
                    "error": "empty_response",
                    "message": "AI bos yanit dondu. Model veya API anahtarini kontrol edin; tekrar deneyin.",
                }
            ), 502
        return jsonify({"insight": insight})
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "API anahtari" in str(exc):
            return jsonify({"error": "no_ai", "message": str(exc)}), 503
        safe = format_provider_error(exc, provider_name)
        return jsonify({"error": "ai_failed", "message": safe}), 500


@app.route("/api/ai/insight/bmi", methods=["POST"])
def api_ai_insight_bmi():
    if client is None:
        return jsonify({"error": "no_ai", "message": "API anahtari yapilandirilmamis."}), 503
    data = request.get_json(silent=True) or {}
    try:
        height = float(data.get("height"))
        weight = float(data.get("weight"))
        bmi = float(data.get("bmi"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_payload"}), 400
    category = (data.get("category") or "").strip() or "—"
    user_msg = (
        f"Boy: {height} cm, Kilo: {weight} kg, BMI: {round(bmi, 1)}, "
        f"Sinif (yaklasik): {category}\n"
        "Bu bilgilere gore genel bilgilendirici yorum istiyorum."
    )
    try:
        insight = ask_openai(user_msg, [], extra_system=BMI_AI_EXTRA, max_tokens=550)
        return jsonify({"insight": insight})
    except Exception as exc:
        if isinstance(exc, RuntimeError) and "API anahtari" in str(exc):
            return jsonify({"error": "no_ai", "message": str(exc)}), 503
        safe = format_provider_error(exc, provider_name)
        return jsonify({"error": "ai_failed", "message": safe}), 500


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "ai_configured": client is not None,
        }
    )


@app.route("/sw.js")
def service_worker():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "sw.js",
        mimetype="application/javascript",
    )


@app.route("/offline.html")
def offline_page():
    return send_from_directory(os.path.join(app.root_path, "static"), "offline.html")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/conversations", methods=["GET"])
def api_list_conversations():
    device_id = session.get("device_id")
    items = store.list_conversations(device_id, limit=80)
    current = session.get("current_conversation_id")
    resp = jsonify({"conversations": items, "current_id": current})
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _int_or_none(val):
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _str_or_none(val):
    """JSON'dan gelen istege bagli metin alanlari: yalnizca str ise gonder (yoksa None = degistirme)."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return None


def _conversation_delete_response(cid: str):
    """Sohbet sil; tarayici/proksi DELETE engelliyorsa POST /.../delete ayni sonucu doner."""
    device_id = session.get("device_id")
    if not device_id:
        return jsonify({"error": "no_device"}), 400
    if not store.delete_conversation(device_id, cid):
        return jsonify({"error": "not_found"}), 404
    cur = session.get("current_conversation_id")
    if cid == cur:
        session["current_conversation_id"] = None
        session.pop("chat_history", None)
        reset_calorie_state()
        reset_goal_state()
        session.modified = True
        return jsonify({"ok": True, "conversation_id": None, "cleared": True})
    session.modified = True
    return jsonify({"ok": True})


@app.route("/api/conversations/<cid>/delete", methods=["POST"])
def api_conversation_delete_post(cid):
    return _conversation_delete_response(cid)


@app.route("/api/conversations/<cid>", methods=["GET", "PATCH", "DELETE"])
def api_conversation_item(cid):
    device_id = session.get("device_id")

    if request.method == "GET":
        conv = store.get_conversation(device_id, cid)
        if not conv:
            return jsonify({"error": "not_found"}), 404
        messages = store.list_messages(device_id, cid)
        return jsonify({"conversation": conv, "messages": messages})

    if request.method == "PATCH":
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title_required"}), 400
        if not store.rename_conversation(device_id, cid, title):
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    return _conversation_delete_response(cid)


@app.route("/api/conversations/<cid>/open", methods=["POST"])
def api_open_conversation(cid):
    device_id = session.get("device_id")
    if not store.get_conversation(device_id, cid):
        return jsonify({"error": "not_found"}), 404
    session["current_conversation_id"] = cid
    reset_calorie_state()
    reset_goal_state()
    rows = store.list_messages(device_id, cid)
    hist = []
    for r in rows:
        hist.append({"role": r["role"], "content": r["content"]})
    hist = _normalize_history(hist)
    cap = _max_session_stored_messages()
    if len(hist) > cap:
        hist = hist[-cap:]
    session["chat_history"] = hist
    session.modified = True
    return jsonify(
        {
            "ok": True,
            "conversation_id": cid,
            "messages": [{"role": r["role"], "content": r["content"]} for r in rows],
        }
    )


@app.route("/api/summary/week", methods=["GET"])
def api_week_summary():
    device_id = session.get("device_id")
    summary = store.weekly_summary(device_id)
    return jsonify(summary)


@app.route("/api/tracking/daily", methods=["GET", "POST"])
def api_tracking_daily():
    device_id = session.get("device_id")
    if not device_id:
        return jsonify({"error": "no_device"}), 400
    if request.method == "GET":
        day = (request.args.get("day") or "").strip()[:10]
        if not day:
            day = time.strftime("%Y-%m-%d", time.localtime())
        today = store.get_daily_log(device_id, day) or {
            "day": day,
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
        }
        week = store.week_daily_logs(device_id, 7)
        return jsonify({"today": today, "week": week})
    data = request.get_json(silent=True) or {}
    day = (data.get("day") or time.strftime("%Y-%m-%d", time.localtime())).strip()[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        return jsonify({"error": "invalid_day"}), 400
    log = store.upsert_daily_log(
        device_id,
        day,
        water_ml=_int_or_none(data.get("water_ml")),
        steps=_int_or_none(data.get("steps")),
        mood=_int_or_none(data.get("mood")),
        note=_str_or_none(data.get("note")),
        hydration_extra=_str_or_none(data.get("hydration_extra")),
        workout_minutes=_int_or_none(data.get("workout_minutes")),
        workout_detail=_str_or_none(data.get("workout_detail")),
        nutrition_breakfast=_str_or_none(data.get("nutrition_breakfast")),
        nutrition_lunch=_str_or_none(data.get("nutrition_lunch")),
        nutrition_dinner=_str_or_none(data.get("nutrition_dinner")),
        nutrition_snacks=_str_or_none(data.get("nutrition_snacks")),
        vitality=_int_or_none(data.get("vitality")),
    )
    return jsonify({"ok": True, "log": log})


@app.route("/chat/reset", methods=["POST"])
def chat_reset():
    device_id = session.get("device_id")
    new_id = store.create_conversation(device_id)
    session["current_conversation_id"] = new_id
    clear_chat_session()
    session.modified = True
    return jsonify({"ok": True, "conversation_id": new_id})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"reply": "Lütfen bir mesaj yazın."}), 400

    _ensure_current_conversation_id()

    try:
        flow_reply = handle_calorie_flow(user_message)
        if flow_reply is None:
            flow_reply = handle_goal_flow(user_message)

        if flow_reply is not None:
            append_chat_turn(user_message, flow_reply)
            return jsonify({"reply": flow_reply})

        prior = _prior_for_model()
        ai_reply = ask_openai(user_message, prior)
        append_chat_turn(user_message, ai_reply)
        return jsonify({"reply": ai_reply})

    except Exception as exc:
        if isinstance(exc, RuntimeError) and "API anahtari" in str(exc):
            msg = str(exc)
            append_chat_turn(user_message, msg)
            return jsonify({"reply": msg})

        if _is_transient_ai_error(exc):
            reply = _transient_failure_reply(exc)
            append_chat_turn(user_message, reply)
            return jsonify({"reply": reply})

        if _is_auth_or_key_error(exc):
            safe = format_provider_error(exc, provider_name)
            append_chat_turn(user_message, safe)
            return jsonify({"reply": safe})

        if _is_model_not_found_error(exc):
            reply = _model_not_found_reply()
            append_chat_turn(user_message, reply)
            return jsonify({"reply": reply})

        if isinstance(exc, APITimeoutError):
            reply = (
                "Yapay zeka yaniti cok uzun surdu veya baglanti zaman asimina ugradi. "
                "Tekrar dene; cok uzun tarif istiyorsan .env icinde AI_MAX_OUTPUT_TOKENS "
                "degerini biraz dusurmek yanit suresini kisaltabilir."
            )
            return jsonify({"reply": reply}), 504

        safe_error = format_provider_error(exc, provider_name)
        return jsonify({"reply": safe_error}), 500


def _sse_data(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "empty_message"}), 400

    def generate():
        _ensure_current_conversation_id()
        full_parts: list[str] = []
        try:
            flow_reply = handle_calorie_flow(user_message)
            if flow_reply is None:
                flow_reply = handle_goal_flow(user_message)

            if flow_reply is not None:
                full_parts.append(flow_reply)
                yield _sse_data({"type": "delta", "text": flow_reply})
            else:
                if client is None:
                    err = (
                        "API anahtari bulunamadi. OpenAI icin OPENAI_API_KEY=sk-... "
                        "veya Google AI Studio icin GEMINI_API_KEY=AIza... ayarlayin."
                    )
                    full_parts.append(err)
                    yield _sse_data({"type": "delta", "text": err})
                else:
                    prior = _prior_for_model()
                    for piece in ask_openai_stream(user_message, prior):
                        full_parts.append(piece)
                        yield _sse_data({"type": "delta", "text": piece})

            text = "".join(full_parts).strip()
            if text:
                append_chat_turn(user_message, text)
            yield _sse_data({"type": "done"})

        except Exception as exc:
            if isinstance(exc, RuntimeError) and "API anahtari" in str(exc):
                msg = str(exc)
                yield _sse_data({"type": "error", "message": msg})
                append_chat_turn(user_message, msg)
                yield _sse_data({"type": "done"})
                return

            if _is_transient_ai_error(exc):
                reply = _transient_failure_reply(exc)
                yield _sse_data({"type": "delta", "text": reply})
                append_chat_turn(user_message, reply)
                yield _sse_data({"type": "done"})
                return

            if _is_auth_or_key_error(exc):
                safe = format_provider_error(exc, provider_name)
                yield _sse_data({"type": "delta", "text": safe})
                append_chat_turn(user_message, safe)
                yield _sse_data({"type": "done"})
                return

            if _is_model_not_found_error(exc):
                reply = _model_not_found_reply()
                yield _sse_data({"type": "delta", "text": reply})
                append_chat_turn(user_message, reply)
                yield _sse_data({"type": "done"})
                return

            if isinstance(exc, APITimeoutError):
                reply = (
                    "Yapay zeka yaniti cok uzun surdu veya baglanti zaman asimina ugradi. "
                    "Tekrar dene; cok uzun tarif istiyorsan .env icinde AI_MAX_OUTPUT_TOKENS "
                    "degerini biraz dusurmek yanit suresini kisaltabilir."
                )
                yield _sse_data({"type": "error", "message": reply})
                yield _sse_data({"type": "done"})
                return

            safe_error = format_provider_error(exc, provider_name)
            yield _sse_data({"type": "delta", "text": safe_error})
            append_chat_turn(user_message, safe_error)
            yield _sse_data({"type": "done"})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False, use_reloader=False)
