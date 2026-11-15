// Learning Mate AI side panel.
// Reads the YouTube video in the active tab, sends its captions to our server once (so the server
// can build the RAG index), then asks questions and shows answers with clickable timestamps.

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let docMode = false;                    // true while a PDF / slide deck (not the YouTube tab) is open
// a document has pages, not minutes: the server stores page N as minute N, so show "p.N"
const fmt = t => { t = Math.floor(t || 0); if (docMode) return "p." + (Math.floor(t / 60) + 1); const m = Math.floor(t / 60), s = t % 60; return m + ":" + String(s).padStart(2, "0"); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const DEFAULT_SERVER = "https://learning-mate-ai.onrender.com";

// ---------------------------------------------------------------- text in both languages
const TXT = {
  en: { server: "Server address", email: "Email", password: "Password", login: "Log in", logout: "Log out", prepare: "Prepare video",
    chat: "Chat", summary: "Summary", quiz: "Quiz", ask: "Ask", spoiler: "Spoiler-free: only the part I have watched",
    qPh: "Ask about this video…", openYt: "Open a YouTube video to start", ready: "ready", notReady: "not prepared yet",
    preparing: "preparing…", captions: "Reading captions…", noCaptions: "No captions found, asking the server to fetch them…",
    failed: "failed", notInVideo: "Not in this video", verified: "verified", checking: "checking against the video…",
    understood: "Understood as", steps: ["Rewrite", "Search", "Check", "Answer", "Verify"], makeSum: "Make summary",
    makeQuiz: "Make a quiz (5 questions)", working: "Working…", needLogin: "Log in first (⚙ settings)", loggedIn: "Logged in",
    noLogin: "This server does not need a login", hint: "Ask anything about the video. Click a time to jump there.",
    general: "From general knowledge (not from the video)", lost: "Connection lost, try again", lang: "বাংলা",
    notes: "Notebook", nText: "+ Text", nTs: "+ Timestamp", nShot: "📷 Screenshot", nEmpty: "Write notes, save the current time or a screenshot of the video. Answers can be added with “Add to notes”.",
    nPh: "Write here…", saving: "saving…", savedCloud: "✓ saved to your account", savedLocal: "✓ saved in this browser (log in to sync with the website)",
    toNotes: "+ Add to notes", added: "Added to notes", shotFail: "Could not capture the video frame",
    docBtn: "Upload a PDF or slides (.pptx) and study it here", uploading: "Uploading…", reading: "Reading pages…", backToVideo: "Back to the YouTube video",
    docLogin: "Log in first (⚙) to upload files", review: "Review flashcards", noCards: "No flashcards for this video yet — make them in the Notebook (AI → Flashcards).",
    micPerm: "Allow the microphone in the tab that just opened, then try again." },
  bn: { server: "সার্ভারের ঠিকানা", email: "ইমেইল", password: "পাসওয়ার্ড", login: "লগইন", logout: "লগআউট", prepare: "ভিডিও প্রস্তুত করো",
    chat: "চ্যাট", summary: "সারাংশ", quiz: "কুইজ", ask: "পাঠাও", spoiler: "স্পয়লার ছাড়া: শুধু যতটুকু দেখেছি",
    qPh: "এই ভিডিও নিয়ে প্রশ্ন করো…", openYt: "শুরু করতে একটা YouTube ভিডিও খোলো", ready: "প্রস্তুত", notReady: "এখনো প্রস্তুত না",
    preparing: "প্রস্তুত হচ্ছে…", captions: "Caption পড়ছি…", noCaptions: "Caption পাইনি, সার্ভারকে আনতে বলছি…",
    failed: "হয়নি", notInVideo: "এই ভিডিওতে নেই", verified: "যাচাই হয়েছে", checking: "ভিডিওর সাথে মিলিয়ে দেখছি…",
    understood: "যেভাবে বুঝেছি", steps: ["প্রশ্ন বোঝা", "খোঁজা", "যাচাই", "উত্তর", "মিলানো"], makeSum: "সারাংশ বানাও",
    makeQuiz: "কুইজ বানাও (৫টা প্রশ্ন)", working: "কাজ চলছে…", needLogin: "আগে লগইন করো (⚙ সেটিংস)", loggedIn: "লগইন আছে",
    noLogin: "এই সার্ভারে লগইন লাগে না", hint: "ভিডিও নিয়ে যেকোনো প্রশ্ন করো। সময়ে ক্লিক করলে ভিডিও ওখানে যাবে।",
    general: "সাধারণ জ্ঞান থেকে (ভিডিও থেকে না)", lost: "সংযোগ কেটে গেছে, আবার চেষ্টা করো", lang: "English",
    notes: "নোটবুক", nText: "+ লেখা", nTs: "+ সময়", nShot: "📷 স্ক্রিনশট", nEmpty: "নোট লেখো, ভিডিওর এখনকার সময় বা স্ক্রিনশট রাখো। উত্তরের নিচে “নোটে রাখো” চাপলে উত্তরও নোটে যাবে।",
    nPh: "এখানে লেখো…", saving: "সেভ হচ্ছে…", savedCloud: "✓ তোমার অ্যাকাউন্টে সেভ হয়েছে", savedLocal: "✓ এই ব্রাউজারে সেভ হয়েছে (লগইন করলে ওয়েবসাইটের সাথে মিলবে)",
    toNotes: "+ নোটে রাখো", added: "নোটে রাখা হয়েছে", shotFail: "ভিডিওর ছবি নেওয়া গেল না",
    docBtn: "PDF বা স্লাইড (.pptx) আপলোড করে এখানে পড়ো", uploading: "আপলোড হচ্ছে…", reading: "পৃষ্ঠা পড়ছি…", backToVideo: "YouTube ভিডিওতে ফিরে যাও",
    docLogin: "ফাইল আপলোড করতে আগে লগইন করো (⚙)", review: "ফ্ল্যাশকার্ড রিভিউ", noCards: "এই ভিডিওর ফ্ল্যাশকার্ড নেই — নোটবুকে AI → ফ্ল্যাশকার্ড দিয়ে বানাও।",
    micPerm: "যে ট্যাব খুলেছে সেখানে মাইক্রোফোন Allow করো, তারপর আবার চেষ্টা করো।" },
};
const STAGES = ["rewrite", "retrieve", "grade", "generate", "verify"];
let cfg = { backend: DEFAULT_SERVER, token: "", user: "", lang: "en", theme: "dark" };
let vid = null, tabId = null, state = "none";
// globals used by the website's notebook (lib/notebook.js)
let cur = null, nbLoadedFor = null, lastTime = 0;
const me = { user: null };
const now = () => lastTime;
const seek = s => { if (docMode) { toast(fmt(s)); return; } if (tabId != null) inPage(pageSeek, [s]); lastTime = s; };
function toast(msg) { const el = $("toast"); el.textContent = msg; el.classList.remove("hide"); clearTimeout(toast.tm); toast.tm = setTimeout(() => el.classList.add("hide"), 2200); }        // state: none | unknown | running | done | error
const chats = {};                                     // video id -> [{q, standalone}]
// keys this panel does not define come from the website's text file (lib/i18n.js), which the notebook uses
const t = (k, vars) => { let s = TXT[cfg.lang][k] ?? window.I18N?.[cfg.lang]?.[k] ?? window.I18N?.en?.[k] ?? k;
  if (vars && typeof s === "string") for (const v in vars) s = s.replace("{" + v + "}", vars[v]); return s; };

function paintText() {
  document.documentElement.lang = cfg.lang;
  document.documentElement.dataset.theme = cfg.theme;
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  document.querySelectorAll("[data-tt]").forEach(el => { el.title = t(el.dataset.tt); el.setAttribute("aria-label", el.title); });
  $("q").placeholder = t("qPh"); $("nbQ").placeholder = t("nbAskPh"); $("nbQ").setAttribute("aria-label", t("nbAskPh"));
  window.LANG = cfg.lang; me.user = cfg.token ? { name: cfg.user } : null;
  $("langBtn").textContent = t("lang");
  $("themeBtn").textContent = cfg.theme === "dark" ? "☀" : "☾";
  $("meBox").hidden = !cfg.token; $("loginBox").hidden = !!cfg.token;
  $("meName").textContent = cfg.user || t("loggedIn");
  paintVideo();
}
const save = () => chrome.storage.local.set({ cfg });

// ---------------------------------------------------------------- server calls
const base = () => (cfg.backend || DEFAULT_SERVER).replace(/\/+$/, "");
function headers() {
  const h = { "Content-Type": "application/json", "x-lang": cfg.lang };
  if (cfg.token) h.Authorization = "Bearer " + cfg.token;
  return h;
}
async function api(path, body, opt) {          // opt = {method, body}: used by the notebook (PUT notes)
  const r = await fetch(base() + path, opt ? { method: opt.method, headers: headers(), body: JSON.stringify(opt.body) }
    : body === undefined ? { headers: headers() } : { method: "POST", headers: headers(), body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({ detail: "bad server response" }));
  if (r.status === 401) { openSettings(true); throw new Error(t("needLogin")); }
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "HTTP " + r.status);
  return d;
}
// Streaming ask: the server sends one line per finished step, then the final answer.
async function askStream(body, onEvent) {
  const r = await fetch(base() + "/api/ask_stream", { method: "POST", headers: headers(), body: JSON.stringify(body) });
  if (!r.ok || !r.body) return api("/api/ask", body);          // older server or an error: normal request
  const reader = r.body.getReader(), dec = new TextDecoder();
  let buf = "", out = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 2);
      if (!line.startsWith("data: ")) continue;
      const ev = JSON.parse(line.slice(6));
      if (ev.ev === "done") out = ev.data;
      else if (ev.ev === "error") throw new Error(ev.detail);
      else onEvent(ev);
    }
  }
  if (!out) throw new Error(t("lost"));
  return out;
}

