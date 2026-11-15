/* Learning Mate AI — Notebook: one infinite page where you type, draw, paste screenshots and timestamps.
   Model (saved per user+video): {v:2, H, items:[{id,type:"text"|"img"|"ts",x,y,w,html|src|t}], ink:dataURL}
   Coordinates are in "units" = 1/1000 of the page width, so the page reflows on any screen size.
   Depends on globals from index.html: $, t, ic, esc, fmt, now, seek, cur, me, api, toast, sleep. */
(function () {
  const PAGE = $("nbPage"), INK = $("nbInk"), IX = INK.getContext("2d"), SCROLL = $("nbScroll");
  let items = [], H = 1600, inkImg = null, tool = "type", color = "#7c5cff", size = 3, sel = null;
  let inkHist = [], inkRedo = [], drawing = false, last = null, saveT = null, cap = null, capV = null, lastClick = null;
  let shapeStart = null, shapeBase = null, zoom = 1;
  const SHAPES = ["line", "arrow", "rect", "ellipse"];
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
  function place(el, it) { if (!it) return; const u = U(); el.style.left = it.x * u + "px"; el.style.top = it.y * u + "px"; if (it.w) el.style.width = it.w * u + "px";
    el.classList.toggle("bin", it.y * u < 30); el.style.zIndex = 2 + Math.max(0, items.indexOf(it)); }   // too close to the top: show the move/delete bar inside the item
  function inkNow() { return INK.width > 2 ? INK.toDataURL("image/png") : inkImg; }
  function paintInk(src) {
    IX.setTransform(1, 0, 0, 1, 0, 0); IX.clearRect(0, 0, INK.width, INK.height); if (!src) return;
    const im = new Image(); im.onload = () => { IX.setTransform(1, 0, 0, 1, 0, 0); IX.drawImage(im, 0, 0, INK.width, im.height * INK.width / im.width); }; im.src = src;
  }
  function build(it) {
    const el = document.createElement("div"); el.className = "nb-it nb-" + it.type + (it.sticky ? " nb-sticky" : ""); el.dataset.id = it.id;
    if (it.sticky) el.style.setProperty("--stk", it.sticky);
    const bar = '<div class="nb-bar"><span class="nb-grip" title="' + esc(t("nbMove")) + '">' + ic("move", 12) + " " + esc(t("nbMove")) + '</span><button class="nb-act" data-b="dup" title="' + esc(t("nbDup")) + '">' + ic("copy", 12) + '</button><button class="nb-act" data-b="front" title="' + esc(t("nbFront")) + '">' + ic("up", 12) + '</button><button class="nb-act" data-b="back" title="' + esc(t("nbBack")) + '">' + ic("down", 12) + '</button><button class="nb-del" title="Delete">' + ic("trash", 12) + "</button></div>";
    if (it.type === "text") el.innerHTML = bar + '<div class="nb-txt" contenteditable="true" spellcheck="false">' + (it.html || "") + '</div><span class="nb-rs" title="' + esc(t("nbResize")) + '"></span>';
    if (it.type === "img") el.innerHTML = bar + '<img draggable="false" src="' + it.src + '" alt=""><span class="nb-rs"></span>' + (it.cap ? '<div class="nb-cap">' + it.cap + "</div>" : "");
    if (it.type === "ts") el.innerHTML = bar + '<a class="tsn" data-t="' + it.t + '">' + ic("play", 10) + " " + fmt(it.t) + "</a>" + (it.label ? ' <span class="nb-lbl">' + esc(it.label) + "</span>" : "");
    PAGE.appendChild(el); place(el, it); wire(el, it); return el;
  }
  function renderAll() { PAGE.querySelectorAll(".nb-it").forEach(e => { try { e.remove(); } catch (_) {} }); items.forEach(build); layout(); }

  /* ---------- item interactions: select, drag, resize, edit, delete ---------- */
  function select(el) { PAGE.querySelectorAll(".nb-it.sel").forEach(x => x.classList.remove("sel")); sel = el; if (el) el.classList.add("sel"); explainState(); }
  function wire(el, it) {
    const tx = el.querySelector(".nb-txt");
    if (tx) {
      tx.addEventListener("input", () => { it.html = tx.innerHTML; grow(it, el); saveSoon(); });
      tx.addEventListener("focus", () => select(el));
      tx.addEventListener("blur", () => { if (!tx.textContent.trim() && !tx.querySelector("img")) remove(it.id); });
    }
    el.querySelector(".nb-del").onclick = e => { e.stopPropagation(); remove(it.id); };
    el.querySelectorAll(".nb-act").forEach(b => { b.onpointerdown = e => e.stopPropagation(); b.onclick = e => { e.stopPropagation();
      if (b.dataset.b === "dup") return pasteItems([it]);
      items = items.filter(i => i !== it); if (b.dataset.b === "front") items.push(it); else items.unshift(it);
      PAGE.querySelectorAll(".nb-it").forEach(x => place(x, items.find(i => i.id === x.dataset.id))); saveSoon(); }; });
    el.querySelectorAll(".tsn").forEach(a => a.onclick = e => { e.stopPropagation(); seek(+a.dataset.t); });
    const startDrag = (e, mode) => {
      if (tool !== "type") return; e.preventDefault(); e.stopPropagation(); select(el);
      const u = U(), sx = e.clientX, sy = e.clientY, ox = it.x, oy = it.y, ow = it.w || el.offsetWidth / u;
      const mv = ev => {
        const dx = (ev.clientX - sx) / u, dy = (ev.clientY - sy) / u;
        if (mode === "move") { it.x = Math.max(0, Math.min(1000 - (it.w || 60), ox + dx)); it.y = Math.max(0, oy + dy); }
        else { it.w = Math.max(80, Math.min(1000 - it.x, ow + dx)); }
        place(el, it); grow(it, el);
      };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); removeEventListener("blur", up);
        if (mode === "move") { it.x = Math.round(it.x / 10) * 10; it.y = Math.round(it.y / 10) * 10; place(el, it); }   // snap to the grid
        saveSoon(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up); addEventListener("blur", up);
      try { e.target.setPointerCapture(e.pointerId); } catch (_) {}
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
    // keep moving down until the spot is below every item it touches (items are not sorted, so repeat)
    let yy = y, moved = true, guard = 0;
    while (moved && guard++ < 200) {
      moved = false;
      items.forEach(i => { const el = PAGE.querySelector('.nb-it[data-id="' + i.id + '"]'); const h = el ? el.offsetHeight / u : 60;
        if (i.y <= yy + 5 && i.y + h > yy - 5) { yy = i.y + h + 16; moved = true; } });
    }
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
  INK.addEventListener("pointerdown", e => {
    if (tool === "type") return; drawing = true; INK.setPointerCapture(e.pointerId);
    inkHist.push(INK.toDataURL()); if (inkHist.length > 40) inkHist.shift(); inkRedo = [];
    last = pt(e);
    if (SHAPES.includes(tool)) { shapeStart = last; shapeBase = IX.getImageData(0, 0, INK.width, INK.height); }
    else dot(last);
  });
  INK.addEventListener("pointermove", e => {
    if (!drawing) return; const p = pt(e);
    if (shapeStart) { IX.putImageData(shapeBase, 0, 0); shape(shapeStart, p, e.shiftKey); return; }   // live preview
    stroke(last, p); last = p;
  });
  // line / arrow / box / circle: drawn into the same ink layer, so undo, eraser, save and PDF just work
  function shape(a, b, square) {
    brush({ p: .5 }); IX.globalCompositeOperation = "source-over"; IX.globalAlpha = 1; IX.strokeStyle = color;
    IX.lineWidth = Math.max(2, size) * (devicePixelRatio || 1);
    let w = b.x - a.x, h = b.y - a.y;
    if (square && (tool === "rect" || tool === "ellipse")) { const m = Math.max(Math.abs(w), Math.abs(h)); w = Math.sign(w || 1) * m; h = Math.sign(h || 1) * m; }
    IX.beginPath();
    if (tool === "rect") IX.strokeRect(a.x, a.y, w, h);
    else if (tool === "ellipse") { IX.ellipse(a.x + w / 2, a.y + h / 2, Math.abs(w / 2), Math.abs(h / 2), 0, 0, 7); IX.stroke(); }
    else {
      IX.moveTo(a.x, a.y); IX.lineTo(b.x, b.y); IX.stroke();
      if (tool === "arrow") {
        const ang = Math.atan2(b.y - a.y, b.x - a.x), L = Math.max(12, IX.lineWidth * 4);
        IX.beginPath(); IX.moveTo(b.x, b.y); IX.lineTo(b.x - L * Math.cos(ang - .45), b.y - L * Math.sin(ang - .45));
        IX.moveTo(b.x, b.y); IX.lineTo(b.x - L * Math.cos(ang + .45), b.y - L * Math.sin(ang + .45)); IX.stroke();
      }
    }
  }
  const end = () => { if (!drawing) return; drawing = false; shapeStart = shapeBase = null; IX.globalAlpha = 1; IX.globalCompositeOperation = "source-over"; inkImg = INK.toDataURL("image/png"); saveSoon(); };
  INK.addEventListener("pointerup", end); INK.addEventListener("pointercancel", end);
  function brush(p) {
    const d = devicePixelRatio || 1;
    IX.globalCompositeOperation = tool === "eraser" ? "destination-out" : "source-over";
    IX.globalAlpha = tool === "marker" ? .33 : 1; IX.strokeStyle = IX.fillStyle = tool === "marker" ? "#facc15" : color;
    IX.lineWidth = (tool === "eraser" ? size * 6 : tool === "marker" ? size * 5 : size * (0.6 + p.p)) * d; IX.lineCap = "round"; IX.lineJoin = "round";
  }
  function stroke(a, b) { brush(b); IX.beginPath(); IX.moveTo(a.x, a.y); IX.lineTo(b.x, b.y); IX.stroke(); }
  function dot(p) { brush(p); IX.beginPath(); IX.arc(p.x, p.y, IX.lineWidth / 2, 0, 7); IX.fill(); }

  /* ---------- select tool: drag a box, then move or delete everything inside (notes + drawing) ---------- */
  let box = null;            // {x,y,w,h} in page px, ids: selected notes, patch: ink cut out of the box
  const BOX = document.createElement("div"); BOX.className = "nb-selbox hide";
  BOX.innerHTML = '<div class="nb-selbar"><button type="button" data-sa="del">' + ic("trash", 12) + " " + esc(t("nbSelDel")) + '</button></div>';
  PAGE.appendChild(BOX);
  const showBox = () => { if (!box) return BOX.classList.add("hide"); BOX.classList.remove("hide");
    Object.assign(BOX.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" }); };
  function clearBox() { box = null; showBox(); PAGE.querySelectorAll(".nb-it.msel").forEach(e => e.classList.remove("msel")); }
  function pickIn(r) {
    const pr = PAGE.getBoundingClientRect(), ids = [];
    PAGE.querySelectorAll(".nb-it").forEach(el => {
      const b = el.getBoundingClientRect(), x = b.left - pr.left, y = b.top - pr.top;
      const hit = x < r.x + r.w && x + b.width > r.x && y < r.y + r.h && y + b.height > r.y;
      el.classList.toggle("msel", hit); if (hit) ids.push(el.dataset.id);
    });
    return ids;
  }
  PAGE.addEventListener("pointerdown", e => {
    if (tool !== "select") return;
    if (e.target.closest(".nb-selbar")) return;
    const pr = PAGE.getBoundingClientRect(), sx = e.clientX - pr.left, sy = e.clientY - pr.top;
    e.preventDefault();
    if (box && sx > box.x && sx < box.x + box.w && sy > box.y && sy < box.y + box.h) return moveBox(e);
    // click right on one thing: select just that thing (and drag it straight away)
    const hit = [...PAGE.querySelectorAll(".nb-it")].reverse().find(el => { const b = el.getBoundingClientRect();
      return e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom; });
    if (hit) {
      clearBox(); const b = hit.getBoundingClientRect();
      box = { x: b.left - pr.left, y: b.top - pr.top, w: b.width, h: b.height, ids: [hit.dataset.id], one: true };
      hit.classList.add("msel"); showBox(); return moveBox(e);
    }
    clearBox(); box = { x: sx, y: sy, w: 0, h: 0, ids: [] }; showBox();
    const mv = ev => { const x = ev.clientX - pr.left, y = ev.clientY - pr.top;
      Object.assign(box, { x: Math.min(sx, x), y: Math.min(sy, y), w: Math.abs(x - sx), h: Math.abs(y - sy) }); showBox(); pickIn(box); };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up);
      if (box.w < 6 || box.h < 6) return clearBox(); box.ids = pickIn(box); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  function moveBox(e) {
    const d = INK.width / PAGE.clientWidth, u = U(), sx = e.clientX, sy = e.clientY, start = { x: box.x, y: box.y };
    inkHist.push(INK.toDataURL()); if (inkHist.length > 40) inkHist.shift(); inkRedo = [];
    const rx = Math.round(box.x * d), ry = Math.round(box.y * d), rw = Math.max(1, Math.round(box.w * d)), rh = Math.max(1, Math.round(box.h * d));
    const patch = document.createElement("canvas"); patch.width = rw; patch.height = rh;
    if (!box.one) { patch.getContext("2d").drawImage(INK, rx, ry, rw, rh, 0, 0, rw, rh); IX.setTransform(1, 0, 0, 1, 0, 0); IX.clearRect(rx, ry, rw, rh); }
    const base = IX.getImageData(0, 0, INK.width, INK.height);
    const its = box.ids.map(id => items.find(i => i.id === id)).filter(Boolean), orig = its.map(i => ({ x: i.x, y: i.y }));
    const mv = ev => {
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      box.x = Math.max(0, Math.min(PAGE.clientWidth - box.w, start.x + dx)); box.y = Math.max(0, start.y + dy); showBox();
      const ddx = box.x - start.x, ddy = box.y - start.y;
      IX.putImageData(base, 0, 0); IX.drawImage(patch, Math.round(box.x * d), Math.round(box.y * d));
      its.forEach((it, k) => { it.x = Math.max(0, orig[k].x + ddx / u); it.y = Math.max(0, orig[k].y + ddy / u);
        const el = PAGE.querySelector('.nb-it[data-id="' + it.id + '"]'); if (el) { place(el, it); grow(it, el); } });
    };
    const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); if (box.one) its.forEach(it => { it.x = Math.round(it.x / 10) * 10; it.y = Math.round(it.y / 10) * 10; const el = PAGE.querySelector('.nb-it[data-id="' + it.id + '"]'); if (el) place(el, it); });
      inkImg = INK.toDataURL(); saveSoon(); };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  }
  function deleteBox() {
    if (!box) return;
    const d = INK.width / PAGE.clientWidth;
    inkHist.push(INK.toDataURL()); inkRedo = [];
    if (!box.one) { IX.setTransform(1, 0, 0, 1, 0, 0); IX.clearRect(Math.round(box.x * d), Math.round(box.y * d), Math.ceil(box.w * d), Math.ceil(box.h * d)); }
    inkImg = INK.toDataURL();
    const ids = new Set(box.ids); items = items.filter(i => !ids.has(i.id));
    ids.forEach(id => PAGE.querySelector('.nb-it[data-id="' + id + '"]')?.remove());
    clearBox(); saveSoon();
  }
  BOX.querySelector('[data-sa="del"]').onclick = e => { e.stopPropagation(); deleteBox(); };
  document.addEventListener("keydown", e => {
    if (box && tool === "select" && (e.key === "Delete" || e.key === "Backspace") && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) { e.preventDefault(); deleteBox(); }
    if (box && e.key === "Escape") clearBox();
  });
  function clearAll() {
    if ((items.length || inkImg || INK.width > 2) && !confirm(t("nbClearAllQ"))) return;
    inkHist.push(INK.toDataURL()); inkRedo = []; inkImg = null; paintInk(null);
    items = []; clearBox(); renderAll(); saveSoon(); toast(t("nbCleared"));
  }

  /* ---------- copy / paste / duplicate (Ctrl+C, Ctrl+V, Ctrl+D) ---------- */
  let clip = [];
  const picked = () => box && box.ids.length ? box.ids.map(id => items.find(i => i.id === id)).filter(Boolean)
    : (sel ? [items.find(i => i.id === sel.dataset.id)].filter(Boolean) : []);
  function pasteItems(list) {
    if (!list.length) return; let last = null;
    list.forEach(src => { const c = JSON.parse(JSON.stringify(src)); c.x = Math.min(980, c.x + 30); c.y += 30; last = add(c); });
    if (last && list.length === 1) select(last); toast(t("nbPasted", { n: list.length }));
  }
  document.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey) || $("p_notes").classList.contains("hide") || document.activeElement.closest?.(".nb-txt,input,textarea")) return;
    const k = e.key.toLowerCase();
    if (k === "c" && picked().length) { clip = JSON.parse(JSON.stringify(picked())); toast(t("nbCopied", { n: clip.length })); }
    if (k === "v" && clip.length) { e.preventDefault(); pasteItems(clip); }
    if (k === "d" && picked().length) { e.preventDefault(); pasteItems(picked()); }
  });
  /* ---------- sticky note ---------- */
  const STICKY = ["#fde68a", "#bbf7d0", "#bfdbfe", "#fbcfe8", "#ddd6fe"]; let stickyN = 0;
  function addSticky() { const p = spot(260); const el = add({ type: "text", x: p.x, y: p.y, w: 260, sticky: STICKY[stickyN++ % STICKY.length], html: "" }, true); }
  /* ---------- listen: read the notebook aloud (browser voice, free, Bangla or English) ---------- */
  function listen(btn) {
    const ss = window.speechSynthesis; if (!ss) return toast(t("micFail"));
    if (ss.speaking) { ss.cancel(); btn.classList.remove("on"); return; }
    const text = notesText(); if (!text) return toast(t("nbListenEmpty"));
    const bn = /[\u0980-\u09FF]/.test(text), parts = text.match(/[^.!?।]+[.!?।]?/g) || [text];
    const voice = speechSynthesis.getVoices().find(v => v.lang.startsWith(bn ? "bn" : "en"));
    btn.classList.add("on");
    parts.forEach((p, i) => { const u = new SpeechSynthesisUtterance(p.trim()); u.lang = bn ? "bn-BD" : "en-US"; if (voice) u.voice = voice; u.rate = 1;
      if (i === parts.length - 1) u.onend = () => btn.classList.remove("on"); ss.speak(u); });
  }
  /* ---------- roadmap: the lecture as a winding road with numbered stops (click a stop's time to jump) ---------- */
  function roadmapSvg(d) {
    const st = d.steps, W = 1200, rowH = 190, perRow = 3, rows = Math.ceil(st.length / perRow), H = 150 + rows * rowH;
    const x = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const cols = ["#7c5cff", "#22d3ee", "#f43f5e", "#22c55e", "#f59e0b", "#a855f7", "#0ea5e9", "#ec4899"];
    const pos = st.map((_, i) => { const r = Math.floor(i / perRow), k = i % perRow, c = r % 2 ? perRow - 1 - k : k; return { x: 200 + c * 400, y: 150 + r * rowH }; });
    let path = "M " + (pos[0].x - 150) + " " + pos[0].y;
    pos.forEach((p, i) => { if (!i) { path += " L " + p.x + " " + p.y; return; } const q = pos[i - 1];
      path += q.y === p.y ? " L " + p.x + " " + p.y : " C " + (q.x + (q.x > 600 ? 170 : -170)) + " " + q.y + ", " + (p.x + (p.x > 600 ? 170 : -170)) + " " + p.y + ", " + p.x + " " + p.y; });
    const lp = pos[pos.length - 1]; path += " L " + (lp.x + (Math.floor((st.length - 1) / perRow) % 2 ? -130 : 130)) + " " + lp.y;
    let g = '<path d="' + path + '" stroke="#cbd5e1" stroke-width="34" fill="none" stroke-linecap="round" stroke-linejoin="round"/>' +
      '<path d="' + path + '" stroke="#fff" stroke-width="3" stroke-dasharray="14 12" fill="none"/>';
    st.forEach((s, i) => { const p = pos[i], col = cols[i % cols.length];
      g += '<circle cx="' + p.x + '" cy="' + p.y + '" r="30" fill="' + col + '" stroke="#fff" stroke-width="5"/>' +
        '<text x="' + p.x + '" y="' + (p.y + 9) + '" font-size="26" text-anchor="middle">' + x(s.emoji || String(i + 1)) + "</text>" +
        '<text x="' + p.x + '" y="' + (p.y - 46) + '" font-size="19" font-weight="800" fill="' + col + '" text-anchor="middle">' + (i + 1) + ". " + x(s.label.slice(0, 26)) + "</text>" +
        '<text x="' + p.x + '" y="' + (p.y + 62) + '" font-size="14" fill="#334155" text-anchor="middle">' + x(s.detail.slice(0, 48)) + "</text>" +
        (s.detail.length > 48 ? '<text x="' + p.x + '" y="' + (p.y + 80) + '" font-size="14" fill="#334155" text-anchor="middle">' + x(s.detail.slice(48, 96)) + "</text>" : "") +
        (s.start != null ? '<text x="' + p.x + '" y="' + (p.y + (s.detail.length > 48 ? 100 : 82)) + '" font-size="13" font-weight="700" fill="#7c5cff" text-anchor="middle">▸ ' + fmt(s.start) + "</text>" : ""); });
    g += '<text x="40" y="58" font-size="28" font-weight="800" fill="#111827">🗺 ' + x(d.title) + "</text>";
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '" font-family="Hind Siliguri, Noto Sans Bengali, Inter, sans-serif"><rect width="100%" height="100%" rx="18" fill="#f8fafc"/>' + g + "</svg>";
    return "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svg)));
  }

  /* ---------- toolbar ---------- */
  function setTool(k) {
    if (k !== "select") clearBox();
    tool = k; document.querySelectorAll("#nbTools [data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === k));
    PAGE.classList.toggle("drawmode", k !== "type"); PAGE.classList.toggle("selmode", k === "select");
    INK.style.pointerEvents = (k === "type" || k === "select") ? "none" : "auto";
    INK.style.cursor = k === "eraser" ? "cell" : "crosshair"; select(null);
    if (SHAPES.includes(k) && $("nbShapeBtn")) { $("nbShapeBtn").innerHTML = $("nbShapes").querySelector('[data-tool="' + k + '"]').innerHTML; }
    if ($("nbShapeBtn")) $("nbShapeBtn").classList.toggle("on", SHAPES.includes(k));
    if ($("nbShapes")) $("nbShapes").classList.add("hide");
  }
  document.querySelectorAll("#nbTools [data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
  document.querySelectorAll("#nbTools .sw").forEach(s => s.onclick = () => { color = s.dataset.col; document.querySelectorAll("#nbTools .sw").forEach(x => x.classList.toggle("on", x === s)); if (tool === "type" || tool === "eraser") setTool("pen"); });
  $("nbSize").oninput = e => size = +e.target.value;
  document.querySelectorAll("#nbTools [data-fmt]").forEach(b => { b.onmousedown = e => e.preventDefault(); b.onclick = () => {
    const f = b.dataset.fmt, tx = document.activeElement && document.activeElement.closest(".nb-txt"); if (!tx) { toast(t("nbPickText")); return; }
    if (f === "h") document.execCommand("formatBlock", false, "h3"); else if (f === "hl") document.execCommand("hiliteColor", false, "rgba(250,204,21,.45)"); else if (f === "list") document.execCommand("insertUnorderedList"); else document.execCommand(f);
    tx.dispatchEvent(new Event("input"));
  }; });
  $("nbUndo").onclick = () => { if (!inkHist.length) return; inkRedo.push(INK.toDataURL()); inkImg = inkHist.pop() || null; paintInk(inkImg); saveSoon(); };
  if ($("nbRedo")) $("nbRedo").onclick = () => { if (!inkRedo.length) return; inkHist.push(INK.toDataURL()); inkImg = inkRedo.pop(); paintInk(inkImg); saveSoon(); };
  if ($("nbClearAll")) $("nbClearAll").onclick = clearAll;
  if ($("nbSticky")) $("nbSticky").onclick = addSticky;
  if ($("nbListen")) $("nbListen").onclick = () => listen($("nbListen"));
  $("nbClear").onclick = () => { inkHist.push(INK.toDataURL()); inkRedo = []; inkImg = null; paintInk(null); saveSoon(); };
  // zoom: the page is 1000 units wide, so zooming = making the page wider than the view (scroll sideways)
  const setZoom = z => { zoom = Math.max(.6, Math.min(2.5, Math.round(z * 10) / 10)); PAGE.style.width = zoom * 100 + "%";
    if ($("nbZoomV")) $("nbZoomV").textContent = Math.round(zoom * 100) + "%"; layout(); };
  if ($("nbZoomIn")) { $("nbZoomIn").onclick = () => setZoom(zoom + .2); $("nbZoomOut").onclick = () => setZoom(zoom - .2); $("nbZoomV").onclick = () => setZoom(1); }
  document.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey) || $("p_notes").classList.contains("hide") || document.activeElement.closest?.(".nb-txt,input,textarea")) return;
    const k = e.key.toLowerCase();
    if (k === "z" && !e.shiftKey) { e.preventDefault(); $("nbUndo").click(); }
    if ((k === "y" || (k === "z" && e.shiftKey)) && $("nbRedo")) { e.preventDefault(); $("nbRedo").click(); }
  });
  // menus open as fixed popups next to their button, so a scrolling toolbar (phones) can't clip them
  function openMenu(btn, menu, other) {
    other?.classList.add("hide");
    if (!menu.classList.toggle("hide")) {
      const r = btn.getBoundingClientRect(), w = menu.offsetWidth, x = Math.max(8, Math.min(r.left, innerWidth - w - 8));
      Object.assign(menu.style, { position: "fixed", left: x + "px", top: r.bottom + 4 + "px", right: "auto" });
    }
  }
  if ($("nbShapeBtn")) $("nbShapeBtn").onclick = e => { e.stopPropagation(); openMenu($("nbShapeBtn"), $("nbShapes"), $("nbAIMenu")); };
  if ($("nbAI")) $("nbAI").onclick = e => { e.stopPropagation(); openMenu($("nbAI"), $("nbAIMenu"), $("nbShapes")); };
  addEventListener("scroll", e => { if (e.target === SCROLL) { $("nbShapes")?.classList.add("hide"); $("nbAIMenu")?.classList.add("hide"); } }, true);
  document.addEventListener("click", e => { if (!e.target.closest("#nbShapes,#nbAIMenu")) { $("nbShapes")?.classList.add("hide"); $("nbAIMenu")?.classList.add("hide"); } });
  document.querySelectorAll("#nbAIMenu [data-ai]").forEach(b => b.onclick = () => { $("nbAIMenu").classList.add("hide"); aiNotes(b.dataset.ai); });
  if ($("nbShare")) $("nbShare").onclick = shareLink;
  if ($("nbMic")) wireMic($("nbMic"), $("nbQ"), () => $("nbAskBtn").click());
  $("nbTs").onclick = () => addTs();
  $("nbSnap").onclick = () => snap();
  $("nbPdf").onclick = () => exportPdf();

  function addTs(label) { const p = spot(); add({ type: "ts", x: p.x, y: p.y, t: Math.floor(now()), label: label || "" }); }

  /* ---------- fast screenshot ---------- */
  async function snap() {
    if (!cur) return; let sec = now(); let url = null;
    try {
      const v = $("vid");
      if (window.nbGrab) {                   // Chrome extension: it grabs the frame from the YouTube tab itself
        const g = await window.nbGrab(); if (!g) throw new Error("no frame"); url = g.src; sec = g.t;
      }
      else if (v) { const c = document.createElement("canvas"); c.width = v.videoWidth; c.height = v.videoHeight; c.getContext("2d").drawImage(v, 0, 0); url = c.toDataURL("image/jpeg", .85); }
      else if (!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia)) {
        // phones/tablets can't capture the screen from a web page: drop the video thumbnail + exact timestamp instead
        url = "https://i.ytimg.com/vi/" + encodeURIComponent(cur.video_id) + "/hqdefault.jpg"; toast(t("ssMobile"));
      }
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
    const el = add({ type: "img", x: p.x, y: p.y, w: Math.min(620, Math.max(160, $("nbPage").clientWidth - p.x - 16)), src: url, cap: '<a class="tsn" data-t="' + Math.floor(sec) + '">' + ic("play", 10) + " " + fmt(sec) + "</a>" });
    const a = el.querySelector(".nb-cap .tsn"); if (a) a.onclick = e => { e.stopPropagation(); seek(+a.dataset.t); };
    el.querySelector("img").onload = () => grow(items[items.length - 1], el);
    toast(t("ssDone"));
  }


  /* ---------- Ask AI inside the notebook: answer card → "place in notebook"; "explain this" for selection / screenshot ---------- */
  const CARD = $("nbCard"); let cardData = null, selText = "";
  function explainState() {
    const it = sel && items.find(i => i.id === sel.dataset.id);
    const ok = !!selText || (it && (it.type === "ts" || (it.type === "img" && /data-t="\d+"/.test(it.cap || ""))));
    $("nbExplain").disabled = false; $("nbExplain").classList.toggle("ready", ok);
  }
  document.addEventListener("selectionchange", () => {
    const g = getSelection(), n = g && g.anchorNode, inNb = n && (n.nodeType === 1 ? n : n.parentElement)?.closest?.(".nb-txt");
    const txt = inNb ? String(g).trim() : "";
    if (txt || !inNb) { selText = txt; explainState(); }
  });
  const chip = (s0, vid) => '<span class="chip" data-s="' + s0 + '">' + ic("play", 10) + " " + fmt(s0) + "</span>";
  function showCard(html) {
    CARD.innerHTML = html; CARD.classList.remove("hide");
    CARD.querySelectorAll(".chip[data-s]").forEach(c => c.onclick = () => seek(+c.dataset.s));
    const x = CARD.querySelector("[data-x]"); if (x) x.onclick = () => CARD.classList.add("hide");
    const pl = CARD.querySelector("[data-place]"); if (pl) pl.onclick = place2nb;
  }
  const head = (badge) => '<div class="hd">' + badge + '<span class="sp"></span><button class="btn sm ghost" data-x>' + ic("x", 13) + " " + t("nbClose") + "</button></div>";
  const loading = q => showCard(head('<span class="spin"></span><b>' + t("thinking") + "</b>") + '<div class="q">' + esc(q) + '</div><div class="shimmer"></div><div class="shimmer" style="width:70%"></div>');
  async function askAI(q, label) {
    if (!cur || !q.trim()) return; loading(label || q);
    try {
      const d = await api("/api/ask", { video_id: cur.video_id, question: q, clip: false, level: "simple" });
      const tr = d.trace || {};
      if (!d.found) { cardData = null; showCard(head('<span class="badge bad">' + ic("x", 12) + " " + t("notFound") + "</span>") + '<div class="q">' + esc(label || q) + "</div><b>" + esc(t("notFoundMsg")) + "</b>"); return; }
      const a = d.answer, refAt = n => { const r = (d.refs || []).find(x => x.n === n); return r ? r.start : null; };
      let body = '<div class="q">' + esc(label || q) + "</div>";
      if (a) {
        body += "<h3>" + esc(a.title) + '</h3><p class="sum">' + esc(a.summary) + "</p>";
        a.sections.forEach(x => { body += (x.heading ? "<h4>" + esc(x.heading) + "</h4>" : "") + "<ul>" + x.points.map(p => "<li>" + esc(p.text) + " " + (p.cites || []).map(n => { const s0 = refAt(n); return s0 == null ? "" : chip(s0); }).join("") + "</li>").join("") + "</ul>"; });
      } else body += "<p>" + esc(d.note || "") + "</p>";
      body += '<div class="row" style="margin-top:6px">' + (d.segments || []).map(g => chip(g.start)).join("") + "</div>";
      cardData = { q: label || q, a, refs: d.refs || [], segs: d.segments || [] };
      showCard(head(tr.verify === "ok" ? '<span class="badge ok">' + ic("check", 12) + " " + tr.claims_supported + "/" + tr.claims_total + " " + t("verified") + "</span>" : '<span class="badge warn">' + ic("alert", 12) + " " + t("unverified") + "</span>") + body +
        '<div class="acts"><button class="btn pri sm" data-place>' + ic("book", 13) + " " + t("nbPlace") + "</button></div>");
    } catch (e) { showCard(head('<span class="badge bad">' + t("error") + "</span>") + esc(tMsg(e.message))); }
  }
  async function explainAt(sec, label) {
    if (!cur) return; loading(label);
    try {
      const d = await api("/api/explain", { video_id: cur.video_id, current_time: Math.max(sec + 45, 30), style: "simple" });
      cardData = { q: label, text: d.explanation, at: d.passage.start };
      showCard(head('<span class="badge">' + ic("sparkles", 12) + " " + t("nbExplain") + "</span>") + '<div class="q">' + esc(label) + " " + chip(d.passage.start) + '</div><p style="white-space:pre-wrap;margin:0;font-size:14px">' + esc(d.explanation) + "</p>" +
        '<div class="acts"><button class="btn pri sm" data-place>' + ic("book", 13) + " " + t("nbPlace") + "</button></div>");
    } catch (e) { showCard(head('<span class="badge bad">' + t("error") + "</span>") + esc(tMsg(e.message))); }
  }
  function place2nb() {
    if (!cardData) return; const tsn = s0 => '<a class="tsn" data-t="' + Math.floor(s0) + '">' + ic("play", 10) + " " + fmt(s0) + "</a>";
    let h = '<p class="nb-q"><i>' + esc(cardData.q) + "</i></p>";
    if (cardData.a) {
      const a = cardData.a, at = n => { const r = cardData.refs.find(x => x.n === n); return r ? r.start : null; };
      h += "<h3>" + esc(a.title) + "</h3><p>" + esc(a.summary) + "</p>";
      a.sections.forEach(x => { h += (x.heading ? "<p><b>" + esc(x.heading) + "</b></p>" : "") + "<ul>" + x.points.map(p => "<li>" + esc(p.text) + " " + (p.cites || []).map(n => { const s0 = at(n); return s0 == null ? "" : tsn(s0); }).join(" ") + "</li>").join("") + "</ul>"; });
    } else if (cardData.text) h += "<p>" + tsn(cardData.at) + " " + esc(cardData.text).replace(/\n/g, "<br>") + "</p>";
    const p0 = spot(); add({ type: "text", x: p0.x, y: p0.y, w: 760, html: h });
    CARD.classList.add("hide"); toast(t("nbPlaced"));
  }
  $("nbAskBtn").onclick = () => { const q = $("nbQ").value.trim(); if (!q) return; $("nbQ").value = ""; askAI(q); };
  $("nbQ").onkeydown = e => { if (e.key === "Enter") $("nbAskBtn").click(); };
  $("nbExplain").onmousedown = e => e.preventDefault();          // keep the text selection alive
  $("nbExplain").onclick = () => {
    if (selText) { const q = selText.slice(0, 400); return askAI((LANG === "en" ? "Explain this, using the video: " : "ভিডিও থেকে এটা বুঝিয়ে দাও: ") + '"' + q + '"', "“" + q.slice(0, 120) + (q.length > 120 ? "…" : "") + "”"); }
    const it = sel && items.find(i => i.id === sel.dataset.id);
    if (it && it.type === "ts") return explainAt(it.t, t("nbAboutAt") + " " + fmt(it.t));
    if (it && it.type === "img") { const m = /data-t="(\d+)"/.exec(it.cap || ""); if (m) return explainAt(+m[1], t("nbAboutAt") + " " + fmt(+m[1])); }
    toast(t("nbExplainHint"));
  };
  /* ---------- AI notes: study notes / mind map / flashcards made from the video, quiz from MY notes ---------- */
  const tsn = s0 => s0 == null ? "" : '<a class="tsn" data-t="' + Math.floor(s0) + '">' + ic("play", 10) + " " + fmt(s0) + "</a>";
  function notesText() {
    const d = document.createElement("div");
    return items.filter(i => i.type === "text").map(i => { d.innerHTML = i.html || ""; return d.textContent; }).join(" ").replace(/\s+/g, " ").trim();
  }
  async function aiNotes(kind) {
    if (!cur) return;
    if (kind === "quiz") return quizFromNotes();
    loading(t("nbAI_" + kind));
    try {
      const d = await api("/api/notes_ai", { video_id: cur.video_id, kind });
      const p0 = spot();
      if (kind === "summary") {
        let h = "<h3>" + esc(d.title || cur.title || "") + "</h3>";
        d.sections.forEach(x => { h += (x.heading ? "<p><b>" + esc(x.heading) + "</b></p>" : "") + "<ul>" + x.points.map(p => "<li>" + esc(p.text) + " " + tsn(p.start) + "</li>").join("") + "</ul>"; });
        add({ type: "text", x: p0.x, y: p0.y, w: 900, html: h });
      }
      if (kind === "mindmap") add({ type: "img", x: p0.x, y: p0.y, w: 900, src: mindMapSvg(d), cap: "" });
      if (kind === "roadmap") add({ type: "img", x: p0.x, y: p0.y, w: 900, src: roadmapSvg(d),
        cap: d.steps.filter(s => s.start != null).map((s, i) => '<a class="tsn" data-t="' + Math.floor(s.start) + '">' + ic("play", 10) + " " + (i + 1) + "</a>").join(" ") });
      if (kind === "flashcards") {
        let h = "<h3>" + esc(t("nbAI_flashcards")) + "</h3><ul>" + d.cards.map(c => "<li><b>" + esc(c.front) + "</b><br>" + esc(c.back) + " " + tsn(c.start) + "</li>").join("") + "</ul>";
        add({ type: "text", x: p0.x, y: p0.y, w: 900, html: h });
        if (me.user) { try { const r = await api("/api/cards", { video_id: cur.video_id, cards: d.cards }); toast(t("cardsAdded", { n: r.added })); } catch (e) { toast(tMsg(e.message)); } }
        else toast(t("cardsLogin"));
      }
      CARD.classList.add("hide"); if (kind !== "flashcards") toast(t("nbPlaced"));
    } catch (e) { showCard(head('<span class="badge bad">' + t("error") + "</span>") + esc(tMsg(e.message))); }
  }
  // mind map as an SVG picture: center bubble, branches around it, children listed under each branch
  function mindMapSvg(d) {
    const W = 1200, br = d.branches, n = br.length, rows = Math.ceil(n / 2), rowH = 90 + 34 * Math.max(...br.map(b => b.children.length), 1);
    const H = Math.max(520, rows * rowH + 120), cx = W / 2, cy = H / 2, x = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const cols = ["#7c5cff", "#22d3ee", "#f43f5e", "#22c55e", "#f59e0b", "#a855f7", "#0ea5e9"];
    let g = "";
    br.forEach((b, i) => {
      const left = i % 2 === 0, r = Math.floor(i / 2), bx = left ? 40 : W - 360, by = 60 + r * rowH, col = cols[i % cols.length];
      g += '<path d="M' + cx + " " + cy + " C " + (left ? cx - 160 : cx + 160) + " " + cy + ", " + (left ? bx + 420 : bx - 100) + " " + (by + 20) + ", " + (left ? bx + 320 : bx) + " " + (by + 20) + '" stroke="' + col + '" stroke-width="3" fill="none"/>';
      g += '<rect x="' + bx + '" y="' + by + '" width="320" height="40" rx="12" fill="' + col + '"/><text x="' + (bx + 160) + '" y="' + (by + 26) + '" fill="#fff" font-size="18" font-weight="700" text-anchor="middle">' + x(b.label.slice(0, 34)) + (b.start != null ? "  ▸" + fmt(b.start) : "") + "</text>";
      b.children.forEach((c, j) => { g += '<text x="' + (bx + 14) + '" y="' + (by + 66 + j * 30) + '" font-size="16" fill="#334155">• ' + x(c.label.slice(0, 40)) + (c.start != null ? "  (" + fmt(c.start) + ")" : "") + "</text>"; });
    });
    g += '<ellipse cx="' + cx + '" cy="' + cy + '" rx="170" ry="54" fill="#111827"/><text x="' + cx + '" y="' + (cy + 8) + '" fill="#fff" font-size="22" font-weight="800" text-anchor="middle">' + x(d.center.slice(0, 30)) + "</text>";
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '" font-family="Hind Siliguri, Noto Sans Bengali, Inter, sans-serif"><rect width="100%" height="100%" rx="18" fill="#f8fafc"/>' + g + "</svg>";
    return "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svg)));
  }
  let nq = [];
  async function quizFromNotes() {
    const txt = notesText();
    if (txt.length < 20) { toast(t("nbQuizEmpty")); return; }
    loading(t("nbAI_quiz"));
    try {
      const d = await api("/api/quiz", { video_id: cur.video_id, n: 5, topic: txt.slice(0, 600) });
      nq = d.questions || []; if (!nq.length) throw new Error(t("quizFail"));
      nq.score = 0; nq.done = 0;
      showCard(head('<span class="badge">' + ic("sparkles", 12) + " " + t("nbAI_quiz") + "</span>") + '<div id="nqScore" class="q"></div>' +
        nq.map((q, i) => '<div style="margin:10px 0"><b>' + (i + 1) + ". " + esc(q.q) + "</b>" + q.options.map((o, j) => '<button class="btn sm ghost nqo" style="display:block;width:100%;text-align:left;margin-top:4px" data-i="' + i + '" data-j="' + j + '">' + esc(o) + "</button>").join("") + '<div class="q" id="nqf' + i + '"></div></div>').join(""));
      CARD.querySelectorAll(".nqo").forEach(b => b.onclick = () => {
        const q = nq[+b.dataset.i]; if (q.picked != null) return; q.picked = +b.dataset.j; nq.done++;
        const ok = q.picked === q.answer; if (ok) nq.score++;
        CARD.querySelectorAll('.nqo[data-i="' + b.dataset.i + '"]').forEach((x, j) => { if (j === q.answer) x.style.borderColor = "var(--ok)"; });
        if (!ok) b.style.borderColor = "var(--bad)";
        $("nqf" + b.dataset.i).innerHTML = (ok ? "✓ " : "✗ ") + esc(q.explanation) + " " + tsn(q.start);
        $("nqf" + b.dataset.i).querySelectorAll(".tsn").forEach(a => a.onclick = () => seek(+a.dataset.t));
        $("nqScore").textContent = t("score") + ": " + nq.score + " / " + nq.length;
        if (nq.done === nq.length && me.user) api("/api/quiz_result", { video_id: cur.video_id, score: nq.score, total: nq.length }).catch(() => {});
      });
    } catch (e) { showCard(head('<span class="badge bad">' + t("error") + "</span>") + esc(tMsg(e.message))); }
  }
  async function shareLink() {
    if (!cur) return;
    if (!me.user) { toast(t("shareLogin")); return; }
    if (saveT) { clearTimeout(saveT); saveT = null; await save(nbVid); }
    try {
      const d = await api("/api/notes/" + cur.video_id + "/share", {});
      const url = (window.nbBase ? window.nbBase() : location.origin) + d.url;
      try { await navigator.clipboard.writeText(url); toast(t("shareCopied")); } catch (_) { prompt(t("shareCopied"), url); }
    } catch (e) { toast(tMsg(e.message)); }
  }
  // voice question: browser speech recognition (Chrome / Edge / Android); Bangla or English by UI language
  function wireMic(btn, input, send) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { btn.classList.add("hide"); return; }
    let rec = null;
    const micLang = () => { try { return localStorage.getItem("lm_mic") || (window.LANG === "bn" ? "bn-BD" : "en-US"); } catch (_) { return "en-US"; } };
    const chip = document.createElement("button"); chip.type = "button"; chip.className = "miclang"; chip.title = t("micLangT");
    const paintChip = () => { chip.textContent = micLang() === "bn-BD" ? "বাং" : "EN"; };
    chip.onclick = e => { e.preventDefault(); try { localStorage.setItem("lm_mic", micLang() === "bn-BD" ? "en-US" : "bn-BD"); } catch (_) {} paintChip(); toast(t(micLang() === "bn-BD" ? "micBn" : "micEn")); };
    paintChip(); btn.after(chip);
    btn.onclick = () => {
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = micLang(); rec.interimResults = true;
      btn.classList.add("rec"); const before = input.value;
      rec.onresult = e => { input.value = (before ? before + " " : "") + [...e.results].map(r => r[0].transcript).join(""); };
      rec.onerror = e => { if (e.error === "not-allowed" && window.onMicDenied) window.onMicDenied(); else toast(t(e.error === "not-allowed" ? "micDenied" : "micFail")); };
      rec.onend = () => { btn.classList.remove("rec"); rec = null; if (input.value.trim() && input.value !== before) send(); };
      rec.start();
    };
  }
  window.wireMic = wireMic;

  /* ---------- save / load (account when logged in, else this browser) ---------- */
  /* the notebook owns the id of the video it belongs to: a pending save always goes to THAT video,
     and switching videos first flushes it (no more wiping another video's notes) */
  let nbVid = null, nbTitle = "", loadGen = 0;
  function saveSoon() { $("nSave").textContent = t("saving"); clearTimeout(saveT); const v = nbVid; saveT = setTimeout(() => { saveT = null; save(v); }, 900); }
  async function save(vid) {
    vid = vid || nbVid; if (!vid || vid !== nbVid) return; inkImg = INK.width > 2 ? inkNow() : inkImg;
    const content = { v: 2, H, items: items.slice(), ink: inkImg, title: nbTitle };
    if (me.user) { try { await api("/api/notes/" + vid, undefined, { method: "PUT", body: { content } }); if (vid === nbVid) $("nSave").innerHTML = ic("check", 12) + " " + t("saved"); } catch (e) { if (vid === nbVid) $("nSave").textContent = e.message; } }
    else { try { localStorage.setItem("notes_" + vid, JSON.stringify(content)); if (vid === nbVid) $("nSave").innerHTML = ic("check", 12) + " " + t("savedLocal"); } catch (e) { $("nSave").textContent = t("tooBig"); } }
  }
  window.loadNotes = async function () {
    if (saveT) { clearTimeout(saveT); saveT = null; save(nbVid); }          // flush the previous video's last edit
    const vid = cur.video_id, gen = ++loadGen; nbVid = vid; nbTitle = cur.title || "";
    items = []; H = 1600; inkImg = null; inkHist = []; inkRedo = []; lastClick = null; $("nSave").textContent = ""; let c = null;
    renderAll(); paintInk(null);
    if (me.user) { try { c = (await api("/api/notes/" + vid)).content; } catch (e) {} }
    else { try { c = JSON.parse(localStorage.getItem("notes_" + vid) || "null"); } catch (e) {} }
    if (gen !== loadGen) return;                                              // another video was opened meanwhile
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
    renderAll(); paintInk(inkImg); setTool("type"); CARD.classList.add("hide"); selText = ""; explainState();
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
  window.nbRelayout = () => { if (!$("p_notes").classList.contains("hide") && PAGE.clientWidth > 0) layout(); };
  // the panel can change width without a window resize (drag the divider, open a tab): keep page + ink canvas in sync,
  // otherwise the ink canvas stays at the old width and the right side can't be drawn on
  if (window.ResizeObserver) { let rq = 0; new ResizeObserver(() => { cancelAnimationFrame(rq); rq = requestAnimationFrame(window.nbRelayout); }).observe(PAGE); }
  addEventListener("resize", window.nbRelayout);

  /* "Add to notes" from an answer */
  window.answerToNotes = function (q, d) {
    const a = d.answer; let h = "<h3>" + esc(a ? a.title : q) + "</h3><p><i>" + esc(q) + "</i></p>" + (a ? "<p>" + esc(a.summary) + "</p>" : "");
    if (a) a.sections.forEach(s => { h += "<p><b>" + esc(s.heading) + "</b></p><ul>" + s.points.map(p => "<li>" + esc(p.text) + " " + (p.cites || []).map(n => { const r = d.refs.find(x => x.n === n); return r ? "(" + fmt(r.start) + ")" : ""; }).join(" ") + "</li>").join("") + "</ul>"; });
    window.openNotes(); setTimeout(() => { const p = spot(); add({ type: "text", x: p.x, y: p.y, w: 760, html: h }); toast(t("addedToNotes")); }, 30);
  };
  window.nbTimestamp = addTs; window.nbSnap = snap;

  /* ---------- PDF: exactly what you see (text + ink + screenshots), plus clickable timestamp list ---------- */
  const loadJs = src => new Promise((ok, no) => { if (document.querySelector('script[src="' + src + '"]')) return ok(); const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });
  async function exportPdf() {
    if (!cur) return; toast(t("pdfWorking")); select(null);
    try {
      const libs = window.nbLibs || {};       // the Chrome extension ships its own copies (it may not load scripts from the web)
      await loadJs(libs.h2c || "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js");
      await loadJs(libs.pdf || "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js");
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
