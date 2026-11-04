"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const machines = new Map(); // name -> card element
let events = null;
let lastStatusAt = 0;
let alarm = null;
let seenAlertIds = new Set();
let connectedOnce = false; // a status has arrived since the last login
let lastConnectAt = 0;
const lastState = new Map(); // machine name -> {reel, saved, url, inflight} for the last-saved picture
const silencedFaults = new Set(); // "machine|message" keys the operator has silenced
let activeFaults = new Set(); // keys of faults present in the latest status

// ---- API ------------------------------------------------------------------------------------

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  };
  const r = await fetch(path, opts);
  if (r.status === 401) {
    const d = await r.json().catch(() => ({}));
    if (path === "/api/login") throw new Error(d.error || "wrong password");
    showLogin(true);
    throw new Error("login required");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

// ---- login ------------------------------------------------------------------------------------

function showLogin(on) {
  $("#login").classList.toggle("hidden", !on);
  $("#machines").classList.toggle("hidden", on);
  $("#logout").classList.toggle("hidden", on);
  if (on && events) { events.close(); events = null; }
  if (on) connectedOnce = false;
  if (on) $("#password").focus();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", {password: $("#password").value});
    $("#password").value = "";
    showLogin(false);
    connect();
  } catch (err) { $("#login-error").textContent = err.message; }
});

$("#logout").addEventListener("click", async () => { await api("/api/logout", {}); showLogin(true); });

// ---- events stream ----------------------------------------------------------------------------

function connect() {
  if (events) events.close();
  lastConnectAt = Date.now();
  events = new EventSource("/api/events");
  events.addEventListener("hello", (e) => {
    const d = JSON.parse(e.data);
    $("#alerts").innerHTML = "";
    seenAlertIds = new Set();
    d.alerts.forEach(showAlert);
  });
  events.addEventListener("status", (e) => { lastStatusAt = Date.now(); connectedOnce = true; render(JSON.parse(e.data)); });
  events.addEventListener("alert", (e) => { const a = JSON.parse(e.data); showAlert(a); react(a); });
  events.onerror = async () => {
    // While CONNECTING the browser retries by itself; CLOSED means it gave up (e.g. a 401 or 5xx).
    if (events && events.readyState === EventSource.CLOSED) {
      events.close();
      events = null;
      try { await api("/api/status"); connect(); } // a 401 here opens the login box
      catch (err) { console.error("event stream reconnect check failed:", err.message); }
    }
  };
}

setInterval(() => {
  const now = Date.now();
  const stale = now - lastStatusAt > 3000;
  const lost = connectedOnce && stale;
  const c = $("#conn");
  c.textContent = lost ? "Connection lost" : (connectedOnce ? "live" : "connecting…");
  c.classList.toggle("lost", lost);
  const loggedIn = $("#login").classList.contains("hidden");
  if (stale && loggedIn && now - lastConnectAt > 3000) connect();
  $("#audio-off").classList.toggle("hidden", !!audio && audio.state === "running");
}, 1000);

// ---- rendering --------------------------------------------------------------------------------

const STATUS_TEXT = {
  dead: "RUNNER DIED", not_ready: "NOT READY", ready: "READY", recording: "RECORDING",
  reel_finished: "REEL FINISHED — switch off", stopped: "STOPPED", shut_down: "SHUT DOWN",
};

function mmss(seconds) {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function card(name, filmType) {
  if (machines.has(name)) return machines.get(name);
  const el = $("#machine-card").content.firstElementChild.cloneNode(true);
  for (const o of $("select[name=film_type]", el).options) o.defaultSelected = o.value === filmType;
  $(".name", el).textContent = name;
  const path = `/api/machines/${encodeURIComponent(name)}`;
  $(".stop", el).addEventListener("click", () => act(`${path}/stop`, el));
  $(".resume", el).addEventListener("click", () => act(`${path}/resume`, el));
  $(".new-reel", el).addEventListener("click", () => $(".new-reel-form", el).classList.toggle("hidden"));
  $(".cancel", el).addEventListener("click", () => $(".new-reel-form", el).classList.add("hidden"));
  $(".new-reel-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const body = {
      name: f.name.value.trim() || null, film_type: f.film_type.value,
      customer: f.customer.value, job_number: f.job_number.value, notes: f.notes.value,
    };
    $(".error", f).textContent = "";
    try { await api(`${path}/new-reel`, body); f.reset(); f.classList.add("hidden"); }
    catch (err) { $(".error", f).textContent = err.message; }
  });
  $(".calibrate", el).addEventListener("click", () => calibrate(name, el));
  const live = $(".live", el);
  live.addEventListener("error", () => live.classList.add("hidden"));
  live.addEventListener("load", () => live.classList.remove("hidden"));
  setInterval(() => {
    if ($("#login").classList.contains("hidden") && !["shut_down", "dead"].includes(el.dataset.state)) {
      live.src = `${path}/live.jpg?t=${Date.now()}`;
    }
  }, 500);
  machines.set(name, el);
  $("#machines").appendChild(el);
  return el;
}

