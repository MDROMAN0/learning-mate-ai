/* Learning Mate AI — "AI engines" panel: free API keys + your own PC (Ollama), in the order they are tried.
   Depends on globals from index.html: $, t, ic, esc, api, toast, LANG. */
(function () {
  let data = null, dirty = {}, order = [];
  window.loadEngines = async function () {
    const box = $("engOut");
    box.innerHTML = '<div class="shimmer"></div><div class="shimmer" style="width:70%"></div>';
    try { data = await api("/api/engines"); order = data.engines.map(e => e.id); dirty = {}; draw(); }
    catch (e) { box.innerHTML = '<div class="empty">' + esc(e.message) + "</div>"; }
  };
  const byId = id => data.engines.find(e => e.id === id);
  function status(e) {
    if (!e.enabled) return '<span class="badge">' + t("engOff") + "</span>";
    if (!e.ready) return '<span class="badge warn">' + t("engNeedKey") + "</span>";
    if (e.last && !e.last.ok) return '<span class="badge bad">' + ic("x", 11) + " " + esc(e.last.error || t("engFail")) + "</span>";
    if (e.last && e.last.ok) return '<span class="badge ok">' + ic("check", 11) + " " + t("engOk") + (e.last.ms ? " · " + (e.last.ms / 1000).toFixed(1) + "s" : "") + "</span>";
    return '<span class="badge ok">' + t("engOn") + "</span>";
  }
  // today's use of one engine on this site: answered calls, failures, and "limit reached - back in Xs" from the 429s
  function useLine(u) {
    if (!u) return '<div class="euse muted">' + t("engUseNone") + "</div>";
    const wait = u.until > 0 ? '<span class="badge warn">' + ic("clock", 11) + " " + t("engLimited", { s: u.until > 90 ? Math.round(u.until / 60) + " min" : u.until + "s" }) + "</span>" : '<span class="badge ok">' + ic("check", 11) + " " + t("engReady") + "</span>";
    return '<div class="euse">' + ic("chart", 12) + " " + t("engToday", { ok: u.ok, fail: u.fail }) + " " + wait + "</div>";
  }
  function card(e, i) {
    const a = data.admin, d = dirty[e.id] || {};
    const on = d.enabled ?? e.enabled;
    let h = '<div class="eng' + (on ? " on" : "") + '" data-id="' + e.id + '">' +
      '<div class="eh"><span class="enum">' + (i + 1) + '</span><div style="flex:1;min-width:0"><b>' + esc(e.name) + "</b>" +
      (e.local ? ' <span class="badge">' + ic("shield", 11) + " open-source</span>" : ' <span class="badge">' + t("engFree") + "</span>") +
      (e.fast_first ? ' <span class="badge" title="' + esc(t("engFastTip")) + '">' + ic("zap", 11) + " " + t("engFast") + "</span>" : "") +
      '<div class="muted" style="font-size:12.5px">' + esc(e.limits) + "</div>" + (e.enabled ? useLine(e.usage) : "") + "</div>" + status(e) + "</div>";
    if (a) {
      h += '<div class="ebody">' +
        '<label class="tog"><input type="checkbox" data-f="enabled"' + (on ? " checked" : "") + "> " + t("engUse") + "</label>";
      if (!e.local) h += '<div class="erow"><input class="in" type="password" autocomplete="off" data-f="key" placeholder="' +
        esc(e.has_key ? t("engKeySaved") + " " + e.key_hint : t("engKeyPh")) + '" aria-label="API key"><a class="btn sm ghost" target="_blank" rel="noopener" href="' + esc(e.key_url) + '">' +
        ic("external", 12) + " " + t("engGetKey") + "</a></div>";
      if (e.needs_account) h += '<input class="in" data-f="account" placeholder="Cloudflare Account ID" aria-label="Account ID" value="' + esc(d.account ?? e.account) + '">';
      if (e.local) h += '<input class="in" data-f="base" aria-label="Ollama URL" value="' + esc(d.base ?? (e.base || e.default_base)) + '">';
      h += '<details><summary>' + t("engModels") + '</summary><div class="erow"><label>' + t("engMain") + '<input class="in" data-f="model" value="' + esc(d.model ?? e.model) + '"></label>' +
        '<label>' + t("engSmall") + '<input class="in" data-f="fast" value="' + esc(d.fast ?? e.fast) + '"></label></div></details>' +
        '<div class="row" style="gap:6px;flex-wrap:wrap"><button class="btn sm" type="button" data-a="test">' + ic("zap", 13) + " " + t("engTest") + "</button>" +
        (e.has_key ? '<button class="btn sm ghost" type="button" data-a="clear">' + ic("trash", 13) + " " + t("engClear") + "</button>" : "") +
        '<span style="flex:1"></span><button class="btn sm ghost" type="button" data-a="up" aria-label="Move up"' + (i ? "" : " disabled") + ">↑</button>" +
        '<button class="btn sm ghost" type="button" data-a="down" aria-label="Move down"' + (i < order.length - 1 ? "" : " disabled") + ">↓</button></div>" +
        '<div class="etest muted" id="et_' + e.id + '"></div>';
      if (e.local) h += '<details class="howto"><summary>' + ic("help", 13) + " " + t("engHowPC") + "</summary>" + t("engHowPCBody") + "</details>";
      h += "</div>";
    }
    return h + "</div>";
  }
  function draw() {
    const live = order.map(byId).filter(e => (dirty[e.id]?.enabled ?? e.enabled) && e.ready);
    let h = '<div class="card soft" style="margin-bottom:14px"><b>' + ic("layers", 15) + " " + t("engChain") + "</b>" +
      '<div class="chain">' + (data.env_engine ? '<span class="badge">' + esc(".env" + (data.env_model ? " · " + data.env_model : "")) + "</span>" : "") +
      live.map(e => '<span class="badge ok">' + esc(e.name) + "</span>").join('<span class="muted">→</span>') +
      (!live.length && !data.env_engine ? '<span class="badge warn">' + t("engNone") + "</span>" : "") + "</div>" +
      (data.env_engine ? '<div style="margin-top:6px">' + useLine(data.env_usage).replace('class="euse', 'class="euse env') + "</div>" : "") +
      '<div class="muted" style="font-size:12.5px;margin-top:6px">' + t("engChainTip") + "</div></div>";
    if (!data.admin) h += '<div class="card" style="margin-bottom:14px"><span class="badge">' + ic("lock", 12) + " " + t("engReadOnly") + "</span></div>";
    h += '<div class="engs">' + order.map((id, i) => card(byId(id), i)).join("") + "</div>";
    if (data.admin) h += '<div class="row savebar"><span class="muted" id="engMsg"></span><span style="flex:1"></span><button class="btn pri" type="button" id="engSave">' + ic("check", 14) + " " + t("engSave") + "</button></div>";
    $("engOut").innerHTML = h;
    wire();
  }
  function wire() {
    document.querySelectorAll("#engOut .eng").forEach(el => {
      const id = el.dataset.id;
      el.querySelectorAll("[data-f]").forEach(inp => inp.oninput = inp.onchange = () => {
        const d = dirty[id] = dirty[id] || {};
        d[inp.dataset.f] = inp.type === "checkbox" ? inp.checked : inp.value;
        if (inp.dataset.f === "key" && inp.value.trim() && !("enabled" in d)) { d.enabled = true; el.querySelector('[data-f="enabled"]').checked = true; }
        el.classList.toggle("on", !!(d.enabled ?? byId(id).enabled)); msg(t("engUnsaved"));
      });
      el.querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
        const a = b.dataset.a, i = order.indexOf(id);
        if (a === "up" || a === "down") { const j = a === "up" ? i - 1 : i + 1; [order[i], order[j]] = [order[j], order[i]]; keepInputs(); draw(); msg(t("engUnsaved")); return; }
        if (a === "clear") { (dirty[id] = dirty[id] || {}).clear_key = true; await save(); return; }
        if (a === "test") {
          if (Object.keys(dirty).length) await save(true);
          const out = $("et_" + id); out.innerHTML = '<span class="spin"></span> ' + t("engTesting");
          try {
            const r = await api("/api/engines/" + id + "/test", {});
            out.innerHTML = ["model", "fast"].map(k => (r[k].ok ? '<span class="badge ok">' + ic("check", 11) : '<span class="badge bad">' + ic("x", 11)) + " " + t(k === "model" ? "engMain" : "engSmall") + "</span> " +
              (r[k].ok ? (r[k].ms / 1000).toFixed(1) + "s" : esc(r[k].error))).join("<br>");
            const d = await api("/api/engines"); data = d; draw(); $("et_" + id).innerHTML = out.innerHTML;
          } catch (e) { out.textContent = e.message; }
        }
      });
    });
    if ($("engSave")) $("engSave").onclick = () => save();
  }
  function keepInputs() {   // typed (unsaved) keys survive a re-draw
    document.querySelectorAll('#engOut [data-f="key"]').forEach(inp => { if (inp.value.trim()) (dirty[inp.closest(".eng").dataset.id] = dirty[inp.closest(".eng").dataset.id] || {}).key = inp.value; });
  }
  const msg = m => { if ($("engMsg")) $("engMsg").textContent = m; };
  async function save(quiet) {
    keepInputs();
    try {
      const r = await api("/api/engines", undefined, { method: "PUT", body: { order, providers: dirty } });
      data.engines = r.engines; dirty = {}; if (!quiet) { draw(); toast(t("engSaved")); }
    } catch (e) { msg(e.message); }
  }
})();
