# Live demo (presentation) — তোমার PC-তে, আসল YouTube-এ

## কেন PC
Cloud server-এর IP-কে YouTube block করে; **তোমার বাসা/hotspot-এর IP** সাধারণত করে না। তাই "যেকোনো YouTube URL দাও → live কাজ করে" দেখাতে হলে app **তোমার laptop-এ** চালাতে হবে। Host করা Render version শুধু public link/backup।

## চালানোর সবচেয়ে সহজ উপায়
**`start.bat`-এ double-click** (প্রথমবার venv বানিয়ে package install করে; পরে সরাসরি চালু হয়ে browser খোলে)। অথবা `python run.py`। প্রথমবার `.env` না থাকলে বানিয়ে দেয়, তুমি `LLM_API_KEY` বসাও।

## Public link লাগলে — তোমার PC থেকেই (free, account ছাড়া)
Sir/বন্ধুকে link দিতে চাইলে host করার দরকার নেই; PC-র app-কেই Cloudflare Quick Tunnel দিয়ে ইন্টারনেটে দাও। App তোমার PC-তে চলে বলে তোমার IP-তে YouTube কাজ করে।
```
winget install Cloudflare.cloudflared
start_share.bat        # (অথবা: python run.py --share) — app + tunnel একসাথে; link terminal-এ [tunnel] লাইনে দেখা যায়
```
`--share` `.env`-এ `APP_PASSWORD` না থাকলে চলতেই দেয় না (ইচ্ছাকৃত নিরাপত্তা)।
- Account লাগে না, URL random, `Ctrl-C` দিলে বন্ধ; PC চালু ও internet থাকতে হবে।
- URL আসলে public — **`.env`-এ `APP_PASSWORD` দাও**, নইলে যে পায় সে তোমার LLM quota পোড়াবে।
- Extension-এ Backend URL হিসেবে এই link বসাও (manifest-এ `*.trycloudflare.com` অনুমতি আছে)।
- (Cloudflare-এর doc/গাইড অনুযায়ী, Sep 2026।)

## দুটো live পথ
**A) Chrome extension (সবচেয়ে ভালো "user সফটওয়্যার দিয়ে YouTube দেখছে" দৃশ্য)**
Laptop-এ backend চলছে (`uvicorn app:app`), Chrome-এ আসল YouTube video খোলা, side panel থেকে index → প্রশ্ন → উত্তরের timestamp চাপলে player সেখানে লাফ দেয়। Caption আনে *তোমার browser* থেকে, `yt-dlp` লাগে না।
**B) Web app (`localhost:8000`)** — URL paste → index → ask। Caption + (চাইলে) video download। উত্তরের segment YouTube embed (`start/end`) বা clip file হিসেবে চলে।

## ২০২৬-এর নতুন ঝুঁকি: yt-dlp-র Deno
YouTube download করতে yt-dlp-র এখন একটা external JavaScript runtime (Deno) + `yt-dlp-ejs` লাগে (yt-dlp-র announcement, Nov 2025); না থাকলে "Sign in to confirm you're not a bot" বা format missing হয়। তাই:
```
pip install -U "yt-dlp[default]"
winget install DenoLand.Deno      # terminal নতুন করে খোলো
winget install ffmpeg
```
তবু না হলে `.env`-এ **`YT_DOWNLOAD=0`** — তখন download বন্ধ, caption + embedded YouTube player-এ segment দেখায় (clip file থাকে না, বাকি সব থাকে)। শেষ উপায়: `YT_COOKIES_FROM_BROWSER=chrome` (তোমার logged-in cookie ব্যবহার করে — ঐ account-এর ঝুঁকি আছে, একটা আলাদা account ভালো)।

## Demo-র আগের দিন (checklist)
1. `python doctor.py` → **READY** না আসা পর্যন্ত ঠিক করো (কী ঠিক করতে হবে ও লিখে দেয়)।
2. ২–৩টা video `python prepare.py <url>` দিয়ে আগে index করো — **তোমার নিরাপত্তা জাল** (library-তে থাকলে live না চললেও দেখানো যায়)।
3. Live-এর জন্য একটা video আগেই বেছে রাখো: caption আছে, ৫–১৫ মিনিট, ২–৩টা স্পষ্ট topic। **ঐ video দিয়ে পুরো flow একবার রিহার্সাল করো ও index হতে কত সময় লাগে মেপে রাখো।**
4. `eval` চালিয়ে সংখ্যা তৈরি রাখো (`docs/EVALUATION.md`)।
5. Mobile hotspot প্রস্তুত রাখো (institute network YouTube-এ সমস্যা করলে)।
6. LLM/embedding API-র free-tier quota demo-র দিন সকালে দেখে নাও; বাড়তি key/model পাশে রাখো।
7. Browser-এ অন্য tab বন্ধ; extension "Load unpacked" করা; Backend URL `http://localhost:8000`।

## Run of show (~৮ মিনিট)
1. Extension খুলে YouTube video-তে "index করো" → (index চলার সময় ১ লাইনে architecture বলো)।
2. Banglish প্রশ্ন → উত্তর + timestamp chip চাপো।
3. Video মাঝপথে থামিয়ে **spoiler-free** → ভবিষ্যতের topic "নেই"।
4. না-থাকা topic → "নেই" (hallucination না)।
5. `/lab` → full pipeline → প্রতিটা stage দেখাও (এটাই sir-এর কেন্দ্র)।
6. Alternatives / Watch plan (library-র video-তে)।
7. Evaluation table।

## কিছু ভাঙলে (failure playbook)
| সমস্যা | করো |
|---|---|
| Index-এ download error | `YT_DOWNLOAD=0`, server restart |
| Caption আসছে না (extension/web) | hotspot; নইলে library-র backup video |
| "Sign in to confirm you're not a bot" | Deno/yt-dlp update; `YT_DOWNLOAD=0` |
| LLM 429/quota | অন্য key/model (`LLM_MODEL`, `LLM_BASE_URL`) |
| Extension ভাঙল | web app (`localhost:8000`) |
| সব ভাঙল | library video + `/lab` — পুরো RAG তবু দেখানো যায় |

## সৎ সীমা
Presentation-এর আগে একবার পুরো live পথ (index → ask → timestamp) PC-তে রিহার্সাল করে নাও; `python doctor.py` সব ঠিক আছে কিনা দেখায়।