// ---------------------------------------------------------------- the YouTube tab
function videoIdOf(url) {
  const m = /[?&]v=([\w-]{11})/.exec(url || "") || /youtube\.com\/(?:shorts|live|embed)\/([\w-]{11})/.exec(url || "");
  return m ? m[1] : null;
}
const inPage = (func, args = []) => chrome.scripting.executeScript({ target: { tabId }, world: "MAIN", func, args }).then(r => r[0].result);

// These three functions run inside the YouTube page, so the captions are fetched from the user's own browser.
function pageCaptions() {
  return (async () => {
    const pr = document.querySelector("#movie_player")?.getPlayerResponse?.() || window.ytInitialPlayerResponse;
    const tracks = pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    if (!tracks.length) return { error: "no captions" };
    const tr = tracks.find(x => x.languageCode?.startsWith("bn")) || tracks.find(x => x.languageCode?.startsWith("en")) || tracks[0];
    const txt = await (await fetch(tr.baseUrl + "&fmt=json3")).text();
    if (!txt) return { error: "empty captions" };
    const segs = (JSON.parse(txt).events || []).filter(e => e.segs).map(e => ({ start: e.tStartMs / 1000,
      end: (e.tStartMs + (e.dDurationMs || 2000)) / 1000, text: e.segs.map(s => s.utf8).join("").replace(/\n/g, " ").trim() })).filter(s => s.text);
    return segs.length ? { segs, title: pr?.videoDetails?.title || document.title } : { error: "empty captions" };
  })().catch(e => ({ error: String(e) }));
}
function pageTranscriptPanel() {       // fallback: read YouTube's own "Show transcript" panel
  return (async () => {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const sec = s => s.trim().split(":").reduce((a, x) => a * 60 + Number(x), 0);
    // YouTube has used two layouts for this panel; read whichever one is on the page
    const ROWS = "transcript-segment-view-model, ytd-transcript-segment-renderer";
    const TIME = '[class*="SegmentViewModelTimestamp"]:not([class*="A11y"]), .segment-timestamp';
    const TEXT = ".ytAttributedStringHost, .segment-text";
    let rows = document.querySelectorAll(ROWS);
    if (!rows.length) {
      const btn = [...document.querySelectorAll("button")].find(b => /^show transcript$/i.test((b.getAttribute("aria-label") || b.textContent).trim())) ||
        [...document.querySelectorAll("button")].find(b => /transcript/i.test((b.getAttribute("aria-label") || "") + b.textContent));
      if (btn) btn.click();
      for (let i = 0; i < 16 && !rows.length; i++) { await wait(500); rows = document.querySelectorAll(ROWS); }
    }
    if (!rows.length) return { error: "no transcript panel" };
    const segs = [...rows].map(r => ({ start: sec(r.querySelector(TIME)?.textContent || "0:00"),
      text: (r.querySelector(TEXT)?.textContent || "").trim() })).filter(s => s.text && !/^\[[^\]]*\]$/.test(s.text));
    segs.forEach((s, i) => { s.end = i + 1 < segs.length ? Math.max(segs[i + 1].start, s.start + 1) : s.start + 5; });
    return segs.length ? { segs, title: document.title.replace(/^\(\d+\)\s*/, "").replace(/ - YouTube$/, "") } : { error: "empty transcript" };
  })().catch(e => ({ error: String(e) }));
}
function pageShot() {                   // current video frame as a small JPEG
  const v = document.querySelector("video");
  if (!v || !v.videoWidth) return { error: "no video" };
  try {
    const W = Math.min(960, v.videoWidth), H = Math.round(v.videoHeight * W / v.videoWidth), c = document.createElement("canvas");
    c.width = W; c.height = H; c.getContext("2d").drawImage(v, 0, 0, W, H);
    return { src: c.toDataURL("image/jpeg", 0.7), t: v.currentTime };
  } catch (e) { return { error: String(e) }; }
}
function pageSeek(s) { const v = document.querySelector("video"); if (v) { if (s != null) { v.currentTime = s; v.play(); } return v.currentTime; } return 0; }

