"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const machines = new Map(); // name -> card element
let events = null;
let lastStatusAt = 0;
let alarm = null;
let seenAlertIds = new Set();

// ---- API ------------------------------------------------------------------------------------

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
  };
  const r = await fetch(path, opts);
  if (r.status === 401) { showLogin(true); throw new Error("login required"); }
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
  events = new EventSource("/api/events");
  events.addEventListener("hello", (e) => {
    const d = JSON.parse(e.data);
    $("#alerts").innerHTML = "";
    seenAlertIds = new Set();
    d.alerts.forEach(showAlert);
  });
  events.addEventListener("status", (e) => { lastStatusAt = Date.now(); render(JSON.parse(e.data)); });
  events.addEventListener("alert", (e) => { const a = JSON.parse(e.data); showAlert(a); react(a); });
  events.onerror = () => { /* EventSource reconnects by itself; the watchdog shows "lost" */ };
}

setInterval(() => {
  const lost = Date.now() - lastStatusAt > 3000;
  const c = $("#conn");
  c.textContent = lost ? "Connection lost" : "live";
  c.classList.toggle("lost", lost);
  const loggedIn = $("#login").classList.contains("hidden");
  if (lost && loggedIn && !events) connect();
}, 1000);

// ---- rendering --------------------------------------------------------------------------------

const STATUS_TEXT = {
  not_ready: "NOT READY", ready: "READY", recording: "RECORDING",
  reel_finished: "REEL FINISHED — switch off", stopped: "STOPPED", shut_down: "SHUT DOWN",
};

function mmss(seconds) {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function card(name) {
  if (machines.has(name)) return machines.get(name);
  const el = $("#machine-card").content.firstElementChild.cloneNode(true);
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
  setInterval(() => {
    if ($("#login").classList.contains("hidden")) {
      $(".live", el).src = `${path}/live.jpg?t=${Date.now()}`;
    }
  }, 500);
  machines.set(name, el);
  $("#machines").appendChild(el);
  return el;
}

async function act(path, el) {
  try { await api(path, {}); } catch (err) { showAlert({level: "warning", title: "Not done", message: err.message, machine: $(".name", el).textContent, t: Date.now() / 1000, id: `local-${Date.now()}`}); }
}

let lastFrameShown = new Map();

function render(snap) {
  for (const m of snap.machines) {
    const el = card(m.name);
    const state = m.runner_alive ? m.state : "shut_down";
    el.dataset.state = state;
    let text = STATUS_TEXT[state] || state;
    if (state === "stopped" && m.last_fault && m.last_fault.kind !== "operator") text = "STOPPED — PROBLEM";
    $(".status", el).textContent = text;
    const showFault = m.last_fault && (state === "stopped" || state === "not_ready");
    $(".fault", el).classList.toggle("hidden", !showFault);
    if (showFault) {
      $(".fault-message", el).textContent = m.last_fault.message;
      $(".fault-action", el).textContent = m.last_fault.action;
    }
    const set = (cls, v) => { $(`.${cls}`, el).textContent = v; };
    set("reel", m.reel || "—"); set("segment", m.segment); set("saved", m.saved); set("failed", m.failed);
    set("pending", m.pending); set("clicks", m.clicks); set("bounces", m.bounces); set("fps", m.fps.toFixed(1));
    set("feet", m.feet.toFixed(1)); set("length", mmss(m.length_s));
    set("free", m.free_gb === null ? "drive missing" : `${m.free_gb} GB`);
    set("sync", `${m.sync_error_ms} ms`); set("delay", `${m.delay_ms} ms`);
    $(".warnings", el).innerHTML = m.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    const key = `${m.reel}/${m.saved + m.pending}`;
    if (m.saved + m.pending > 0 && lastFrameShown.get(m.name) !== key) {
      lastFrameShown.set(m.name, key);
      $(".last", el).src = `/api/machines/${encodeURIComponent(m.name)}/last.jpg?t=${Date.now()}`;
      $(".last-n", el).textContent = `#${m.saved + m.pending}`;
    }
    $(".stop", el).disabled = !(state === "recording" || state === "ready" || state === "reel_finished");
    $(".resume", el).disabled = state !== "stopped";
    $(".new-reel", el).disabled = !(["ready", "not_ready", "reel_finished", "stopped"].includes(state));
    $(".calibrate", el).disabled = state === "recording" || state === "shut_down";
    $(".calibrate", el).title = state === "recording" ? "Stop first: the delay cannot change while recording" : "";
  }
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
  if (alarm) clearInterval(alarm);
  alarm = null;
  document.body.classList.remove("alarm");
  $("#silence").classList.add("hidden");
}

function chime() { tone(1047, 0, 0.15); tone(1319, 0.18, 0.3); }

$("#silence").addEventListener("click", stopAlarm);

function notify(a) {
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
      fig.innerHTML = `<img src="${p.url}?t=${Date.now()}"><figcaption>${p.offset_ms >= 0 ? "+" : ""}${p.offset_ms} ms</figcaption>`;
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
