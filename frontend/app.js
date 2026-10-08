"use strict";

const { Room, RoomEvent, Track } = LivekitClient;
const $ = (id) => document.getElementById(id);
// "" = same origin (page served by the backend); see config.js
const API = (window.APP_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");

/* ======================================================================
 * Voice call
 * ==================================================================== */
const call = {
  room: null,
  segments: new Map(), // segment id -> <li>
};

function setStatus(text) { $("call-status").textContent = text; }

function setAgentState(state) {
  const pill = $("agent-state");
  pill.textContent = state;
  pill.className = `pill ${state}`;
}

function addLine(kind, text, { id, interim = false } = {}) {
  const list = $("transcript");
  list.querySelector(".empty")?.remove();
  let li = id ? call.segments.get(id) : null;
  if (!li) {
    li = document.createElement("li");
    li.className = kind;
    if (kind !== "system") {
      const who = document.createElement("span");
      who.className = "who";
      who.textContent = kind === "user" ? "You" : "Agent";
      li.append(who, document.createElement("span"));
    } else {
      li.append(document.createElement("span"));
    }
    if (id) call.segments.set(id, li);
    list.append(li);
  }
  li.lastChild.textContent = text;
  li.classList.toggle("interim", interim);
  list.scrollTop = list.scrollHeight;
}

async function startCall() {
  $("call-btn").disabled = true;
  setStatus("Requesting a room…");
  try {
    const res = await fetch(`${API}/api/token`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const { serverUrl, roomName, participantToken } = await res.json();

    const room = new Room({ adaptiveStream: true, dynacast: true });
    call.room = room;
    call.segments.clear();
    $("transcript").replaceChildren();

    room
      .on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) document.body.append(track.attach());
      })
      .on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()))
      .on(RoomEvent.ParticipantConnected, (p) => {
        addLine("system", "Agent joined");
        setStatus("Connected — speak your number.");
        watchAgentState(p);
      })
      .on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => watchAgentState(p))
      .on(RoomEvent.ParticipantDisconnected, () => {
        addLine("system", "Agent left the call");
        setAgentState("offline");
        refreshDashboard();
        endCall();
      })
      .on(RoomEvent.Disconnected, () => resetCallUi());

    // Live transcripts for both sides arrive on the "lk.transcription" text stream.
    room.registerTextStreamHandler("lk.transcription", async (reader, participant) => {
      const attrs = reader.info.attributes || {};
      const segmentId = attrs["lk.segment_id"] || reader.info.id;
      const isUser = participant.identity === room.localParticipant.identity;
      const isFinal = attrs["lk.transcription_final"] === "true";
      let text = "";
      for await (const chunk of reader) {
        // user transcripts are re-sent whole; agent text arrives as deltas
        text = isUser ? chunk : text + chunk;
        addLine(isUser ? "user" : "agent", text, { id: segmentId, interim: isUser && !isFinal });
      }
      if (isUser) addLine("user", text, { id: segmentId, interim: !isFinal });
    });

    setStatus("Connecting…");
    await room.connect(serverUrl, participantToken);
    await room.localParticipant.setMicrophoneEnabled(true);
    await room.startAudio();
    addLine("system", `Joined room ${roomName}`);
    setStatus("Waiting for the agent to join…");
    room.remoteParticipants.forEach(watchAgentState);

    $("call-btn").textContent = "End call";
    $("call-btn").classList.remove("primary");
    $("call-btn").disabled = false;
    $("mute-btn").disabled = false;
  } catch (err) {
    await endCall();
    const hint = /401|invalid token|not ?allowed|region settings/i.test(err.message)
      ? " — LiveKit rejected the token: check LIVEKIT_API_KEY / LIVEKIT_API_SECRET match LIVEKIT_URL."
      : "";
    setStatus(`Could not start the call: ${err.message}${hint}`); // after endCall so it isn't overwritten
  }
}

function watchAgentState(participant) {
  const state = participant.attributes?.["lk.agent.state"];
  if (state) setAgentState(state);
}

async function endCall() {
  const room = call.room;
  call.room = null;
  if (room) await room.disconnect();
  resetCallUi();
}

