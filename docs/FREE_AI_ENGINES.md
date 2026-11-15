# Free AI engines (no paid plan, ৳0)

Learning Mate AI can use several **free** AI services at once. When one reaches its free limit (or fails),
the next one answers by itself, so students never hit a wall. Short "judge" jobs (understanding the
question, checking relevance, verifying the answer) go to a fast engine first, which keeps the main
engine's free quota for real answers. Repeated questions are answered instantly from a cache.

## Add engines (website → **AI engines**)
| Engine | Free key | Notes |
|---|---|---|
| Google Gemini | https://aistudio.google.com/apikey | free tier, limits per model |
| Groq | https://console.groq.com/keys | ~30 req/min, ~1,000 req/day per model; used first for small jobs |
| Mistral | https://console.mistral.ai/api-keys | free "Experiment" plan (lets Mistral train on your data) |
| OpenRouter | https://openrouter.ai/keys | only the `:free` models, ~50 req/day |
| NVIDIA NIM | https://build.nvidia.com | free for prototyping |
| Cloudflare Workers AI | https://dash.cloudflare.com/profile/api-tokens | needs Account ID too; 10,000 neurons/day |
| **My PC (Ollama)** | none | open-source, no limit |

No card is needed for any of them. Free limits change; each card in the panel has a **Test** button.

Who can change keys: the person running the site on this PC (localhost), anyone with `APP_PASSWORD`,
the emails in `ADMIN_EMAILS`, or — if that is not set — the first account made on the site.
Keys are stored in the app database (encrypted with `SECRET_KEY`) and never shown again in full.

## Your own PC as an engine (Ollama, open-source, unlimited)
1. Install Ollama: https://ollama.com/download
2. Download models once:
   ```
   ollama pull qwen2.5:7b
   ollama pull qwen2.5:3b
   ollama pull bge-m3
   ```
3. **Site on this PC (localhost):** AI engines → "My PC (Ollama)" → URL `http://localhost:11434/v1` → tick *Use this engine* → Save → Test.
4. **Online site (Render):** put the same `DATABASE_URL` as Render in this PC's `.env`, install the free
   `cloudflared`, then double-click `start_pc_server.bat` and keep the window open. While the PC is on, the
   online site uses it; when it is off, the site falls back to the free APIs automatically.

The 7B model needs about 8 GB RAM; a GPU makes it much faster.
