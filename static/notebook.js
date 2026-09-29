/* Learning Mate AI — Notebook: one infinite page where you type, draw, paste screenshots and timestamps.
   Model (saved per user+video): {v:2, H, items:[{id,type:"text"|"img"|"ts",x,y,w,html|src|t}], ink:dataURL}
   Coordinates are in "units" = 1/1000 of the page width, so the page reflows on any screen size.
   Depends on globals from index.html: $, t, ic, esc, fmt, now, seek, cur, me, api, toast, sleep. */
(function () {
  const PAGE = $("nbPage"), INK = $("nbInk"), IX = INK.getContext("2d"), SCROLL = $("nbScroll");
  let items = [], H = 1600, inkImg = null, tool = "type", color = "#7c5cff", size = 3, sel = null;
  let inkHist = [], drawing = false, last = null, saveT = null, cap = null, capV = null, lastClick = null;
  const U = () => PAGE.clientWidth / 1000;               // px per unit
  const uid = () => Math.random().toString(36).slice(2, 9);

  /* ---------- render ---------- */
  function layout() {
    const u = U(); PAGE.style.height = H * u + "px";
    const d = devicePixelRatio || 1, w = Math.round(PAGE.clientWidth * d), h = Math.round(H * u * d);
    if (INK.width !== w || INK.height !== h) {
      const keep = inkNow(); INK.width = w; INK.height = h; INK.style.height = H * u + "px"; paintInk(keep);
    }
    PAGE.querySelectorAll(".nb-it").forEach(el => place(el, items.find(i => i.id === el.dataset.id)));
  }
  function place(el, it) { if (!it) return; const u = U(); el.style.left = it.x * u + "px"; el.style.top = it.y * u + "px"; if (it.w) el.style.width = it.w * u + "px"; }
  function inkNow() { return INK.width > 2 ? INK.toDataURL("image/png") : inkImg; }
  function paintInk(src) {
    IX.setTransform(1, 0, 0, 1, 0, 0); IX.clearRect(0, 0, INK.width, INK.height); if (!src) return;
    const im = new Image(); im.onload = () => { IX.setTransform(1, 0, 0, 1, 0, 0); IX.drawImage(im, 0, 0, INK.width, im.height * INK.width / im.width); }; im.src = src;
  }
  function build(it) {
    const el = document.createElement("div"); el.className = "nb-it nb-" + it.type; el.dataset.id = it.id;
    const bar = '<div class="nb-bar"><span class="nb-grip" title="' + esc(t("nbMove")) + '">' + ic("move", 12) + " " + esc(t("nbMove")) + '</span><button class="nb-del" title="Delete">' + ic("trash", 12) + "</button></div>";
    if (it.type === "text") el.innerHTML = bar + '<div class="nb-txt" contenteditable="true" spellcheck="false">' + (it.html || "") + "</div>";
    if (it.type === "img") el.innerHTML = bar + '<img draggable="false" src="' + it.src + '" alt=""><span class="nb-rs"></span>' + (it.cap ? '<div class="nb-cap">' + it.cap + "</div>" : "");
    if (it.type === "ts") el.innerHTML = bar + '<a class="tsn" data-t="' + it.t + '">' + ic("play", 10) + " " + fmt(it.t) + "</a>" + (it.label ? ' <span class="nb-lbl">' + esc(it.label) + "</span>" : "");
    PAGE.appendChild(el); place(el, it); wire(el, it); return el;
  }
  function renderAll() { PAGE.querySelectorAll(".nb-it").forEach(e => e.remove()); items.forEach(build); layout(); }

  /* ---------- item interactions: select, drag, resize, edit, delete ---------- */
  function select(el) { PAGE.querySelectorAll(".nb-it.sel").forEach(x => x.classList.remove("sel")); sel = el; if (el) el.classList.add("sel"); }
  function wire(el, it) {
    const tx = el.querySelector(".nb-txt");
    if (tx) {
      tx.addEventListener("input", () => { it.html = tx.innerHTML; grow(it, el); saveSoon(); });
      tx.addEventListener("focus", () => select(el));
      tx.addEventListener("blur", () => { if (!tx.textContent.trim() && !tx.querySelector("img")) remove(it.id); });
    }
    el.querySelector(".nb-del").onclick = e => { e.stopPropagation(); remove(it.id); };
    el.querySelectorAll(".tsn").forEach(a => a.onclick = e => { e.stopPropagation(); seek(+a.dataset.t); });
    const startDrag = (e, mode) => {
      if (tool !== "type") return; e.preventDefault(); e.stopPropagation(); select(el);
      const u = U(), sx = e.clientX, sy = e.clientY, ox = it.x, oy = it.y, ow = it.w || 0;
      const mv = ev => {
        const dx = (ev.clientX - sx) / u, dy = (ev.clientY - sy) / u;
        if (mode === "move") { it.x = Math.max(0, Math.min(1000 - (it.w || 60), ox + dx)); it.y = Math.max(0, oy + dy); }
        else { it.w = Math.max(80, Math.min(1000 - it.x, ow + dx)); }
        place(el, it); grow(it, el);
      };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); saveSoon(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up);
    };
    el.querySelector(".nb-grip").addEventListener("pointerdown", e => startDrag(e, "move"));
    if (it.type !== "text") el.addEventListener("pointerdown", e => { if (!e.target.closest(".nb-rs,.nb-del,.tsn")) startDrag(e, "move"); });
    const rs = el.querySelector(".nb-rs"); if (rs) rs.addEventListener("pointerdown", e => startDrag(e, "size"));
  }
  function grow(it, el) {           // page grows when content reaches the bottom
    const u = U(), bottom = it.y + (el ? el.offsetHeight / u : 60);
    if (bottom + 300 > H) { H = Math.ceil(bottom + 600); layout(); }
  }
  function remove(id) { items = items.filter(i => i.id !== id); const el = PAGE.querySelector('.nb-it[data-id="' + id + '"]'); if (el) el.remove(); sel = null; saveSoon(); }
  function add(it, focus) { it.id = uid(); items.push(it); const el = build(it); grow(it, el); if (focus && it.type === "text") setTimeout(() => el.querySelector(".nb-txt").focus(), 0); saveSoon(); return el; }

  /* free spot: last click, else just below the visible top of the notebook */
  function spot(w) {
    if (lastClick) { const p = lastClick; lastClick = { x: p.x, y: p.y + 40 }; return p; }
    const u = U(), y = (SCROLL.scrollTop + 30) / u;
    let yy = y; items.forEach(i => { const el = PAGE.querySelector('.nb-it[data-id="' + i.id + '"]'); if (el && i.y <= yy + 5 && i.y + el.offsetHeight / u > yy - 5) yy = i.y + el.offsetHeight / u + 16; });
    return { x: 40, y: yy };
  }

  /* ---------- page clicks: type mode creates a text box where you click ---------- */
  PAGE.addEventListener("pointerdown", e => {
    if (tool !== "type" || e.target !== PAGE) return;
    const r = PAGE.getBoundingClientRect(), u = U(); select(null);
    const x = (e.clientX - r.left) / u, y = (e.clientY - r.top) / u;
    lastClick = { x, y: y + 40 };
    setTimeout(() => add({ type: "text", x: Math.min(x, 700), y: y - 12, w: Math.min(560, 1000 - Math.min(x, 700)), html: "" }, true), 0);
  });
  document.addEventListener("keydown", e => {
    if ((e.key === "Delete" || e.key === "Backspace") && sel && !document.activeElement.closest(".nb-txt") && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) && !$("p_notes").classList.contains("hide")) {
      e.preventDefault(); remove(sel.dataset.id);
    }
  });

  /* ---------- ink (pen / highlighter / eraser) on top of everything, incl. screenshots ---------- */
  const pt = e => { const r = INK.getBoundingClientRect(), d = INK.width / r.width; return { x: (e.clientX - r.left) * d, y: (e.clientY - r.top) * d, p: e.pressure || .5 }; };
  INK.addEventListener("pointerdown", e => { if (tool === "type") return; drawing = true; INK.setPointerCapture(e.pointerId); inkHist.push(INK.toDataURL()); if (inkHist.length > 40) inkHist.shift(); last = pt(e); dot(last); });
  INK.addEventListener("pointermove", e => { if (!drawing) return; const p = pt(e); stroke(last, p); last = p; });
  const end = () => { if (!drawing) return; drawing = false; IX.globalAlpha = 1; IX.globalCompositeOperation = "source-over"; inkImg = INK.toDataURL("image/png"); saveSoon(); };
  INK.addEventListener("pointerup", end); INK.addEventListener("pointercancel", end);
  function brush(p) {
    const d = devicePixelRatio || 1;
    IX.globalCompositeOperation = tool === "eraser" ? "destination-out" : "source-over";
    IX.globalAlpha = tool === "marker" ? .33 : 1; IX.strokeStyle = IX.fillStyle = tool === "marker" ? "#facc15" : color;
    IX.lineWidth = (tool === "eraser" ? size * 6 : tool === "marker" ? size * 5 : size * (0.6 + p.p)) * d; IX.lineCap = "round"; IX.lineJoin = "round";
  }
  function stroke(a, b) { brush(b); IX.beginPath(); IX.moveTo(a.x, a.y); IX.lineTo(b.x, b.y); IX.stroke(); }
  function dot(p) { brush(p); IX.beginPath(); IX.arc(p.x, p.y, IX.lineWidth / 2, 0, 7); IX.fill(); }

  /* ---------- toolbar ---------- */
  function setTool(k) {
    tool = k; document.querySelectorAll("#nbTools [data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === k));
    PAGE.classList.toggle("drawmode", k !== "type"); INK.style.pointerEvents = k === "type" ? "none" : "auto";
    INK.style.cursor = k === "eraser" ? "cell" : "crosshair"; select(null);
  }
  document.querySelectorAll("#nbTools [data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  document.querySelectorAll("#nbTools .sw").forEach(s => s.onclick = () => { color = s.dataset.col; document.querySelectorAll("#nbTools .sw").forEach(x => x.classList.toggle("on", x === s)); if (tool === "type" || tool === "eraser") setTool("pen"); });
  $("nbSize").oninput = e => size = +e.target.value;
  document.querySelectorAll("#nbTools [data-fmt]").forEach(b => { b.onmousedown = e => e.preventDefault(); b.onclick = () => {
    const f = b.dataset.fmt, tx = document.activeElement && document.activeElement.closest(".nb-txt"); if (!tx) { toast(t("nbPickText")); return; }
    if (f === "h") document.execCommand("formatBlock", false, "h3"); else if (f === "hl") document.execCommand("hiliteColor", false, "rgba(250,204,21,.45)"); else if (f === "list") document.execCommand("insertUnorderedList"); else document.execCommand(f);
    tx.dispatchEvent(new Event("input"));
  }; });
  $("nbUndo").onclick = () => { const u = inkHist.pop(); inkImg = u || null; paintInk(inkImg); saveSoon(); };
  $("nbClear").onclick = () => { inkHist.push(INK.toDataURL()); inkImg = null; paintInk(null); saveSoon(); };
  $("nbTs").onclick = () => addTs();
  $("nbSnap").onclick = () => snap();
  $("nbPdf").onclick = () => exportPdf();

  function addTs(label) { const p = spot(); add({ type: "ts", x: p.x, y: p.y, t: Math.floor(now()), label: label || "" }); }

  /* ---------- fast screenshot ---------- */
  async function snap() {
    if (!cur) return; const sec = now(); let url = null;
    try {
      const v = $("vid");
      if (v) { const c = document.createElement("canvas"); c.width = v.videoWidth; c.height = v.videoHeight; c.getContext("2d").drawImage(v, 0, 0); url = c.toDataURL("image/jpeg", .85); }
      else {
        if (!cap) {
          toast(t("ssHint"));
          cap = await navigator.mediaDevices.getDisplayMedia({ video: { displaySurface: "browser", frameRate: 5 }, audio: false, preferCurrentTab: true, selfBrowserSurface: "include" });
          capV = document.createElement("video"); capV.muted = true; capV.srcObject = cap; await capV.play();
          cap.getVideoTracks()[0].addEventListener("ended", () => { cap = null; capV = null; });
        }
        for (let i = 0; i < 25; i++) { const a = capV.videoWidth / capV.videoHeight, b = innerWidth / innerHeight; if (capV.videoWidth && Math.abs(a - b) < .012) break; await sleep(80); }
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        // crop exactly the YouTube player (inset 3px so no rounded border / page UI leaks in)
        const r = $("playerBox").getBoundingClientRect(), s = capV.videoWidth / innerWidth, pad = 3;
        const sx = (r.left + pad) * s, sy = (r.top + pad) * s, w = Math.round((r.width - 2 * pad) * s), h = Math.round((r.height - 2 * pad) * s);
        const c = document.createElement("canvas"), k = Math.min(1, 1280 / w);
        c.width = Math.round(w * k); c.height = Math.round(h * k); c.getContext("2d").drawImage(capV, sx, sy, w, h, 0, 0, c.width, c.height); url = c.toDataURL("image/jpeg", .85);
      }
    } catch (e) { toast(t("ssDenied")); return; }
    const f = document.createElement("div"); f.className = "flash"; document.body.appendChild(f); setTimeout(() => f.remove(), 400);
    window.openNotes(); await sleep(30); const p = spot();
    const el = add({ type: "img", x: p.x, y: p.y, w: 620, src: url, cap: '<a class="tsn" data-t="' + Math.floor(sec) + '">' + ic("play", 10) + " " + fmt(sec) + "</a>" });
    const a = el.querySelector(".nb-cap .tsn"); if (a) a.onclick = e => { e.stopPropagation(); seek(+a.dataset.t); };
    el.querySelector("img").onload = () => grow(items[items.length - 1], el);
    toast(t("ssDone"));
  }

  /* ---------- save / load (account when logged in, else this browser) ---------- */
  function saveSoon() { $("nSave").textContent = t("saving"); clearTimeout(saveT); saveT = setTimeout(save, 900); }
  async function save() {
    if (!cur) return; inkImg = INK.width > 2 ? inkNow() : inkImg;
    const content = { v: 2, H, items, ink: inkImg, title: cur.title };
    if (me.user) { try { await api("/api/notes/" + cur.video_id, undefined, { method: "PUT", body: { content } }); $("nSave").innerHTML = ic("check", 12) + " " + t("saved"); } catch (e) { $("nSave").textContent = e.message; } }
    else { try { localStorage.setItem("notes_" + cur.video_id, JSON.stringify(content)); $("nSave").innerHTML = ic("check", 12) + " " + t("savedLocal"); } catch (e) { $("nSave").textContent = t("tooBig"); } }
  }
  window.loadNotes = async function () {
    items = []; H = 1600; inkImg = null; inkHist = []; lastClick = null; $("nSave").textContent = ""; let c = null;
    if (me.user) { try { c = (await api("/api/notes/" + cur.video_id)).content; } catch (e) {} }
    else { try { c = JSON.parse(localStorage.getItem("notes_" + cur.video_id) || "null"); } catch (e) {} }
    if (c && c.v === 2) { items = c.items || []; H = c.H || 1600; inkImg = c.ink || null; items = liftFigures(items); }
    else if (c) {                                   // migrate old notes (html editor + separate board)
      if (c.html) {
        const tmp = document.createElement("div"); tmp.innerHTML = c.html; let y = 40;
        tmp.querySelectorAll("figure").forEach(f => { const im = f.querySelector("img"); if (!im) return;
          const a = f.querySelector(".tsn"); items.push({ id: uid(), type: "img", x: 40, y: 0, w: 620, src: im.getAttribute("src"),
            cap: a ? '<a class="tsn" data-t="' + a.dataset.t + '">' + ic("play", 10) + " " + fmt(+a.dataset.t) + "</a>" : "" }); f.remove(); });
        if (tmp.textContent.trim()) { items.unshift({ id: uid(), type: "text", x: 40, y: 40, w: 900, html: tmp.innerHTML }); y = 160; }
        items.filter(i => i.type === "img").forEach(i => { i.y = y; y += 420; });
      }
      if (c.board) items.push({ id: uid(), type: "img", x: 40, y: 40 + 420 * items.length, w: 700, src: c.board });
    }
    renderAll(); paintInk(inkImg); setTool("type");
  };
  /* screenshots that ended up inside a text box (old notes) become their own draggable image items */
  function liftFigures(list) {
    const out = [];
    list.forEach(it => {
      if (it.type !== "text" || !/<img/i.test(it.html || "")) { out.push(it); return; }
      const tmp = document.createElement("div"); tmp.innerHTML = it.html; let y = it.y + 60;
      tmp.querySelectorAll("figure, img").forEach(f => { const im = f.tagName === "IMG" ? f : f.querySelector("img"); if (!im || !im.isConnected) return;
        const a = f.querySelector && f.querySelector(".tsn");
        out.push({ id: uid(), type: "img", x: it.x, y, w: 620, src: im.getAttribute("src"), cap: a ? '<a class="tsn" data-t="' + a.dataset.t + '">' + ic("play", 10) + " " + fmt(+a.dataset.t) + "</a>" : "" });
        y += 420; (f.tagName === "IMG" ? f : f).remove(); });
      if (tmp.textContent.trim()) out.push({ ...it, html: tmp.innerHTML });
    });
    return out;
  }
  window.nbRelayout = () => { if (!$("p_notes").classList.contains("hide")) layout(); };
  addEventListener("resize", window.nbRelayout);

  /* "Add to notes" from an answer */
  window.answerToNotes = function (q, d) {
    const a = d.answer; let h = "<h3>" + esc(a ? a.title : q) + "</h3><p><i>" + esc(q) + "</i></p>" + (a ? "<p>" + esc(a.summary) + "</p>" : "");
    if (a) a.sections.forEach(s => { h += "<p><b>" + esc(s.heading) + "</b></p><ul>" + s.points.map(p => "<li>" + esc(p.text) + " " + (p.cites || []).map(n => { const r = d.refs.find(x => x.n === n); return r ? "(" + fmt(r.start) + ")" : ""; }).join(" ") + "</li>").join("") + "</ul>"; });
    window.openNotes(); setTimeout(() => { const p = spot(); add({ type: "text", x: p.x, y: p.y, w: 900, html: h }); toast(t("addedToNotes")); }, 30);
  };
  window.nbTimestamp = addTs; window.nbSnap = snap;

  /* ---------- PDF: exactly what you see (text + ink + screenshots), plus clickable timestamp list ---------- */
  const loadJs = src => new Promise((ok, no) => { if (document.querySelector('script[src="' + src + '"]')) return ok(); const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  async function exportPdf() {
    if (!cur) return; toast(t("pdfWorking")); select(null);
    try {
      await loadJs("https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js");
      await loadJs("https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js");
      let maxY = 0; const u = U();
      PAGE.querySelectorAll(".nb-it").forEach(el => { maxY = Math.max(maxY, el.offsetTop + el.offsetHeight); });
      maxY = Math.max(maxY, inkBottom() / (devicePixelRatio || 1)) + 40;
      PAGE.classList.add("printing");
      const shot = await html2canvas(PAGE, { backgroundColor: "#ffffff", scale: 2, height: Math.min(maxY, PAGE.scrollHeight), windowWidth: document.documentElement.clientWidth, useCORS: true, logging: false });
      PAGE.classList.remove("printing");
      const { jsPDF } = window.jspdf, pdf = new jsPDF({ unit: "pt", format: "a4" }), pw = pdf.internal.pageSize.getWidth(), ph = pdf.internal.pageSize.getHeight(), m = 28;
      const iw = pw - 2 * m, scale = iw / shot.width, sliceH = Math.floor((ph - 2 * m - 30) / scale);
      pdf.setFontSize(9); pdf.setTextColor(90);
      for (let y = 0, pg = 0; y < shot.height; y += sliceH, pg++) {
        if (pg) pdf.addPage();
        const c = document.createElement("canvas"); c.width = shot.width; c.height = Math.min(sliceH, shot.height - y);
        c.getContext("2d").drawImage(shot, 0, y, shot.width, c.height, 0, 0, shot.width, c.height);
        pdf.textWithLink("Learning Mate AI  -  youtube.com/watch?v=" + cur.video_id, m, m, { url: "https://www.youtube.com/watch?v=" + cur.video_id });
        pdf.addImage(c.toDataURL("image/jpeg", .9), "JPEG", m, m + 14, iw, c.height * scale);
      }
      const ts = items.filter(i => i.type === "ts").map(i => i.t).concat(items.filter(i => i.type === "img" && i.cap).map(i => +(/data-t="(\d+)"/.exec(i.cap) || [0, 0])[1])).sort((a, b) => a - b);
      if (ts.length) { pdf.addPage(); pdf.setFontSize(13); pdf.setTextColor(20); pdf.text("Timestamps", m, m + 10); pdf.setFontSize(11); pdf.setTextColor(75, 47, 208);
        ts.forEach((s, i) => pdf.textWithLink(fmt(s) + "   https://youtu.be/" + cur.video_id + "?t=" + s, m, m + 34 + i * 18, { url: "https://youtu.be/" + cur.video_id + "?t=" + s })); }
      pdf.save((cur.title || "notes").replace(/[^\wঀ-৿ -]+/g, "").slice(0, 60) + " - notes.pdf");
    } catch (e) { PAGE.classList.remove("printing"); toast("PDF: " + e.message); }
  }
  function inkBottom() {
    try { const d = IX.getImageData(0, 0, INK.width, INK.height).data; for (let y = INK.height - 1; y >= 0; y -= 4) { const row = y * INK.width * 4; for (let x = 3; x < INK.width * 4; x += 16) if (d[row + x]) return y; } } catch (e) {}
    return 0;
  }
})();
