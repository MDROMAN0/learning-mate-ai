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

window.nbBase = base;                    // share links point at the server, not at the extension
// voice questions: the side panel cannot show Chrome's microphone prompt, so ask once in a normal tab
window.onMicDenied = () => { chrome.tabs.create({ url: chrome.runtime.getURL("mic.html") }); toast(t("micPerm")); };
wireMic($("qMic"), $("q"), () => $("ask").click());
$("docFile").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) uploadDoc(f); };
$("docExit").onclick = exitDoc;
