const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = t => { t = Math.floor(t); const m = Math.floor(t / 60), s = t % 60; return m + ":" + String(s).padStart(2, "0"); };
let vid = null;

chrome.storage.local.get(["backend", "key"], v => { $("backend").value = v.backend || "http://localhost:8000"; $("key").value = v.key || ""; });
$("gear").onclick = () => $("settings").classList.toggle("on");
$("q").addEventListener("keydown", e => { if (e.key === "Enter") $("ask").click(); });
const save = () => chrome.storage.local.set({ backend: $("backend").value.replace(/\/$/, ""), key: $("key").value });
$("backend").onchange = save; $("key").onchange = save;

async function api(path, body) {
  save();
  const r = await fetch($("backend").value.replace(/\/$/, "") + path, { method: "POST",
    headers: { "Content-Type": "application/json", "x-app-key": $("key").value }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({ detail: "bad response" }));
  if (!r.ok) throw new Error(d.detail || r.status);
  return d;
}
async function tab() { const [t] = await chrome.tabs.query({ active: true, currentWindow: true }); return t; }

// Runs inside the YouTube page (user's own IP): read caption track -> json3 events
function pageFetchCaptions() {
  return (async () => {
    const pr = (document.querySelector("#movie_player")?.getPlayerResponse?.()) || window.ytInitialPlayerResponse;
    const tracks = pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    if (!tracks.length) return { error: "no caption tracks on this video" };
    const t = tracks.find(x => x.languageCode?.startsWith("bn")) || tracks.find(x => x.languageCode?.startsWith("en")) || tracks[0];
    const res = await fetch(t.baseUrl + "&fmt=json3");
    const txt = await res.text();
    if (!txt) return { error: "YouTube returned empty captions (blocked/PO token)" };
    const j = JSON.parse(txt);
    const segs = (j.events || []).filter(e => e.segs).map(e => ({ start: e.tStartMs / 1000,
      end: (e.tStartMs + (e.dDurationMs || 2000)) / 1000, text: e.segs.map(s => s.utf8).join("").replace(/\n/g, " ").trim() })).filter(s => s.text);
    return { segs, title: pr?.videoDetails?.title || "", id: pr?.videoDetails?.videoId };
  })();
}
// Fallback: open YouTube's own "Show transcript" panel and read the rows it renders (selectors may change)
function pageDomTranscript() {
  return (async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const toSec = t => t.trim().split(":").reduce((a, x) => a * 60 + Number(x), 0);
    let rows = document.querySelectorAll("ytd-transcript-segment-renderer");
    if (!rows.length) {
      const btn = [...document.querySelectorAll("button")].find(b => /show transcript|transcript দেখান/i.test((b.getAttribute("aria-label") || "") + b.textContent));
      if (btn) { btn.click(); await sleep(2000); }
      rows = document.querySelectorAll("ytd-transcript-segment-renderer");
    }
    if (!rows.length) return { error: "transcript panel not found" };
    const segs = [...rows].map(r => ({ start: toSec(r.querySelector(".segment-timestamp")?.textContent || "0:00"),
      text: (r.querySelector(".segment-text")?.textContent || "").trim() })).filter(s => s.text);
    segs.forEach((s, i) => { s.end = i + 1 < segs.length ? segs[i + 1].start : s.start + 5; });
    const pr = document.querySelector("#movie_player")?.getPlayerResponse?.() || window.ytInitialPlayerResponse;
    return { segs, title: pr?.videoDetails?.title || document.title, id: pr?.videoDetails?.videoId };
  })();
}
function pageTime() { return document.querySelector("video")?.currentTime || 0; }

$("idx").onclick = async () => {
  try {
    const t = await tab();
    $("st").textContent = "Caption আনছি...";
    let [{ result }] = await chrome.scripting.executeScript({ target: { tabId: t.id }, world: "MAIN", func: pageFetchCaptions });
    if (result.error) {
      $("st").textContent = "json3 fail (" + result.error + ") — transcript panel চেষ্টা করছি...";
      [{ result }] = await chrome.scripting.executeScript({ target: { tabId: t.id }, world: "MAIN", func: pageDomTranscript });
    }
    if (result.error) { $("st").textContent = "❌ " + result.error + " — website-এর Upload tab ব্যবহার করো"; return; }
    vid = result.id;
    let d = await api("/api/index_transcript", { video_id: vid, title: result.title, segments: result.segs });
    while (d.status === "running") {
      $("st").textContent = d.msg; await new Promise(r => setTimeout(r, 2000));
      d = await (await fetch($("backend").value + "/api/job/" + vid, { headers: { "x-app-key": $("key").value } })).json();
    }
    $("st").textContent = d.status === "done" ? "✅ Ready: " + d.meta.title : "❌ " + d.msg;
    if (d.status === "done") $("vbadge").textContent = "✓ indexed · " + d.meta.n_chunks + " chunks";
  } catch (e) { $("st").textContent = "❌ " + e.message; }
};

$("ask").onclick = async () => {
  try {
    const t = await tab();
    const m = /[?&]v=([\w-]{11})/.exec(t.url || ""); vid = vid || (m && m[1]);
    if (!vid) { $("out").innerHTML = "YouTube video খোলো"; return; }
    let ct = null;
    if ($("sp").checked) { const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: t.id }, world: "MAIN", func: pageTime }); ct = result; }
    const q = $("q").value.trim(); if (!q) return;
    $("out").innerHTML = '<div class="bub">' + esc(q) + '</div><div class="card"><span class="spin"></span> <span class="muted">retrieve → grade → answer → verify…</span></div>';
    const d = await api("/api/ask", { video_id: vid, question: q, current_time: ct, clip: false });
    let h = '<div class="bub">' + esc(q) + "</div>";
    if (!d.found) { $("out").innerHTML = h + '<div class="card"><span class="badge bad">✕ Not in video</span><div>' + esc(d.message) + "</div></div>"; return; }
    const tr = d.trace || {};
    h += '<div class="card"><span class="badge ' + (tr.verify === "ok" ? "ok" : "") + '">✓ ' + (tr.claims_supported || 0) + "/" + (tr.claims_total || 0) + " verified</span>";
    if (d.answer) {
      h += "<b>" + esc(d.answer.title) + '</b><p style="color:var(--text2);margin:4px 0">' + esc(d.answer.summary) + "</p>";
      d.answer.sections.forEach(s => { h += "<h4>" + esc(s.heading) + "</h4><ul>" + s.points.map(p => "<li>" + esc(p.text) + " " +
        (p.cites || []).map(n => { const r = d.refs.find(x => x.n === n); return r ? '<span class="chip" data-t="' + r.start + '">▶ ' + fmt(r.start) + "</span>" : ""; }).join("") + "</li>").join("") + "</ul>"; });
    } else h += esc(d.note);
    h += '<div style="margin-top:8px">' + (d.segments || []).map(sg => '<span class="chip" data-t="' + sg.start + '">▶ ' + fmt(sg.start) + "–" + fmt(sg.end) + "</span>").join(" ") + "</div>";
    $("out").innerHTML = h + "</div>";
    document.querySelectorAll(".chip").forEach(c => c.onclick = () => chrome.scripting.executeScript({ target: { tabId: t.id }, world: "MAIN",
      func: s => { const v = document.querySelector("video"); if (v) { v.currentTime = s; v.play(); } }, args: [Number(c.dataset.t)] }));
  } catch (e) { $("out").innerHTML = '<div class="card bad">' + esc(e.message) + "</div>"; }
};