let titleCache = "";
function paintVideo() {
  $("composer").hidden = !vid; $("thumb").hidden = !vid;
  if (!vid) { $("vtitle").textContent = t("openYt"); $("vstate").hidden = true; $("prep").hidden = true; return; }
  $("thumb").hidden = docMode; $("docIcon").hidden = !docMode; $("docExit").hidden = !docMode;
  if (!docMode) $("thumb").src = "https://i.ytimg.com/vi/" + vid + "/mqdefault.jpg";
  $("vtitle").textContent = titleCache || vid;
  const label = { done: t("ready"), running: t("preparing"), unknown: t("notReady"), error: t("failed") }[state] || "";
  $("vstate").hidden = !label; $("vstate").textContent = label;
  $("vstate").className = "pill " + ({ done: "ok", running: "warn", error: "bad" }[state] || "");
  $("prep").hidden = state !== "unknown" && state !== "error";
}
async function watchJob() {            // poll until the server finishes building the index
  for (;;) {
    const myVid = vid, d = await api("/api/job/" + vid);
    if (myVid !== vid) return;
    if (d.status === "done") { state = "done"; titleCache = d.meta?.title || titleCache; if (cur) cur.title = titleCache; paintVideo(); return; }
    if (d.status !== "running") { state = d.status === "error" ? "error" : "unknown"; if (d.msg) $("vstate").title = d.msg; paintVideo(); return; }
    state = "running"; paintVideo(); if (d.msg) $("vstate").textContent = d.msg;
    await sleep(2000);
  }
}
async function refreshVideo() {
  if (docMode) return;                  // a PDF is open: switching tabs must not replace it
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const id = videoIdOf(tab?.url);
  tabId = tab?.id ?? null;
  if (id === vid) return;
  vid = id; state = id ? "unknown" : "none"; titleCache = id ? (tab.title || "").replace(/^\(\d+\)\s*/, "").replace(/ - YouTube$/, "") : "";
  $("p_chat").innerHTML = id ? '<p class="muted">' + t("hint") + "</p>" : ""; $("p_sum").innerHTML = ""; $("p_quiz").innerHTML = "";
  cur = id ? { video_id: id, title: titleCache } : null; nbLoadedFor = null;
  paintVideo(); showTab("chat");
  if (id) watchJob().catch(() => {});
}
async function prepare() {
  $("prep").disabled = true; state = "running"; paintVideo();
  try {
    $("vstate").textContent = t("captions");
    let got = await inPage(pageCaptions);
    if (got.error) got = await inPage(pageTranscriptPanel);
    if (got.error) { $("vstate").textContent = t("noCaptions"); await api("/api/index", { url: "https://www.youtube.com/watch?v=" + vid }); }
    else { titleCache = got.title || titleCache; await api("/api/index_transcript", { video_id: vid, title: titleCache, segments: got.segs }); }
    await watchJob();
  } catch (e) { state = "error"; paintVideo(); $("vstate").textContent = e.message; }
  $("prep").disabled = false;
}

