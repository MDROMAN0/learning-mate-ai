/* Learning Mate AI — study tools on the website: progress dashboard, spaced-repetition flashcard review,
   watch-progress tracking, search inside all notes, voice questions, quiz score saving.
   Depends on globals from index.html: $, t, ic, esc, fmt, fmtT, api, me, cur, now, view, openVid, toast, LANG. */
(function () {
  /* ---------- progress view ---------- */
  let deck = [], pos = 0;
  window.loadProgress = async function () {
    const box = $("progOut");
    if (!me.user) { box.innerHTML = '<div class="empty">' + t("progLogin") + "</div>"; return; }
    box.innerHTML = '<div class="shimmer"></div><div class="shimmer" style="width:70%"></div>';
    try {
      const [d, c] = await Promise.all([api("/api/dashboard"), api("/api/cards")]);
      deck = c.cards || []; pos = 0;
      let h = '<div class="pstats">' +
        stat("fire", d.streak, t("streak")) + stat("cards", c.due, t("dueCards")) +
        stat("chat", d.questions, t("questionsAsked")) + stat("quiz", d.quizzes, t("quizAvg")) + "</div>";
      h += '<div class="card" id="revBox" style="margin-top:14px"></div>';
      h += '<div class="plist">' + (d.videos.length ? d.videos.map(row).join("") : '<div class="empty">' + t("noProgress") + "</div>") + "</div>";
      box.innerHTML = h;
      box.querySelectorAll(".prow").forEach(el => el.onclick = () => openVid(el.dataset.id));
      drawReview();
    } catch (e) { box.innerHTML = '<div class="empty">' + esc(e.message) + "</div>"; }
  };
  const stat = (i, n, label) => '<div class="pstat">' + ic(i, 18) + "<b>" + (n || 0).toLocaleString(LANG === "bn" ? "bn-BD" : "en") + "</b><span>" + label + "</span></div>";
  function row(v) {
    const bar = '<div class="pbar"><i style="width:' + v.watched_pct + '%"></i></div>';
    const bits = [v.watched_pct + "% " + t("watched")];
    if (v.quiz_pct != null) bits.push(t("quizAvg") + " " + v.quiz_pct + "%");
    if (v.questions) bits.push(v.questions + " " + t("questionsAsked"));
    if (v.cards) bits.push(v.cards_due + "/" + v.cards + " " + t("dueCards"));
    return '<button class="prow" type="button" data-id="' + esc(v.video_id) + '"><div class="pt">' + esc(v.title) + (v.has_notes ? " " + ic("book", 13) : "") + "</div>" + bar +
      '<div class="muted" style="font-size:12.5px">' + bits.map(esc).join(" · ") + "</div></button>";
  }
  function drawReview() {
    const b = $("revBox"); if (!b) return;
    if (!deck.length) { b.innerHTML = '<div class="muted">' + t("noDue") + "</div>"; return; }
    if (pos >= deck.length) { b.innerHTML = "<b>" + t("reviewDone") + "</b>"; return; }
    const c = deck[pos];
    b.innerHTML = '<div class="row" style="justify-content:space-between"><span class="badge">' + ic("cards", 12) + " " + t("cardOf", { i: pos + 1, n: deck.length }) + '</span><button class="btn sm ghost" id="cDel" type="button" aria-label="' + esc(t("deleteCard")) + '">' + ic("trash", 13) + "</button></div>" +
      '<div class="cfront">' + esc(c.front) + '</div><div class="cback hide" id="cBack">' + esc(c.back) +
      (c.start != null ? ' <span class="chip" id="cGo">' + ic("play", 10) + " " + fmtT(c.start) + "</span>" : "") + "</div>" +
      '<div class="row" id="cAct" style="justify-content:center;margin-top:12px"><button class="btn pri" type="button" id="cShow">' + t("showAnswer") + "</button></div>";
    $("cShow").onclick = () => {
      $("cBack").classList.remove("hide");
      $("cAct").innerHTML = [["again", 0, "bad"], ["hard", 1, "warn"], ["good", 2, "ok"], ["easy", 3, "ok"]].map(([k, g]) => '<button class="btn sm" type="button" data-g="' + g + '">' + t(k) + "</button>").join("");
      $("cAct").querySelectorAll("[data-g]").forEach(x => x.onclick = () => grade(+x.dataset.g));
    };
    if ($("cGo")) $("cGo").onclick = () => window.openAt(c.video_id, c.start);
    $("cDel").onclick = async () => { try { await api("/api/cards/" + c.id, undefined, { method: "DELETE" }); } catch (_) {} deck.splice(pos, 1); drawReview(); };
  }
  async function grade(g) {
    const c = deck[pos];
    try { await api("/api/cards/" + c.id + "/review", { grade: g }); } catch (e) { toast(e.message); return; }
    if (g === 0) deck.push(c);           // "again": see it once more in this session
    pos++; drawReview();
  }

  /* ---------- watch progress: remember how far each video was watched (logged-in users) ---------- */
  let lastSent = 0;
  setInterval(() => {
    if (!me.user || !cur || cur.pending || cur.doc || $("v_work").classList.contains("hide")) return;
    const s = now(); if (!s || Math.abs(s - lastSent) < 10) return;
    lastSent = s;
    fetch("/api/progress", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
      body: JSON.stringify({ video_id: cur.video_id, t: s, duration: cur.duration || 0 }) }).catch(() => {});
  }, 15000);

  /* ---------- search inside all notes ---------- */
  let st = null;
  window.searchNotes = function (q) {
    clearTimeout(st);
    st = setTimeout(async () => {
      const g = $("notesGrid");
      if (q.trim().length < 2) { window.loadNotesListOrig(); return; }
      try {
        const d = await api("/api/notes_search?q=" + encodeURIComponent(q.trim()));
        g.innerHTML = d.results.length ? d.results.map(r => '<button class="prow" type="button" data-id="' + esc(r.video_id) + '"><div class="pt">' + esc(r.title) + '</div><div class="muted" style="font-size:13px">' + hl(r.snippet, q) + "</div></button>").join("") : '<div class="empty">' + t("nothing") + "</div>";
        g.querySelectorAll(".prow").forEach(el => el.onclick = async () => { await openVid(el.dataset.id); window.openNotes(); });
      } catch (e) { g.innerHTML = '<div class="empty">' + esc(e.message) + "</div>"; }
    }, 300);
  };
  const hl = (s, q) => esc(s).replace(new RegExp("(" + q.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");

  /* ---------- voice question in the main chat ---------- */
  if (window.wireMic && $("qMic")) window.wireMic($("qMic"), $("q"), () => $("askBtn").click());
})();
