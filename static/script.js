const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const chatBox = document.getElementById("chat-box");
const sendBtn = document.getElementById("send-btn");
const resetBtn = document.getElementById("reset-chat");
const exportBtn = document.getElementById("export-chat");
const charCount = document.getElementById("char-count");
const themeToggle = document.getElementById("theme-toggle");
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const toastEl = document.getElementById("toast");
const sideNavItems = document.querySelectorAll(".side-nav-item");
const panelChat = document.getElementById("panel-chat");
const panelTracking = document.getElementById("panel-tracking");
const panelBmi = document.getElementById("panel-bmi");
const trackWeekBars = document.getElementById("track-week-bars");
const trackWater = document.getElementById("track-water");
const trackSteps = document.getElementById("track-steps");
const trackMood = document.getElementById("track-mood");
const trackNote = document.getElementById("track-note");
const trackVitality = document.getElementById("track-vitality");
const trackWorkoutMinutes = document.getElementById("track-workout-minutes");
const trackWorkoutDetail = document.getElementById("track-workout-detail");
const trackNutritionBreakfast = document.getElementById("track-nutrition-breakfast");
const trackNutritionLunch = document.getElementById("track-nutrition-lunch");
const trackNutritionDinner = document.getElementById("track-nutrition-dinner");
const trackNutritionSnacks = document.getElementById("track-nutrition-snacks");
const trackHydrationExtra = document.getElementById("track-hydration-extra");
const trackSave = document.getElementById("track-save");
const valWater = document.getElementById("val-water");
const valSteps = document.getElementById("val-steps");
const valMood = document.getElementById("val-mood");
const valWorkout = document.getElementById("val-workout");
const valVitality = document.getElementById("val-vitality");
const ringWater = document.getElementById("ring-water");
const ringSteps = document.getElementById("ring-steps");
const ringMood = document.getElementById("ring-mood");
const bmiHeight = document.getElementById("bmi-height");
const bmiWeight = document.getElementById("bmi-weight");
const bmiCalc = document.getElementById("bmi-calc");
const bmiResult = document.getElementById("bmi-result");
const bmiAiBtn = document.getElementById("bmi-ai-btn");
const bmiAiOutput = document.getElementById("bmi-ai-output");
const bmiAiBody = document.getElementById("bmi-ai-body");
const trackDayInput = document.getElementById("track-day-input");
const trackTodayBtn = document.getElementById("track-today-btn");
const trackSelectedHeading = document.getElementById("track-selected-heading");
const trackPastBanner = document.getElementById("track-past-banner");
const trackFormLead = document.getElementById("track-form-lead");
const trackWeekStrip = document.getElementById("track-week-strip");
const trackWeekRecapList = document.getElementById("track-week-recap-list");
const trackAiInsight = document.getElementById("track-ai-insight");
const trackAiOutput = document.getElementById("track-ai-output");
const trackAiBody = document.getElementById("track-ai-body");
const trackDailySummaryBody = document.getElementById("track-daily-summary-body");
const trackSaveHint = document.getElementById("track-save-hint");
const trackDailyAiBtn = document.getElementById("track-daily-ai-btn");
const trackDailyAiBody = document.getElementById("track-daily-ai-body");
const convList = document.getElementById("conv-list");
const weekStats = document.getElementById("week-stats");
const refreshArchiveBtn = document.getElementById("refresh-archive");
const voiceBtn = document.getElementById("voice-btn");
const readLastBtn = document.getElementById("read-last-btn");

const WELCOME_TEXT =
  "Merhaba! Beslenme, egzersiz ve günlük alışkanlıklarınızda yanınızdayım. Nereden başlayalım?";

let lastBmiPayload = null;

const THEME_KEY = "lifeplus-theme";

let trackingPanelToday = null;
let trackingSnapshotBaseline = null;

/** Günlük su hedefi (ml); gösterim için ~2 L */
const WATER_GOAL_ML = 2000;
const WATER_MAX_ML = 8000;

let currentConversationId = null;
let archiveRefreshTimer = null;

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatBotHtml(raw) {
  const esc = escapeHtml(raw);
  const bolded = esc.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const chunks = bolded.split(/\n\n+/).filter((c) => c.length);
  if (chunks.length <= 1) {
    return `<p>${bolded.replace(/\n/g, "<br>")}</p>`;
  }
  return chunks.map((c) => `<p>${c.replace(/\n/g, "<br>")}</p>`).join("");
}

function showToast(message, ms = 2800) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.hidden = false;
  requestAnimationFrame(() => {
    toastEl.classList.add("is-visible");
  });
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toastEl.classList.remove("is-visible");
    setTimeout(() => {
      toastEl.hidden = true;
    }, 350);
  }, ms);
}

function appendMessage(text, sender) {
  const article = document.createElement("article");
  article.classList.add("message", sender);

  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = sender === "user" ? "Sen" : "Asistan";

  const body = document.createElement("div");
  body.className = "message-body";
  if (sender === "bot") {
    body.innerHTML = formatBotHtml(text);
  } else {
    body.textContent = text;
  }

  article.appendChild(meta);
  article.appendChild(body);
  chatBox.appendChild(article);
  chatBox.scrollTop = chatBox.scrollHeight;
  return article;
}