// ---------------------------------------------------------------- chat
const chip = r => '<button class="chip" type="button" data-s="' + r.start + '" title="' + esc(r.preview || "") + '">▸ ' + fmt(r.start) + "</button>";
function answerHtml(a, refs) {
  let h = "<h3>" + esc(a.title) + '</h3><p style="margin:2px 0 6px;color:var(--text2)">' + esc(a.summary) + "</p>";
  (a.sections || []).forEach(s => {
    h += (s.heading ? "<h4>" + esc(s.heading) + "</h4>" : "") + "<ul>" + (s.points || []).map(p => "<li>" + esc(p.text) + " " +
      (p.cites || []).map(n => { const r = refs.find(x => x.n === n); return r ? chip(r) : ""; }).join("") + "</li>").join("") + "</ul>";
  });
  return h;
}
const stepsHtml = () => '<div class="steps">' + t("steps").map((s, i) => '<span data-k="' + STAGES[i] + '">' + s + "</span>").join("") + "</div>";

async function ask() {
  const q = $("q").value.trim();
  if (!q || !vid) return;
  if (state !== "done") { await prepare(); if (state !== "done") return; }
  $("q").value = ""; $("ask").disabled = true;
  const hist = chats[vid] = chats[vid] || [];
  const box = document.createElement("div");
  box.innerHTML = '<div class="bub">' + esc(q) + '</div><div class="card">' + stepsHtml() + '<div class="body"><span class="spin"></span> <span class="muted">' + t("working") + "</span></div></div>";
  $("p_chat").appendChild(box);
  const body = box.querySelector(".body"), scroll = () => box.scrollIntoView({ block: "end", behavior: "smooth" });
  scroll();
  let refs = [];
  try {
    const now = $("sp").checked ? await inPage(pageSeek, [null]) : null;
    const d = await askStream({ video_id: vid, question: q, current_time: now, clip: false, history: hist.slice(-3).map(x => ({ q: x.standalone || x.q })) }, ev => {
      if (ev.ev === "stage") box.querySelector('[data-k="' + ev.name + '"]')?.classList.add("done");
      if (ev.ev === "evidence") { refs = ev.refs; body.innerHTML = refs.map(chip).join(" ") + ' <span class="spin"></span>'; }
      if (ev.ev === "draft") body.innerHTML = '<span class="pill warn"><span class="spin"></span> ' + t("checking") + "</span>" + answerHtml(ev.answer, refs);
      scroll();
    });
    const tr = d.trace || {};
    if (d.found) box.querySelectorAll(".steps span").forEach(s => s.classList.add("done"));
    hist.push({ q, standalone: tr.standalone });
    let h = tr.standalone ? '<div class="muted">' + t("understood") + ": <b>" + esc(tr.standalone) + "</b></div>" : "";
    if (!d.found) {
      h += '<span class="pill bad">' + t("notInVideo") + '</span><p style="margin:6px 0 0">' + esc(d.message) + "</p>";
      if (d.general) h += '<p class="pill warn" style="margin-top:8px">' + t("general") + '</p><p style="white-space:pre-wrap;margin:4px 0 0">' + esc(d.general) + "</p>";
    } else {
      h += '<span class="pill ' + (tr.verify === "ok" ? "ok" : "warn") + '">' + (tr.claims_supported || 0) + "/" + (tr.claims_total || 0) + " " + t("verified") + "</span>";
      h += d.answer ? answerHtml(d.answer, d.refs || []) : "<p>" + esc(d.note) + "</p>";
      h += '<div style="margin-top:8px">' + (d.segments || []).map(s => '<button class="chip" type="button" data-s="' + s.start + '">▸ ' + fmt(s.start) + (docMode ? (Math.ceil(s.end / 60) > Math.floor(s.start / 60) + 1 ? "–p." + Math.ceil(s.end / 60) : "") : "–" + fmt(s.end)) + "</button>").join(" ") + "</div>";
    }
    if (d.found && d.answer) h += '<div class="addn"><button class="btn ghost sm" type="button">' + t("toNotes") + "</button></div>";
    body.innerHTML = h;
    const an = body.querySelector(".addn button");
    if (an) an.onclick = async () => { await openNotebook(); window.answerToNotes(q, d); an.textContent = "✓ " + t("added"); an.disabled = true; };
  } catch (e) { body.innerHTML = '<span class="pill bad">' + esc(e.message) + "</span>"; }
  $("ask").disabled = false; scroll(); $("q").focus();
}