function resetCallUi() {
  $("call-btn").textContent = "Start call";
  $("call-btn").classList.add("primary");
  $("call-btn").disabled = false;
  $("mute-btn").disabled = true;
  $("mute-btn").textContent = "Mute";
  setAgentState("offline");
  if (!call.room) setStatus("Call ended. Press “Start call” to try again.");
}

$("call-btn").addEventListener("click", () => (call.room ? endCall() : startCall()));
$("mute-btn").addEventListener("click", async () => {
  const lp = call.room?.localParticipant;
  if (!lp) return;
  const enabled = !lp.isMicrophoneEnabled;
  await lp.setMicrophoneEnabled(enabled);
  $("mute-btn").textContent = enabled ? "Mute" : "Unmute";
});

/* ======================================================================
 * Dashboard
 * ==================================================================== */
const LANG_LABEL = { en: "English", hi: "Hindi", mixed: "Mixed" };
const expanded = new Set();

function formatNumber(n) { return `${n.slice(0, 5)} ${n.slice(5)}`; }
function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function filterParams() {
  const form = new FormData($("filters"));
  const params = new URLSearchParams();
  const search = (form.get("search") || "").replace(/\D/g, "");
  if (search) params.set("search", search);
  if (form.get("language")) params.set("language", form.get("language"));
  // date inputs are local days: send the start / end of that day in UTC
  if (form.get("from")) params.set("from", new Date(`${form.get("from")}T00:00:00`).toISOString());
  if (form.get("to")) params.set("to", new Date(`${form.get("to")}T23:59:59.999`).toISOString());
  return params;
}

function renderRows(records) {
  const tbody = $("rows");
  tbody.replaceChildren();
  for (const r of records) {
    const open = expanded.has(r.id);
    const tr = document.createElement("tr");
    tr.className = "record";
    tr.tabIndex = 0;
    tr.setAttribute("aria-expanded", String(open));
    tr.innerHTML = `
      <td class="number"><span class="chevron">›</span> ${formatNumber(r.parsedNumber)}</td>
      <td><span class="lang ${r.language}">${LANG_LABEL[r.language] ?? r.language}</span></td>
      <td>${formatDate(r.collectedAt)}</td>
      <td class="actions"><button class="btn small danger" type="button">Delete</button></td>`;
    const toggle = () => {
      open ? expanded.delete(r.id) : expanded.add(r.id);
      renderRows(records);
    };
    tr.addEventListener("click", (e) => { if (!e.target.closest("button")) toggle(); });
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
    tr.querySelector("button").addEventListener("click", () => deleteRecord(r));
    tbody.append(tr);

    if (open) {
      const detail = document.createElement("tr");
      detail.className = "detail";
      const td = document.createElement("td");
      td.colSpan = 4;
      const label = document.createElement("span");
      label.className = "label";
      label.textContent = `Raw transcript · record #${r.id}`;
      td.append(label, document.createTextNode(r.rawTranscript)); // textContent: no HTML injection
      detail.append(td);
      tbody.append(detail);
    }
  }
  $("empty").hidden = records.length > 0;
}

async function refreshDashboard() {
  try {
    const [list, stats] = await Promise.all([
      fetch(`${API}/api/phone?${filterParams()}`).then((r) => r.json()),
      fetch(`${API}/api/phone/stats`).then((r) => r.json()),
    ]);
    renderRows(list);
    $("stat-total").textContent = stats.total;
    $("stat-en").textContent = stats.byLanguage.en;
    $("stat-hi").textContent = stats.byLanguage.hi;
    $("stat-mixed").textContent = stats.byLanguage.mixed;
    $("error").hidden = true;
    $("last-refresh").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    $("error").textContent = `Could not load data: ${err.message}`;
    $("error").hidden = false;
  }
}

async function deleteRecord(record) {
  if (!confirm(`Delete ${formatNumber(record.parsedNumber)}?`)) return;
  const res = await fetch(`${API}/api/phone/${record.id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) alert(`Delete failed (${res.status})`);
  expanded.delete(record.id);
  refreshDashboard();
}

let debounce;
$("filters").addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(refreshDashboard, 250);
});
$("filters").addEventListener("reset", () => setTimeout(refreshDashboard, 0));
$("filters").addEventListener("submit", (e) => e.preventDefault());

refreshDashboard();
setInterval(refreshDashboard, 5000); // live data from the backend
