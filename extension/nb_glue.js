// Connects the website's notebook (lib/notebook.js) to the side panel: video time, screenshots, PDF libraries.
window.nbLibs = { h2c: "lib/html2canvas.min.js", pdf: "lib/jspdf.umd.min.js" };
window.nbGrab = async () => { const r = await inPage(pageShot); return r && !r.error ? r : null; };
window.openNotes = () => showTab("notes");
applyIcons();

async function openNotebook() {
  if (!cur) return;
  if (nbLoadedFor !== cur.video_id) { nbLoadedFor = cur.video_id; await window.loadNotes(); }
  setTimeout(() => window.nbRelayout(), 0);
}
// keep the video time fresh while the notebook is open (timestamps and "explain this" use it)
setInterval(async () => {
  if (tabId == null || $("p_notes").classList.contains("hide")) return;
  try { lastTime = (await inPage(pageSeek, [null])) || lastTime; } catch (_) {}
}, 1000);