// ---------------------------------------------------------------- summary and quiz tabs
async function loadSummary() {
  const p = $("p_sum");
  if (state !== "done") { p.innerHTML = '<p class="muted">' + t("notReady") + "</p>"; return; }
  p.innerHTML = '<p><span class="spin"></span> <span class="muted">' + t("working") + "</span></p>";
  try {
    const d = await api("/api/chapters/" + vid);
    p.innerHTML = '<div class="card"><p style="margin:0 0 8px">' + esc(d.summary || "") + "</p>" + (d.chapters || []).map(c =>
      '<div style="margin:6px 0">' + chip({ start: c.start }) + " <b>" + esc(c.title) + '</b><div class="muted">' + esc(c.gist || "") + "</div></div>").join("") + "</div>";
  } catch (e) { p.innerHTML = '<span class="pill bad">' + esc(e.message) + "</span>"; }
}
async function loadQuiz() {
  const p = $("p_quiz");
  if (state !== "done") { p.innerHTML = '<p class="muted">' + t("notReady") + "</p>"; return; }
  p.innerHTML = '<p><span class="spin"></span> <span class="muted">' + t("working") + "</span></p>";
  try {
    const now = $("sp").checked ? await inPage(pageSeek, [null]) : null;
    const d = await api("/api/quiz", { video_id: vid, n: 5, current_time: now });
    p.innerHTML = (d.questions || []).map((x, i) => '<div class="card" data-ans="' + x.answer + '"><b>' + (i + 1) + ". " + esc(x.q) + "</b>" +
      x.options.map((o, j) => '<button class="opt" type="button" data-j="' + j + '">' + esc(o) + "</button>").join("") +
      '<div class="muted why" hidden>' + esc(x.explanation || "") + " " + (x.start != null ? chip({ start: x.start }) : "") + "</div></div>").join("") ||
      '<p class="muted">' + t("failed") + "</p>";
  } catch (e) { p.innerHTML = '<span class="pill bad">' + esc(e.message) + "</span>"; }
}
function showTab(name) {
  ["chat", "sum", "quiz", "notes"].forEach(k => { $("p_" + k).hidden = k !== name; $("t_" + k).setAttribute("aria-selected", k === name); });
  $("p_notes").classList.toggle("hide", name !== "notes"); $("main").classList.toggle("nbmode", name === "notes");
  $("composer").hidden = !vid || name !== "chat";
  if (name === "sum" && vid && !$("p_sum").innerHTML) loadSummary();
  if (name === "notes") openNotebook();
  if (name === "quiz" && vid && !$("p_quiz").innerHTML) $("p_quiz").innerHTML = '<div class="row" style="flex-wrap:wrap;margin-bottom:10px"><button class="btn" type="button" id="mkQuiz">' + t("makeQuiz") +
    '</button><button class="btn ghost" type="button" id="mkRev">' + t("review") + "</button></div>";
}