async function act(path, el) {
  try { await api(path, {}); } catch (err) { showAlert({level: "warning", title: "Not done", message: err.message, machine: $(".name", el).textContent, t: Date.now() / 1000, id: `local-${Date.now()}`}); }
}

// The last-saved picture and its frame number come from the server (X-Frame-Number), fetched only
// when the saved count changes; never requested while nothing is saved.
function updateLast(m, el) {
  let st = lastState.get(m.name);
  if (!st) { st = {reel: m.reel, saved: 0, url: null, inflight: false}; lastState.set(m.name, st); }
  if (st.reel !== m.reel || m.saved === 0) {
    st.reel = m.reel; st.saved = 0;
    if (st.url) { URL.revokeObjectURL(st.url); st.url = null; }
    $(".last", el).removeAttribute("src");
    $(".last-n", el).textContent = "";
  }
  if (m.saved > 0 && m.saved !== st.saved && !st.inflight) fetchLast(m.name, m.saved, el, st);
}

async function fetchLast(name, savedNow, el, st) {
  st.inflight = true;
  const reel = st.reel;
  try {
    const r = await fetch(`/api/machines/${encodeURIComponent(name)}/last.jpg`);
    if (r.status === 401) { showLogin(true); return; }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const n = r.headers.get("X-Frame-Number");
    const blob = await r.blob();
    if (st.reel !== reel) return; // a new reel started meanwhile
    if (st.url) URL.revokeObjectURL(st.url);
    st.url = URL.createObjectURL(blob);
    $(".last", el).src = st.url;
    $(".last-n", el).textContent = `#${n}`;
    st.saved = savedNow;
  } catch (err) {
    $(".last-n", el).textContent = `(could not load: ${err.message})`;
  } finally {
    st.inflight = false;
  }
}

function render(snap) {
  const faults = new Set();
  for (const m of snap.machines) {
    const el = card(m.name, m.film_type);
    const dead = !m.runner_alive && Boolean(m.runner_error);
    const state = m.runner_alive ? m.state : (dead ? "dead" : "shut_down");
    el.dataset.state = state;
    let text = STATUS_TEXT[state] || state;
    const problem = state === "stopped" && m.last_fault && m.last_fault.kind !== "operator";
    if (problem) text = "STOPPED — PROBLEM";
    $(".status", el).textContent = text;
    const showFault = dead || (m.last_fault && (state === "stopped" || state === "not_ready"));
    $(".fault", el).classList.toggle("hidden", !showFault);
    if (dead) {
      $(".fault-message", el).textContent = m.runner_error.split("\n")[0];
      $(".fault-action", el).textContent = "Restart the capture program";
      faults.add(`${m.name}|${m.runner_error}`);
    } else if (showFault) {
      $(".fault-message", el).textContent = m.last_fault.message;
      $(".fault-action", el).textContent = m.last_fault.action;
    }
    if (problem) faults.add(`${m.name}|${m.last_fault.message}`);
    const set = (cls, v) => { $(`.${cls}`, el).textContent = v; };
    set("reel", m.reel || "—"); set("segment", m.segment); set("saved", m.saved); set("failed", m.failed);
    set("pending", m.pending); set("clicks", m.clicks); set("bounces", m.bounces); set("fps", m.fps.toFixed(1));
    set("feet", m.feet.toFixed(1)); set("length", mmss(m.length_s));
    set("free", m.free_gb === null ? "drive missing" : `${m.free_gb} GB`);
    set("sync", `${m.sync_error_ms} ms`); set("delay", `${m.delay_ms} ms`);
    $(".warnings", el).innerHTML = m.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    updateLast(m, el);
    $(".stop", el).disabled = !(state === "recording" || state === "ready" || state === "reel_finished");
    $(".resume", el).disabled = state !== "stopped";
    $(".new-reel", el).disabled = !(["ready", "not_ready", "reel_finished", "stopped"].includes(state));
    $(".calibrate", el).disabled = state === "recording" || state === "shut_down" || state === "dead";
    $(".cal-reason", el).textContent = state === "recording" ? "Stop first: the delay cannot change while recording" : "";
  }
  activeFaults = faults;
  for (const k of faults) if (!silencedFaults.has(k)) startAlarm();
  const pc = snap.pc;
  $("#pc").textContent = `PC: CPU ${pc.cpu_percent}% · memory ${pc.memory_percent}% · temperature ${pc.temperature_c === null ? "n/a" : pc.temperature_c.toFixed(0) + " °C"} · updated ${new Date(snap.t * 1000).toLocaleTimeString()}`;
}

