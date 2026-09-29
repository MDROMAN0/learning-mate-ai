# তোমার (Roman-এর) কাজ — শুধু যেগুলো তুমি ছাড়া হয় না

বাকি সব Cowork করবে (`HANDOFF.md`)। নিচেরগুলো **তুমি** করবে, কারণ এখানে account/login/key/password লাগে। Key কখনো chat-এ paste করবে না।

## ১. একবারের কাজ (Chrome + terminal)
1. **Chrome-এ** https://aistudio.google.com/apikey → Google login (তোমার) → **Create API key** → copy।
2. Project ফোল্ডারে terminal খুলে: `python setup_keys.py` → key paste করো (স্ক্রিনে দেখা যাবে না) → Enter।
3. (ঐচ্ছিক, Bangla ASR) https://dashboard.sarvam.ai → account/key → একই `setup_keys.py`-এ paste।
4. `APP_PASSWORD`: `setup_keys.py` প্রশ্ন করলে Enter দাও, নিজে বানিয়ে দেবে — **সেভ করে রাখো** (website-এ "App key" ঘরে লাগবে)।
5. `python doctor.py` → **READY**।

## ২. Public link / host চাইলে (পরে)
- GitHub: login তোমার (repo push Cowork করবে)।
- Render (render.com): sign up/login তোমার; Blueprint deploy Cowork করবে; **Secrets (`LLM_API_KEY`, `SARVAM_API_KEY`, `APP_PASSWORD`) Render dashboard-এ তুমি বসাবে**।
- `start_share.bat` (Cloudflare tunnel) চাইলে: `winget install Cloudflare.cloudflared` Cowork করবে; `APP_PASSWORD` থাকতে হবে।

## ৩. Demo-র দিন Chrome-এ খুলে রাখবে (tab list)
1. `http://localhost:8000` (app) · 2. `http://localhost:8000/lab` (RAG Lab)
3. আগে বাছা YouTube video (caption আছে) · 4. `chrome://extensions` (extension Load unpacked করা, side panel প্রস্তুত)
5. https://aistudio.google.com (quota/usage দেখতে) · 6. (host হলে) Render dashboard, GitHub repo
সব login আগে থেকে করা থাকুক; presentation-এর মাঝে password টাইপ করতে হলে সময় নষ্ট।

## নিয়ম
- Key/password/ব্যক্তিগত কিছু **chat-এ বা Cowork-এর prompt-এ লিখবে না** — `setup_keys.py` বা Render dashboard।
- Cowork কোথাও account/login/key/payment-এ আটকে গেলে থামবে ও তোমাকে বলবে; তুমি করে দিলে সে এগোবে।
- Free-tier-এ দেওয়া text Google উন্নয়নে ব্যবহার করতে পারে → ব্যক্তিগত/গোপন video-transcript দিও না।