// ---------------------------------------------------------------- PDF / slides
async function uploadDoc(file) {
  if (!cfg.token) { openSettings(true); $("setMsg").textContent = t("docLogin"); return; }
  const fd = new FormData(); fd.append("file", file); fd.append("title", file.name.replace(/\.(pdf|pptx)$/i, ""));
  docMode = true; vid = "upload"; state = "running"; titleCache = file.name; paintVideo(); $("vstate").textContent = t("uploading");
  try {
    const r = await fetch(base() + "/api/upload", { method: "POST", headers: { Authorization: "Bearer " + cfg.token, "x-lang": cfg.lang }, body: fd });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "HTTP " + r.status);
    let j = d;
    while (j.status === "running") { $("vstate").textContent = j.msg || t("reading"); await sleep(1500); j = await api("/api/job/" + d.video_id); }
    if (j.status !== "done") throw new Error(j.msg || t("failed"));
    vid = j.meta.video_id; state = "done"; titleCache = j.meta.title;
    cur = { video_id: vid, title: titleCache, doc: j.meta.doc, duration: j.meta.duration }; nbLoadedFor = null;
    $("p_chat").innerHTML = '<p class="muted">' + t("hint") + "</p>"; $("p_sum").innerHTML = ""; $("p_quiz").innerHTML = "";
    $("sp").checked = false; $("sp").disabled = true; paintVideo(); showTab("chat");
  } catch (e) { state = "error"; paintVideo(); $("vstate").textContent = e.message; }
}
function exitDoc() { docMode = false; vid = null; $("sp").disabled = false; refreshVideo(); }