function appendWelcomeMessage() {
  const article = document.createElement("article");
  article.classList.add("message", "bot", "message-welcome");
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = "Asistan";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = WELCOME_TEXT;
  article.appendChild(meta);
  article.appendChild(body);
  chatBox.appendChild(article);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function renderChatFromMessages(messages) {
  chatBox.innerHTML = "";
  const list = Array.isArray(messages) ? messages : [];
  if (list.length === 0) {
    appendWelcomeMessage();
    return;
  }
  for (const m of list) {
    const role = m.role === "user" ? "user" : "bot";
    appendMessage(m.content || "", role);
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

function setLoading(isLoading) {
  sendBtn.disabled = isLoading;
  messageInput.disabled = isLoading;
  sendBtn.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function localDayString() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getTrackingDay() {
  if (trackDayInput && trackDayInput.value) return trackDayInput.value;
  return localDayString();
}

function formatTrackingDateLong(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return iso || "";
  const dt = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  try {
    return dt.toLocaleDateString("tr-TR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function waterMlFromRow(row) {
  if (!row) return 0;
  if (row.water_ml != null && row.water_ml !== "") {
    const v = Number(row.water_ml);
    if (Number.isFinite(v)) return Math.max(0, Math.min(WATER_MAX_ML, Math.round(v)));
  }
  const g = Number(row.water_glasses) || 0;
  return Math.max(0, Math.min(WATER_MAX_ML, Math.round(g * 250)));
}

function parseLitersInputToMl(raw) {
  const s = String(raw ?? "")
    .trim()
    .replace(/\s/g, "")
    .replace(",", ".");
  if (s === "") return 0;
  const n = Number.parseFloat(s);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(WATER_MAX_ML, Math.round(n * 1000));
}

function formatLitersDisplay(ml) {
  const m = Math.max(0, Number(ml) || 0);
  if (m === 0) return "0";
  const L = m / 1000;
  return L.toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function mlToWaterInputValue(ml) {
  const m = Math.max(0, Number(ml) || 0);
  if (m === 0) return "";
  const L = m / 1000;
  const x = Math.round(L * 100) / 100;
  return String(x);
}

function trackingRowHasData(row) {
  if (!row) return false;
  const w = waterMlFromRow(row);
  const s = Number(row.steps) || 0;
  if (w > 0 || s > 0) return true;
  if (row.mood != null && row.mood !== "") return true;
  if (row.vitality != null && row.vitality !== "") return true;
  if ((Number(row.workout_minutes) || 0) > 0) return true;
  const fields = [
    row.note,
    row.hydration_extra,
    row.workout_detail,
    row.nutrition_breakfast,
    row.nutrition_lunch,
    row.nutrition_dinner,
    row.nutrition_snacks,
  ];
  return fields.some((t) => (t || "").toString().trim().length > 0);
}

function trackingRowSummary(row) {
  const parts = [];
  const wMl = waterMlFromRow(row);
  const s = Number(row.steps) || 0;
  if (wMl) parts.push(`${formatLitersDisplay(wMl)} L su`);
  if (s) parts.push(`${s} adım`);
  if (row.mood != null && row.mood !== "") parts.push(`mod ${row.mood}/5`);
  const note = (row.note || "").trim();
  if (note) {
    parts.push(note.length > 80 ? `${note.slice(0, 77)}…` : note);
  } else {
    const meal = (row.nutrition_breakfast || row.nutrition_lunch || row.nutrition_dinner || "").trim();
    if (meal) parts.push(meal.length > 64 ? `${meal.slice(0, 61)}…` : meal);
  }
  if (parts.length === 0) return "Henüz kayıt yok";
  return parts.join(" · ");
}

function formatTrackingDateTime(ts) {
  if (ts == null || ts === "") return "";
  try {
    return new Date(Number(ts) * 1000).toLocaleString("tr-TR", {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function buildTrackingSnapshotFromForm() {
  return JSON.stringify({
    water_ml: parseLitersInputToMl(trackWater ? trackWater.value : ""),
    steps: trackSteps && trackSteps.value !== "" ? Number(trackSteps.value) : "",
    mood: trackMood && trackMood.value !== "" ? Number(trackMood.value) : "",
    vitality: trackVitality && trackVitality.value !== "" ? Number(trackVitality.value) : "",
    workout_minutes:
      trackWorkoutMinutes && trackWorkoutMinutes.value !== "" ? Number(trackWorkoutMinutes.value) : "",
    workout_detail: trackWorkoutDetail ? trackWorkoutDetail.value.trim() : "",
    nutrition_breakfast: trackNutritionBreakfast ? trackNutritionBreakfast.value.trim() : "",
    nutrition_lunch: trackNutritionLunch ? trackNutritionLunch.value.trim() : "",
    nutrition_dinner: trackNutritionDinner ? trackNutritionDinner.value.trim() : "",
    nutrition_snacks: trackNutritionSnacks ? trackNutritionSnacks.value.trim() : "",
    hydration_extra: trackHydrationExtra ? trackHydrationExtra.value.trim() : "",
    note: trackNote ? trackNote.value.trim() : "",
  });
}

function isTrackingDirty() {
  if (trackingSnapshotBaseline === null) return false;
  return buildTrackingSnapshotFromForm() !== trackingSnapshotBaseline;
}

function updateTrackSaveHint(today) {
  if (!trackSaveHint) return;
  const dirty = isTrackingDirty();
  let main = "";
  if (today && today.updated_at != null && Number(today.updated_at) > 0) {
    const ft = formatTrackingDateTime(today.updated_at);
    if (ft) main = `Son kayıt: ${ft}`;
  }
  if (!main) {
    main = "Bu tarih için henüz kayıt yok; Kaydet ile bu cihaza yazılır.";
  }
  trackSaveHint.textContent = dirty ? `Kaydedilmemiş değişiklikler var. · ${main}` : main;
}

function refreshTrackingSaveHint() {
  if (trackingPanelToday) updateTrackSaveHint(trackingPanelToday);
}

function truncateSummaryText(s, max) {
  const t = (s || "").trim();
  if (!t) return "";
  return t.length > max ? `${t.slice(0, max - 1)}…` : t;
}

function buildTodayFromForm() {
  const day = getTrackingDay();
  const wMl = parseLitersInputToMl(trackWater ? trackWater.value : "");
  const stepsRaw = trackSteps && trackSteps.value !== "" ? Number(trackSteps.value) : 0;
  const mood =
    trackMood && trackMood.value !== "" && !Number.isNaN(Number(trackMood.value))
      ? Number(trackMood.value)
      : null;
  const vit =
    trackVitality && trackVitality.value !== "" && !Number.isNaN(Number(trackVitality.value))
      ? Number(trackVitality.value)
      : null;
  const wm =
    trackWorkoutMinutes && trackWorkoutMinutes.value !== ""
      ? Number(trackWorkoutMinutes.value) || 0
      : 0;
  return {
    day,
    water_ml: wMl,
    steps: stepsRaw,
    mood,
    vitality: vit,
    workout_minutes: wm,
    workout_detail: trackWorkoutDetail ? trackWorkoutDetail.value : "",
    nutrition_breakfast: trackNutritionBreakfast ? trackNutritionBreakfast.value : "",
    nutrition_lunch: trackNutritionLunch ? trackNutritionLunch.value : "",
    nutrition_dinner: trackNutritionDinner ? trackNutritionDinner.value : "",
    nutrition_snacks: trackNutritionSnacks ? trackNutritionSnacks.value : "",
    hydration_extra: trackHydrationExtra ? trackHydrationExtra.value : "",
    note: trackNote ? trackNote.value : "",
    updated_at: trackingPanelToday ? trackingPanelToday.updated_at : null,
  };
}

function renderDailySummary(today) {
  if (!trackDailySummaryBody) return;
  if (!trackingRowHasData(today)) {
    trackDailySummaryBody.innerHTML =
      '<p class="track-summary-empty">Bu gün için henüz kayıt yok. Sağdaki formu doldurup Kaydet butonuna basın.</p>';
    return;
  }
  const chunks = [];
  const wMl = waterMlFromRow(today);
  const goalL = WATER_GOAL_ML / 1000;
  chunks.push(
    `<div class="track-summary-row"><span class="track-summary-k">Su</span><span class="track-summary-v">${escapeHtml(formatLitersDisplay(wMl))} / ${escapeHtml(String(goalL))} L (hedef)</span></div>`
  );
  const s = Number(today.steps) || 0;
  if (s > 0) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Adım</span><span class="track-summary-v">${escapeHtml(String(s))}</span></div>`
    );
  }
  if (today.mood != null && today.mood !== "") {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Mod</span><span class="track-summary-v">${escapeHtml(String(today.mood))} / 5</span></div>`
    );
  }
  if (today.vitality != null && today.vitality !== "") {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Yenilenme</span><span class="track-summary-v">${escapeHtml(String(today.vitality))} / 5</span></div>`
    );
  }
  const wm = Number(today.workout_minutes) || 0;
  const wdRaw = (today.workout_detail || "").trim();
  const wd = truncateSummaryText(wdRaw, 140);
  if (wm > 0 || wd) {
    const parts = [];
    if (wm > 0) parts.push(`${wm} dk`);
    if (wd) parts.push(wd);
    const line = escapeHtml(parts.join(" · "));
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">İdman</span><span class="track-summary-v">${line}</span></div>`
    );
  }
  const nb = truncateSummaryText(today.nutrition_breakfast, 120);
  if (nb) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Kahvaltı</span><span class="track-summary-v">${escapeHtml(nb)}</span></div>`
    );
  }
  const nl = truncateSummaryText(today.nutrition_lunch, 120);
  if (nl) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Öğle</span><span class="track-summary-v">${escapeHtml(nl)}</span></div>`
    );
  }
  const nd = truncateSummaryText(today.nutrition_dinner, 120);
  if (nd) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Akşam</span><span class="track-summary-v">${escapeHtml(nd)}</span></div>`
    );
  }
  const ns = truncateSummaryText(today.nutrition_snacks, 100);
  if (ns) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Ara öğün</span><span class="track-summary-v">${escapeHtml(ns)}</span></div>`
    );
  }
  const hx = truncateSummaryText(today.hydration_extra, 160);
  if (hx) {
    chunks.push(
      `<div class="track-summary-row"><span class="track-summary-k">Ek sıvı</span><span class="track-summary-v">${escapeHtml(hx)}</span></div>`
    );
  }
  const note = (today.note || "").trim();
  if (note) {
    chunks.push(
      `<div class="track-summary-note"><span class="track-summary-k">Günlük not</span><p>${escapeHtml(
        truncateSummaryText(note, 480)
      )}</p></div>`
    );
  }
  trackDailySummaryBody.innerHTML = chunks.join("");
}

function setMainTab(tabId) {
  sideNavItems.forEach((t) => {
    const active = t.getAttribute("data-tab") === tabId;
    t.classList.toggle("is-active", active);
    t.setAttribute("aria-selected", active ? "true" : "false");
  });
  if (panelChat) panelChat.classList.toggle("is-visible", tabId === "chat");
  if (panelTracking) panelTracking.classList.toggle("is-visible", tabId === "tracking");
  if (panelBmi) panelBmi.classList.toggle("is-visible", tabId === "bmi");
  if (tabId === "chat" && messageInput) messageInput.focus();
  if (tabId === "tracking") loadTrackingPanel();
}

function applyTrackingVisuals(wMl, s, mood, workoutMin, vitality) {
  const wi = Math.max(0, Math.min(WATER_MAX_ML, Number(wMl) || 0));
  const st = Math.max(0, Number(s) || 0);
  const wm = Math.max(0, Math.min(600, Number(workoutMin) || 0));
  if (valWater) valWater.textContent = formatLitersDisplay(wi);
  if (valSteps) valSteps.textContent = st ? String(st) : "0";
  if (valMood) valMood.textContent = mood != null && mood !== "" ? String(mood) : "—";
  if (valWorkout) valWorkout.textContent = String(wm);
  if (valVitality) {
    valVitality.textContent =
      vitality != null && vitality !== "" && !Number.isNaN(Number(vitality)) ? String(vitality) : "—";
  }
  if (ringWater)
    ringWater.style.setProperty("--p", String(Math.min(100, (wi / WATER_GOAL_ML) * 100)));
  if (ringSteps) ringSteps.style.setProperty("--p", String(Math.min(100, (st / 12000) * 100)));
  if (ringMood) {
    const m = mood != null && mood !== "" ? Number(mood) : 0;
    ringMood.style.setProperty("--p", m > 0 ? String((m / 5) * 100) : "0");
  }
}

async function loadTrackingPanel() {
  if (!trackWeekBars) return;
  try {
    if (trackDayInput) {
      const t = localDayString();
      trackDayInput.max = t;
    }
    const day = getTrackingDay();
    const r = await fetch(`/api/tracking/daily?day=${encodeURIComponent(day)}`, {
      credentials: "same-origin",
    });
    if (!r.ok) return;
    const data = await r.json();
    const today = data.today || {};
    trackingPanelToday = today;
    resetDailyAiPanel();
    const dayIso = (today.day || day).toString().slice(0, 10);
    if (trackDayInput) trackDayInput.value = dayIso;

    const wMl = waterMlFromRow(today);
    const s = Number(today.steps) || 0;
    const mood = today.mood != null && today.mood !== "" ? Number(today.mood) : null;
    if (trackWater) trackWater.value = mlToWaterInputValue(wMl);
    if (trackSteps) trackSteps.value = s ? String(s) : "";
    if (trackMood) trackMood.value = mood != null && !Number.isNaN(mood) ? String(mood) : "";
    const vit =
      today.vitality != null && today.vitality !== "" ? Number(today.vitality) : null;
    if (trackVitality) trackVitality.value = vit != null && !Number.isNaN(vit) ? String(vit) : "";
    const wm = Number(today.workout_minutes) || 0;
    if (trackWorkoutMinutes) trackWorkoutMinutes.value = wm ? String(wm) : "";
    if (trackWorkoutDetail) trackWorkoutDetail.value = today.workout_detail || "";
    if (trackNutritionBreakfast) trackNutritionBreakfast.value = today.nutrition_breakfast || "";
    if (trackNutritionLunch) trackNutritionLunch.value = today.nutrition_lunch || "";
    if (trackNutritionDinner) trackNutritionDinner.value = today.nutrition_dinner || "";
    if (trackNutritionSnacks) trackNutritionSnacks.value = today.nutrition_snacks || "";
    if (trackHydrationExtra) trackHydrationExtra.value = today.hydration_extra || "";
    if (trackNote) trackNote.value = today.note || "";
    applyTrackingVisuals(wMl, s, mood, wm, vit);

    const todayCalendar = localDayString();
    if (trackSelectedHeading) trackSelectedHeading.textContent = formatTrackingDateLong(dayIso);
    if (trackPastBanner) {
      if (dayIso !== todayCalendar) {
        trackPastBanner.hidden = false;
        trackPastBanner.textContent = `Geçmiş gün: ${formatTrackingDateLong(dayIso)}. Kaydettiğinizde veriler bu tarihe yazılır.`;
      } else {
        trackPastBanner.hidden = true;
      }
    }
    if (trackFormLead) {
      trackFormLead.textContent =
        dayIso === todayCalendar
          ? "Bugünün kaydını aşağıda düzenleyip saklayın."
          : `${formatTrackingDateLong(dayIso)} tarihli kayıt — istediğiniz gibi güncelleyebilirsiniz.`;
    }

    const week = data.week || [];

    if (trackWeekStrip) {
      trackWeekStrip.innerHTML = "";
      week.forEach((row) => {
        const iso = (row.day || "").slice(0, 10);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "track-day-pill";
        btn.setAttribute("role", "tab");
        btn.setAttribute("aria-selected", iso === dayIso ? "true" : "false");
        btn.dataset.day = iso;
        if (iso === dayIso) btn.classList.add("is-active");
        if (trackingRowHasData(row)) btn.classList.add("has-data");
        const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
        let wd = "";
        let num = "";
        if (dm) {
          const dt = new Date(Number(dm[1]), Number(dm[2]) - 1, Number(dm[3]));
          wd = dt.toLocaleDateString("tr-TR", { weekday: "short" });
          num = dm[3];
        }
        btn.innerHTML = `<span class="track-day-pill-wd">${escapeHtml(wd)}</span><span class="track-day-pill-num">${escapeHtml(num)}</span>`;
        btn.addEventListener("click", () => {
          if (trackDayInput) trackDayInput.value = iso;
          loadTrackingPanel();
        });
        trackWeekStrip.appendChild(btn);
      });
    }

    if (trackWeekRecapList) {
      trackWeekRecapList.innerHTML = "";
      [...week].reverse().forEach((row) => {
        const iso = (row.day || "").slice(0, 10);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "track-recap-item";
        if (iso === dayIso) btn.classList.add("is-active");
        const title = formatTrackingDateLong(iso);
        const sum = trackingRowSummary(row);
        btn.innerHTML = `<span class="track-recap-date">${escapeHtml(title)}</span><span class="track-recap-summary">${escapeHtml(sum)}</span>`;
        btn.addEventListener("click", () => {
          if (trackDayInput) trackDayInput.value = iso;
          loadTrackingPanel();
        });
        trackWeekRecapList.appendChild(btn);
      });
    }

    trackWeekBars.innerHTML = "";
    week.forEach((row) => {
      const col = document.createElement("div");
      col.className = "track-bar-col";
      const stack = document.createElement("div");
      stack.className = "track-bar-stack";
      const ml = waterMlFromRow(row);
      const steps = Number(row.steps) || 0;
      const barW = document.createElement("div");
      barW.className = "track-bar track-bar-water";
      barW.style.height = `${Math.max(Math.min(88, (ml / 3000) * 88), 6)}px`;
      const barS = document.createElement("div");
      barS.className = "track-bar track-bar-steps";
      barS.style.height = `${Math.max(Math.min(88, (steps / 12000) * 88), 5)}px`;
      stack.append(barW, barS);
      const label = document.createElement("span");
      label.className = "track-bar-day";
      const parts = (row.day || "").split("-");
      label.textContent = parts.length === 3 ? `${parts[2]}.${parts[1]}` : row.day || "";
      col.append(stack, label);
      trackWeekBars.appendChild(col);
    });

    renderDailySummary(buildTodayFromForm());
    trackingSnapshotBaseline = buildTrackingSnapshotFromForm();
    updateTrackSaveHint(today);
  } catch {
    /* ignore */
  }
}

/** Tarayici AbortSignal.timeout yoksa (eski Safari) yedek. */
function fetchTimeoutSignal(ms) {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    return AbortSignal.timeout(ms);
  }
  const c = new AbortController();
  setTimeout(() => c.abort(), ms);
  return c.signal;
}

/** Sunucu AI_REQUEST_TIMEOUT_SECONDS tavanı (600) + pay; daha kisa tutma yoksa erken kesilir. */
const CHAT_FETCH_TIMEOUT_MS = 630000;

/**
 * SSE (data: {...}\\n\\n) — asistan metnini parca parca alir.
 * @returns {Promise<string>} tam metin
 */
async function streamAssistantReply(message, bodyEl, signal) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    let msg = `Sunucu hatası (${response.status}).`;
    try {
      const err = await response.json();
      if (err.error) msg = String(err.error);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  const processBlock = (block) => {
    const raw = block.trim();
    if (!raw.startsWith("data:")) return;
    const line = raw.slice(5).trim();
    if (!line) return;
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      return;
    }
    if (obj.type === "delta") {
      fullText += obj.text || "";
      bodyEl.textContent = fullText;
      chatBox.scrollTop = chatBox.scrollHeight;
    } else if (obj.type === "error") {
      throw new Error(obj.message || "Bilinmeyen hata");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      processBlock(block);
    }
  }
  if (buffer.trim()) {
    for (const part of buffer.split("\n\n")) {
      processBlock(part);
    }
  }
  return fullText;
}

function resizeTextarea() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 160)}px`;
}

function updateCharCount() {
  const n = messageInput.value.length;
  if (charCount) charCount.textContent = `${n} / 16000`;
}

function formatShortDate(ts) {
  if (!ts && ts !== 0) return "";
  try {
    return new Date(ts * 1000).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function scheduleArchiveRefresh() {
  clearTimeout(archiveRefreshTimer);
  archiveRefreshTimer = setTimeout(() => {
    refreshArchive();
    refreshWeekSummary();
  }, 400);
}

async function refreshWeekSummary() {
  if (!weekStats) return;
  try {
    const r = await fetch("/api/summary/week", { credentials: "same-origin" });
    if (!r.ok) return;
    const s = await r.json();
    weekStats.innerHTML = `
      <div class="week-row"><dt>Mesaj</dt><dd>${escapeHtml(String(s.messages_total ?? 0))}</dd></div>
      <div class="week-row"><dt>Yeni sohbet</dt><dd>${escapeHtml(String(s.conversations_started ?? 0))}</dd></div>
      <div class="week-row"><dt>Kalori akışı</dt><dd>${escapeHtml(String(s.kalori_flow_starts ?? 0))}</dd></div>
      <div class="week-row"><dt>Hedef akışı</dt><dd>${escapeHtml(String(s.hedef_flow_starts ?? 0))}</dd></div>
    `;
  } catch {
    /* ignore */
  }
}

async function refreshArchive() {
  if (!convList) return;
  try {
    const r = await fetch("/api/conversations", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!r.ok) return;
    const data = await r.json();
    currentConversationId = data.current_id || null;
    const items = data.conversations || [];
    convList.innerHTML = "";
    if (items.length === 0) {
      const li = document.createElement("li");
      li.className = "archive-hint";
      li.style.listStyle = "none";
      li.textContent = "Henüz kayıtlı sohbet yok.";
      convList.appendChild(li);
      return;
    }
    for (const c of items) {
      const li = document.createElement("li");
      li.className = "conv-item";
      if (c.id === currentConversationId) li.classList.add("is-current");
      li.dataset.id = c.id;

      const title = document.createElement("div");
      title.className = "conv-title";
      title.textContent = c.title || "Sohbet";

      const meta = document.createElement("div");
      meta.className = "conv-meta";
      meta.textContent = `${c.message_count || 0} mesaj · ${formatShortDate(c.updated_at)}`;

      const actions = document.createElement("div");
      actions.className = "conv-actions";

      const btnRen = document.createElement("button");
      btnRen.type = "button";
      btnRen.textContent = "Ad";
      btnRen.addEventListener("click", (e) => {
        e.stopPropagation();
        renameConversation(c.id, c.title);
      });

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "danger";
      btnDel.textContent = "Sil";
      btnDel.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c.id);
      });

      actions.append(btnRen, btnDel);
      li.append(title, meta, actions);
      li.addEventListener("click", () => openConversation(c.id));
      convList.appendChild(li);
    }
  } catch {
    /* ignore */
  }
}

async function openConversation(id) {
  try {
    const r = await fetch(`/api/conversations/${encodeURIComponent(id)}/open`, {
      method: "POST",
      credentials: "same-origin",
    });
    const data = await r.json();
    if (!r.ok) {
      showToast("Sohbet açılamadı.");
      return;
    }
    currentConversationId = data.conversation_id || id;
    renderChatFromMessages(data.messages || []);
    refreshArchive();
    showToast("Sohbet yüklendi.");
    if (panelChat && !panelChat.classList.contains("is-visible")) {
      setMainTab("chat");
    }
    messageInput.focus();
  } catch {
    showToast("Bağlantı hatası.");
  }
}

async function renameConversation(id, currentTitle) {
  const t = window.prompt("Yeni başlık", currentTitle || "");
  if (t === null) return;
  const title = String(t).trim();
  if (!title) {
    showToast("Başlık boş olamaz.");
    return;
  }
  try {
    const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!r.ok) {
      showToast("Ad değiştirilemedi.");
      return;
    }
    showToast("Başlık güncellendi.");
    refreshArchive();
  } catch {
    showToast("Bağlantı hatası.");
  }
}

async function deleteConversation(id) {
  if (!window.confirm("Bu sohbeti ve mesajlarını silmek istiyor musunuz?")) return;
  try {
    const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "same-origin",
      cache: "no-store",
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      showToast("Silinemedi.");
      return;
    }
    const removed = convList && convList.querySelector(`li.conv-item[data-id="${id}"]`);
    if (removed) removed.remove();
    if (data.cleared) {
      renderChatFromMessages([]);
      currentConversationId = data.conversation_id || null;
    }
    if (data.cleared) {
      showToast("Sohbet silindi, yeni sohbet açıldı.");
    } else {
      showToast("Sohbet silindi.");
    }
    await refreshArchive();
    refreshWeekSummary();
  } catch {
    showToast("Bağlantı hatası.");
  }
}

messageInput.addEventListener("input", () => {
  resizeTextarea();
  updateCharCount();
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (chatForm.requestSubmit) chatForm.requestSubmit();
    else chatForm.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
  }
});

if (resetBtn) {
  resetBtn.addEventListener("click", async () => {
    try {
      const response = await fetch("/chat/reset", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        showToast("Sohbet sıfırlanamadı.");
        return;
      }
      const data = await response.json().catch(() => ({}));
      currentConversationId = data.conversation_id || currentConversationId;
      chatBox.innerHTML = "";
      appendWelcomeMessage();
      showToast("Yeni sohbet başladı.");
      refreshArchive();
      refreshWeekSummary();
      messageInput.focus();
    } catch {
      showToast("Bağlantı hatası. Sayfayı yenileyin.");
    }
  });
}

if (refreshArchiveBtn) {
  refreshArchiveBtn.addEventListener("click", () => {
    refreshArchive();
    refreshWeekSummary();
    showToast("Liste güncellendi.");
  });
}

if (exportBtn) {
  exportBtn.addEventListener("click", () => {
    const lines = [];
    chatBox.querySelectorAll(".message").forEach((el) => {
      const who = el.classList.contains("user") ? "Sen" : "Asistan";
      const body = el.querySelector(".message-body");
      const text = body ? body.innerText.trim() : "";
      if (text) lines.push(`[${who}]\n${text}\n`);
    });
    if (lines.length === 0) {
      showToast("İndirilecek mesaj yok.");
      return;
    }
    const blob = new Blob([lines.join("\n---\n\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lifeplus-sohbet-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Dosya indirildi.");
  });
}

sideNavItems.forEach((tab) => {
  tab.addEventListener("click", () => {
    const id = tab.getAttribute("data-tab");
    if (id) setMainTab(id);
  });
});

function trackingLiveSummary() {
  applyTrackingVisuals(
    parseLitersInputToMl(trackWater ? trackWater.value : ""),
    trackSteps && trackSteps.value ? Number(trackSteps.value) : 0,
    trackMood && trackMood.value ? Number(trackMood.value) : null,
    trackWorkoutMinutes && trackWorkoutMinutes.value !== ""
      ? Number(trackWorkoutMinutes.value)
      : 0,
    trackVitality && trackVitality.value ? Number(trackVitality.value) : null
  );
  renderDailySummary(buildTodayFromForm());
  refreshTrackingSaveHint();
}

if (trackWater) {
  trackWater.addEventListener("input", trackingLiveSummary);
}
if (trackSteps) {
  trackSteps.addEventListener("input", trackingLiveSummary);
}
if (trackMood) {
  trackMood.addEventListener("change", trackingLiveSummary);
}
if (trackVitality) {
  trackVitality.addEventListener("change", trackingLiveSummary);
}
if (trackWorkoutMinutes) {
  trackWorkoutMinutes.addEventListener("input", trackingLiveSummary);
}
[
  trackNote,
  trackWorkoutDetail,
  trackNutritionBreakfast,
  trackNutritionLunch,
  trackNutritionDinner,
  trackNutritionSnacks,
  trackHydrationExtra,
].forEach((el) => {
  if (el) el.addEventListener("input", trackingLiveSummary);
});

function resetDailyAiPanel() {
  if (!trackDailyAiBody) return;
  trackDailyAiBody.hidden = true;
  trackDailyAiBody.innerHTML = "";
  if (trackDailyAiBtn) trackDailyAiBtn.disabled = false;
}

async function fetchDailyTrackingInsight() {
  if (!trackDailyAiBtn || !trackDailyAiBody) return;
  trackDailyAiBtn.disabled = true;
  trackDailyAiBody.hidden = false;
  trackDailyAiBody.innerHTML =
    '<p class="ai-loading">Günlük veriler okunuyor, AI yorumu hazırlanıyor…</p>';
  try {
    const r = await fetch("/api/ai/insight/tracking/daily", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ day: getTrackingDay() }),
      signal: fetchTimeoutSignal(120000),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg =
        data.message ||
        (data.error === "no_ai"
          ? "API anahtarı yapılandırılmamış (.env içinde OPENAI_API_KEY veya GEMINI_API_KEY)."
          : null) ||
        data.error ||
        "Yorum alınamadı.";
      trackDailyAiBody.innerHTML = `<p class="ai-insight-error">${escapeHtml(String(msg))}</p>`;
      showToast("Günlük AI yorumu alınamadı.");
      return;
    }
    const insight = data.insight || "";
    trackDailyAiBody.innerHTML = insight ? formatBotHtml(insight) : "<p>Yorum boş döndü.</p>";
    showToast(insight ? "Günlük yorum hazır." : "Yorum boş.");
  } catch (err) {
    const aborted = err && err.name === "AbortError";
    trackDailyAiBody.innerHTML = `<p class="ai-insight-error">${escapeHtml(
      aborted ? "İşlem zaman aşımına uğradı; tekrar deneyin." : "Bağlantı veya sunucu hatası."
    )}</p>`;
    showToast(aborted ? "Zaman aşımı." : "Bağlantı hatası.");
  } finally {
    trackDailyAiBtn.disabled = false;
  }
}

if (trackDailyAiBtn) {
  trackDailyAiBtn.addEventListener("click", () => fetchDailyTrackingInsight());
}

async function fetchTrackingInsight() {
  if (!trackAiInsight) return;
  trackAiInsight.disabled = true;
  if (trackAiOutput) trackAiOutput.hidden = false;
  if (trackAiBody)
    trackAiBody.innerHTML =
      '<p class="ai-loading">Haftalık veriler okunuyor, AI analizi hazırlanıyor…</p>';
  try {
    const r = await fetch("/api/ai/insight/tracking", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: fetchTimeoutSignal(180000),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg =
        data.message ||
        (data.error === "no_ai"
          ? "API anahtarı yapılandırılmamış (.env içinde OPENAI_API_KEY veya GEMINI_API_KEY)."
          : null) ||
        data.error ||
        "Özet alınamadı.";
      if (trackAiBody)
        trackAiBody.innerHTML = `<p class="ai-insight-error">${escapeHtml(String(msg))}</p>`;
      showToast("AI özeti alınamadı.");
      return;
    }
    const insight = data.insight || "";
    if (trackAiBody)
      trackAiBody.innerHTML = insight ? formatBotHtml(insight) : "<p>Özet boş döndü.</p>";
    showToast(insight ? "Haftalık özet hazır." : "Özet boş.");
  } catch (err) {
    const aborted = err && err.name === "AbortError";
    if (trackAiBody)
      trackAiBody.innerHTML = `<p class="ai-insight-error">${escapeHtml(
        aborted ? "İşlem zaman aşımına uğradı; tekrar deneyin." : "Bağlantı veya sunucu hatası."
      )}</p>`;
    showToast(aborted ? "Zaman aşımı." : "Bağlantı hatası.");
  } finally {
    trackAiInsight.disabled = false;
  }
}

if (trackAiInsight) {
  trackAiInsight.addEventListener("click", () => fetchTrackingInsight());
}

if (trackSave) {
  trackSave.addEventListener("click", async () => {
    try {
      const body = {
        day: getTrackingDay(),
        note: trackNote ? trackNote.value : "",
        hydration_extra: trackHydrationExtra ? trackHydrationExtra.value : "",
        workout_detail: trackWorkoutDetail ? trackWorkoutDetail.value : "",
        nutrition_breakfast: trackNutritionBreakfast ? trackNutritionBreakfast.value : "",
        nutrition_lunch: trackNutritionLunch ? trackNutritionLunch.value : "",
        nutrition_dinner: trackNutritionDinner ? trackNutritionDinner.value : "",
        nutrition_snacks: trackNutritionSnacks ? trackNutritionSnacks.value : "",
      };
      if (trackWater) body.water_ml = parseLitersInputToMl(trackWater.value);
      if (trackSteps && trackSteps.value !== "") body.steps = Number(trackSteps.value);
      if (trackMood && trackMood.value !== "") body.mood = Number(trackMood.value);
      if (trackVitality && trackVitality.value !== "") body.vitality = Number(trackVitality.value);
      if (trackWorkoutMinutes && trackWorkoutMinutes.value !== "") {
        body.workout_minutes = Number(trackWorkoutMinutes.value) || 0;
      } else {
        body.workout_minutes = 0;
      }
      const r = await fetch("/api/tracking/daily", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        showToast("Kaydedilemedi.");
        return;
      }
      showToast("Kaydedildi.");
      loadTrackingPanel();
      refreshWeekSummary();
    } catch {
      showToast("Bağlantı hatası.");
    }
  });
}

function applyTheme(theme) {
  const t = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
    return;
  }
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    applyTheme("dark");
  } else {
    applyTheme("light");
  }
}

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(cur === "dark" ? "light" : "dark");
  });
}

async function refreshStatus() {
  if (!statusDot || !statusLabel) return;
  statusDot.className = "status-dot";
  statusLabel.textContent = "Kontrol…";
  try {
    const r = await fetch("/health", { credentials: "same-origin" });
    const data = await r.json();
    if (!r.ok) throw new Error("bad");
    if (data.ai_configured) {
      statusDot.classList.add("is-ok");
      statusLabel.textContent = "Asistan hazır";
    } else {
      statusDot.classList.add("is-warn");
      statusLabel.textContent = "API anahtarı yok";
    }
  } catch {
    statusDot.classList.add("is-off");
    statusLabel.textContent = "Sunucu yok";
  }
}

function bmiCategory(bmi) {
  if (bmi < 18.5) return "Zayıf (düşük)";
  if (bmi < 25) return "Normal aralık";
  if (bmi < 30) return "Fazla kilolu";
  return "Obezite riski (yüksek)";
}

if (bmiCalc) {
  bmiCalc.addEventListener("click", () => {
    const h = Number(bmiHeight && bmiHeight.value);
    const w = Number(bmiWeight && bmiWeight.value);
    if (!h || !w || h < 80 || h > 250 || w < 30 || w > 300) {
      bmiResult.hidden = false;
      bmiResult.innerHTML =
        "<p>Lütfen geçerli boy (80–250 cm) ve kilo (30–300 kg) girin.</p>";
      if (bmiAiBtn) bmiAiBtn.disabled = true;
      lastBmiPayload = null;
      return;
    }
    const m = h / 100;
    const bmi = w / (m * m);
    const rounded = Math.round(bmi * 10) / 10;
    const cat = bmiCategory(bmi);
    bmiResult.hidden = false;
    bmiResult.innerHTML = `<p><strong>BMI:</strong> ${rounded}</p><p><strong>Sınıf:</strong> ${escapeHtml(cat)}</p><p style="margin-top:12px;font-size:0.85rem;color:var(--text-muted)">Bu hesaplama bilgilendiricidir; kişisel sağlık için doktor veya diyetisyene danışın.</p>`;
    lastBmiPayload = { height: h, weight: w, bmi: rounded, category: cat };
    if (bmiAiBtn) bmiAiBtn.disabled = false;
    if (bmiAiOutput) {
      bmiAiOutput.hidden = true;
      if (bmiAiBody) bmiAiBody.innerHTML = "";
    }
  });
}

async function fetchBmiInsight() {
  if (!lastBmiPayload || !bmiAiBtn) return;
  bmiAiBtn.disabled = true;
  if (bmiAiOutput) bmiAiOutput.hidden = false;
  if (bmiAiBody)
    bmiAiBody.innerHTML = '<p class="ai-loading">AI kısa yorum hazırlıyor…</p>';
  try {
    const r = await fetch("/api/ai/insight/bmi", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        height: lastBmiPayload.height,
        weight: lastBmiPayload.weight,
        bmi: lastBmiPayload.bmi,
        category: lastBmiPayload.category,
      }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = data.message || data.error || "Yorum alınamadı.";
      if (bmiAiBody) bmiAiBody.innerHTML = `<p>${escapeHtml(String(msg))}</p>`;
      showToast("AI yorumu alınamadı.");
      return;
    }
    if (bmiAiBody) bmiAiBody.innerHTML = formatBotHtml(data.insight || "");
    showToast("AI yorumu hazır.");
  } catch {
    if (bmiAiBody) bmiAiBody.innerHTML = "";
    showToast("Bağlantı hatası.");
  } finally {
    if (bmiAiBtn) bmiAiBtn.disabled = false;
  }
}

if (bmiAiBtn) {
  bmiAiBtn.addEventListener("click", () => fetchBmiInsight());
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
  if (!message) return;

  appendMessage(message, "user");
  messageInput.value = "";
  resizeTextarea();
  updateCharCount();

  const botArticle = document.createElement("article");
  botArticle.classList.add("message", "bot", "is-streaming");
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = "Asistan";
  const body = document.createElement("div");
  body.className = "message-body";
  body.setAttribute("aria-live", "polite");
  body.setAttribute("aria-atomic", "true");
  body.textContent = "";
  botArticle.appendChild(meta);
  botArticle.appendChild(body);
  chatBox.appendChild(botArticle);
  chatBox.scrollTop = chatBox.scrollHeight;

  setLoading(true);

  try {
    const signal = fetchTimeoutSignal(CHAT_FETCH_TIMEOUT_MS);
    const fullText = await streamAssistantReply(message, body, signal);
    botArticle.classList.remove("is-streaming");
    const trimmed = (fullText || "").trim();
    body.innerHTML = formatBotHtml(trimmed || " ");
    scheduleArchiveRefresh();
  } catch (err) {
    botArticle.classList.remove("is-streaming");
    const name = err && err.name;
    const isAbort =
      name === "AbortError" ||
      name === "TimeoutError" ||
      (err instanceof DOMException && (name === "AbortError" || name === "TimeoutError"));
    let reply;
    if (isAbort) {
      reply =
        "Tarayıcı zaman aşımı (~10 dk): bağlantı takıldı veya sunucu yanıt vermedi. Sayfayı yenileyip tekrar deneyin; çok uzun bekliyorsanız .env içinde AI_REQUEST_TIMEOUT_SECONDS değerini kontrol edin.";
      showToast("Zaman aşımı — tekrar deneyin.");
    } else {
      reply = err && err.message ? String(err.message) : "Sunucuya bağlanırken bir hata oluştu.";
      showToast("Hata veya bağlantı sorunu.");
    }
    body.innerHTML = formatBotHtml(reply);
    scheduleArchiveRefresh();
  } finally {
    setLoading(false);
    messageInput.focus();
  }
});

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  const isLocal =
    location.hostname === "localhost" || location.hostname === "127.0.0.1" || location.protocol === "file:";
  if (location.protocol !== "https:" && !isLocal) return;
  navigator.serviceWorker
    .register("/sw.js")
    .then((reg) => {
      reg.update().catch(() => {});
    })
    .catch(() => {});
}

function setupVoiceInput() {
  if (!voiceBtn || !messageInput) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    voiceBtn.disabled = true;
    voiceBtn.title = "Bu tarayıcı sesli girişi desteklemiyor";
    return;
  }
  let voiceBusy = false;
  const voiceRec = new SR();
  voiceRec.lang = "tr-TR";
  voiceRec.interimResults = true;
  voiceRec.continuous = false;
  voiceRec.onresult = (e) => {
    let text = "";
    for (let i = 0; i < e.results.length; i++) {
      text += e.results[i][0].transcript;
    }
    messageInput.value = text.trim();
    resizeTextarea();
    updateCharCount();
  };
  voiceRec.onerror = (ev) => {
    voiceBusy = false;
    voiceBtn.classList.remove("is-recording");
    if (ev.error === "not-allowed") {
      showToast("Mikrofon izni gerekli.");
    } else if (ev.error !== "aborted" && ev.error !== "no-speech") {
      showToast("Ses tanıma hatası.");
    }
  };
  voiceRec.onend = () => {
    voiceBusy = false;
    voiceBtn.classList.remove("is-recording");
  };
  voiceBtn.addEventListener("click", () => {
    if (voiceBusy) {
      try {
        voiceRec.stop();
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      voiceBusy = true;
      voiceBtn.classList.add("is-recording");
      voiceRec.start();
    } catch {
      voiceBusy = false;
      voiceBtn.classList.remove("is-recording");
      showToast("Ses tanıma başlatılamadı.");
    }
  });
}

function setupReadAloud() {
  if (!readLastBtn) return;
  readLastBtn.addEventListener("click", () => {
    const nodes = chatBox.querySelectorAll(".message.bot:not(.message-welcome)");
    if (!nodes.length) {
      showToast("Okunacak mesaj yok.");
      return;
    }
    const last = nodes[nodes.length - 1];
    const body = last.querySelector(".message-body");
    const text = body ? body.innerText.trim() : "";
    if (!text) {
      showToast("Okunacak metin yok.");
      return;
    }
    if (!window.speechSynthesis) {
      showToast("Tarayici sesli okuma desteklemiyor.");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "tr-TR";
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  });
}

initTheme();
refreshStatus();
resizeTextarea();
updateCharCount();
refreshArchive();
refreshWeekSummary();
if (trackDayInput) {
  trackDayInput.max = localDayString();
  if (!trackDayInput.value) trackDayInput.value = localDayString();
  trackDayInput.addEventListener("change", () => loadTrackingPanel());
}
if (trackTodayBtn) {
  trackTodayBtn.addEventListener("click", () => {
    if (trackDayInput) {
      trackDayInput.value = localDayString();
      trackDayInput.max = localDayString();
    }
    loadTrackingPanel();
  });
}
setupVoiceInput();
setupReadAloud();
registerServiceWorker();