function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c])); }

// ---- alerts and alarm -------------------------------------------------------------------------

function showAlert(a) {
  if (seenAlertIds.has(a.id)) return;
  seenAlertIds.add(a.id);
  const li = document.createElement("li");
  li.className = a.level;
  li.innerHTML = `<b>${escapeHtml(a.title)}</b> <span class="muted">${escapeHtml(a.machine)} · ${new Date(a.t * 1000).toLocaleTimeString()}</span><br>${escapeHtml(a.message)}`;
  $("#alerts").prepend(li);
}

function react(a) {
  if (a.level === "problem") { startAlarm(); notify(a); }
  else if (a.level === "info" && a.title.startsWith("Reel finished")) { chime(); notify(a); }
}

let audio = null;
function ctx() { if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)(); return audio; }

function tone(freq, start, dur) {
  const c = ctx();
  const o = c.createOscillator(); const g = c.createGain();
  o.frequency.value = freq; o.type = "square";
  g.gain.setValueAtTime(0.0001, c.currentTime + start);
  g.gain.exponentialRampToValueAtTime(0.3, c.currentTime + start + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + start + dur);
  o.connect(g).connect(c.destination); o.start(c.currentTime + start); o.stop(c.currentTime + start + dur);
}

function startAlarm() {
  document.body.classList.add("alarm");
  $("#silence").classList.remove("hidden");
  if (alarm) return;
  const beep = () => { tone(880, 0, 0.25); tone(660, 0.3, 0.25); };
  beep();
  alarm = setInterval(beep, 1000);
}

function stopAlarm() {
  for (const k of activeFaults) silencedFaults.add(k);
  if (alarm) clearInterval(alarm);
  alarm = null;
  document.body.classList.remove("alarm");
  $("#silence").classList.add("hidden");
}

function chime() { tone(1047, 0, 0.15); tone(1319, 0.18, 0.3); }

$("#silence").addEventListener("click", stopAlarm);

function unlockAudio() { ctx().resume(); }
for (const ev of ["pointerdown", "keydown", "touchstart"]) {
  window.addEventListener(ev, unlockAudio, {once: true});
}

function notify(a) {
  unlockAudio();
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  new Notification(a.title, {body: `${a.machine}: ${a.message}`});
}

$("#notify").addEventListener("click", async () => {
  if (!("Notification" in window)) { $("#notify").textContent = "No notifications here"; return; }
  const p = await Notification.requestPermission();
  $("#notify").textContent = p === "granted" ? "Notifications on" : "Notifications blocked";
  ctx().resume(); // a user gesture unlocks audio for the alarm
});

// ---- calibration ------------------------------------------------------------------------------

async function calibrate(name, el) {
  const box = $(".calibration", el);
  const strip = $(".strip", box);
  $(".error", box).textContent = "";
  const path = `/api/machines/${encodeURIComponent(name)}`;
  try {
    const cal = await api(`${path}/calibration`);
    if (!cal.pictures.length) { $(".error", box).textContent = "No click yet: run a few frames first, then Stop and Calibrate"; box.classList.remove("hidden"); return; }
    strip.innerHTML = "";
    for (const p of cal.pictures) {
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.src = p.url;
      const cap = document.createElement("figcaption");
      cap.textContent = `${p.offset_ms >= 0 ? "+" : ""}${p.offset_ms} ms`;
      fig.append(img, cap);
      fig.addEventListener("click", async () => {
        const next = Math.round((cal.delay_ms + p.offset_ms) * 10) / 10;
        if (!confirm(`Set the delay for ${name} to ${next} ms?`)) return;
        try { await api(`${path}/delay`, {delay_ms: next}); box.classList.add("hidden"); }
        catch (err) { $(".error", box).textContent = err.message; }
      });
      strip.appendChild(fig);
    }
    box.classList.remove("hidden");
  } catch (err) { $(".error", box).textContent = err.message; box.classList.remove("hidden"); }
}

// ---- start ------------------------------------------------------------------------------------

api("/api/status").then((snap) => { showLogin(false); render(snap); connect(); }).catch(() => {});