// flashcards made in the notebook (AI -> Flashcards), reviewed with spaced repetition
let rdeck = [], rpos = 0;
async function loadReview() {
  const p = $("p_quiz"), box = document.createElement("div"); box.id = "revBox"; box.className = "card";
  p.querySelector("#revBox")?.remove(); p.prepend(box);
  if (!cfg.token) { box.innerHTML = '<span class="muted">' + t("cardsLogin") + "</span>"; return; }
  box.innerHTML = '<span class="spin"></span>';
  try { const d = await api("/api/cards?video_id=" + encodeURIComponent(vid)); rdeck = d.cards || []; rpos = 0; drawReview(); }
  catch (e) { box.innerHTML = '<span class="pill bad">' + esc(e.message) + "</span>"; }
}
function drawReview() {
  const b = $("revBox"); if (!b) return;
  if (!rdeck.length) { b.innerHTML = '<span class="muted">' + t("noCards") + "</span>"; return; }
  if (rpos >= rdeck.length) { b.innerHTML = "<b>" + t("reviewDone") + "</b>"; return; }
  const c = rdeck[rpos];
  b.innerHTML = '<span class="pill">' + t("cardOf", { i: rpos + 1, n: rdeck.length }) + '</span><p style="font-weight:650;font-size:15.5px;margin:10px 0 6px">' + esc(c.front) +
    '</p><p id="rBack" hidden style="margin:0 0 8px;color:var(--text2)">' + esc(c.back) + " " + (c.start != null ? chip({ start: c.start }) : "") + '</p><div class="row" id="rAct"><button class="btn" type="button" id="rShow">' + t("showAnswer") + "</button></div>";
  $("rShow").onclick = () => {
    $("rBack").hidden = false;
    $("rAct").innerHTML = ["again", "hard", "good", "easy"].map((k, g) => '<button class="btn ghost sm" type="button" data-g="' + g + '">' + t(k) + "</button>").join("");
    $("rAct").querySelectorAll("[data-g]").forEach(x => x.onclick = async () => {
      const g = +x.dataset.g; try { await api("/api/cards/" + c.id + "/review", { grade: g }); } catch (e) { toast(e.message); return; }
      if (g === 0) rdeck.push(c); rpos++; drawReview();
    });
  };
}

// ---------------------------------------------------------------- settings and events
function openSettings(open) { $("settings").hidden = !open; $("gear").setAttribute("aria-expanded", String(open)); }
async function login() {
  $("setMsg").textContent = t("working");
  try {
    const d = await api("/api/auth/token", { email: $("email").value.trim(), password: $("pass").value });
    $("pass").value = "";
    if (!d.token) { $("setMsg").textContent = t("noLogin"); return; }
    cfg.token = d.token; cfg.user = d.user?.name || d.user?.email || ""; save(); paintText(); $("setMsg").textContent = t("loggedIn");
    if (vid) watchJob().catch(() => {});
  } catch (e) { $("setMsg").textContent = e.message; }
}

document.addEventListener("click", e => {
  const c = e.target.closest(".chip");
  if (c) { seek(Number(c.dataset.s)); return; }
  const o = e.target.closest(".opt");
  if (o) {
    const card = o.closest(".card"), right = Number(card.dataset.ans);
    card.querySelectorAll(".opt").forEach((b, j) => { b.disabled = true; if (j === right) b.classList.add("right"); });
    if (Number(o.dataset.j) !== right) o.classList.add("wrong");
    card.querySelector(".why").hidden = false;
    const all = [...document.querySelectorAll("#p_quiz .card[data-ans]")];
    if (cfg.token && all.every(x => x.querySelector(".opt:disabled"))) {
      const score = all.filter(x => !x.querySelector(".opt.wrong")).length;
      api("/api/quiz_result", { video_id: vid, score, total: all.length }).catch(() => {});
    }
    return;
  }
  if (e.target.id === "mkQuiz") loadQuiz();
  if (e.target.id === "mkRev") loadReview();
  const tb = e.target.closest("[data-tab]");
  if (tb) showTab(tb.dataset.tab);
});
$("ask").onclick = ask;
$("q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
$("prep").onclick = prepare;
$("gear").onclick = () => openSettings($("settings").hidden);
$("langBtn").onclick = () => { cfg.lang = cfg.lang === "en" ? "bn" : "en"; save(); paintText(); };
$("themeBtn").onclick = () => { cfg.theme = cfg.theme === "dark" ? "light" : "dark"; save(); paintText(); };
$("backend").onchange = () => { cfg.backend = $("backend").value.trim() || DEFAULT_SERVER; cfg.token = ""; cfg.user = ""; save(); paintText(); vid = null; refreshVideo(); };
$("loginBtn").onclick = login;
$("logoutBtn").onclick = () => { cfg.token = ""; cfg.user = ""; save(); paintText(); };
chrome.tabs.onActivated.addListener(refreshVideo);
chrome.tabs.onUpdated.addListener((id, info) => { if (info.url || info.status === "complete") refreshVideo(); });

chrome.storage.local.get(["cfg"], v => {
  cfg = { ...cfg, ...(v.cfg || {}) };
  $("backend").value = cfg.backend;
  paintText(); refreshVideo();
});
