# GUIDE — Vani.ai protocol notes

## Auth architecture

- Frontend: Next.js on `c.vani.ai`, auth = **Supabase** (project `bfwynudfpppahxozcexw`)
- Session cookie: `sb-bfwynudfpppahxozcexw-auth-token` (httpOnly) — value = JSON
  `{access_token (JWT), refresh_token, user{...}}` with `base64-` prefix (Supabase JS format)
- JWT contains: email, sub (user id), aud=authenticated. TTL 3600s, refresh via refresh_token
- **API Platform** (`platform.vani.ai`) is a SEPARATE account from Chat — but API keys live in
  Chat settings: `c.vani.ai/settings/developer`
- Registration = login. New account created automatically on email verification (magic link)

## Login form

- `POST` via React server action (no classic form action URL) — fields: `email`, `next`,
  hidden `turnstile_token`
- **Cloudflare Turnstile** (invisible, `response-field:false`): sitekey `0x4AAAAAAFM_3cPV7Jg5kRlB`,
  action `signup`. Renders after page load; token lands in `input[name=turnstile_token]`
- Headless Chromium (Playwright default) = "Complete the security check" wall.
  **camoufox (Firefox stealth) passes invisibly** — token appears in 3-10s, no solve service needed
- Server action response: Next.js RSC flight payload (not JSON). Key creation result must be
  scraped from DOM modal text: regex `vani_[a-f0-9]{40,80}`

## API keys

- Settings → Developer → Create key (name + expiry: 30/60/90d/No expiry)
- Max 10 active keys per account
- Full key shown ONCE in modal ("Copy your key now")
- Format: `vani_` + 64 hex
- Keys count against plan allowance (shared with chat) — no separate API balance

## api.vani.ai

```
GET  /v1/models                      -> 47 models (OpenRouter-style ids: vendor/model)
POST /v1/chat/completions            -> OpenAI-compatible (stream + non-stream)
POST /v1/responses                   -> Responses API also supported (per settings page)
Anthropic: origin https://api.vani.ai, x-api-key header, client appends /v1/messages
```

Errors:
- `429 concurrency_limit` — free plan = 1 concurrent generation. Slot frees ~30-60s after finish.
- `402 usage_limit_exceeded` — billing-period allowance gone
- `429 weekly_limit_reached` — weekly window
- `401 invalid_token` — bad/revoked key

Model ids (all 47): zhipu/glm-5.3(-derisked,-flash), anthropic/claude-opus-5.5, opus-5,
opus-4.8/4.7/4.6, fable-5.1/5, sonnet-5.5/5/4.6, haiku-4.5, openai/gpt-6.1-sol, gpt-6-sol,
gpt-6-astra, gpt-6-luna, gpt-5.6-sol/terra/luna, gpt-5.5 (+ *-fast variants),
x-ai/grok-4.7/4.6/4.5, google/gemini-3.1-pro, gemini-3.8-flash, moonshotai/kimi-k3,
k2.8-preview, k2.7-code, minimax/minimax-m3, meta/muse-spark-1.3, xiaomi/mimo-v2.5,
mimo-v2.6-flash/pro, deepseek/deepseek-v4.1-flash, qwen/qwen3.8-flash/max, tencent/hy4-preview
Context: up to 1,048,576 (kimi-k3), 1,050,000 (gpt-5.6-sol), max_completion 128-131K

## Guest API (no account!)

```
POST https://c.vani.ai/api/public/chat   {"model":"openai/gpt-6.1-sol","messages":[...]}
  -> SSE: message.start / content.delta{text} / usage{tokens} / message.complete
GET  https://c.vani.ai/api/public/usage  -> allowance_micro=1000000 per IP
```
3 guest models: gpt-6.1-sol, gpt-6-luna, zhipu/glm-5.3-derisked. Works from bare curl
(no TLS fingerprint check, unlike Notion).

## Autoreg pitfalls (learned the hard way)

1. `msg.get_date()` doesn't exist — use `msg.get("Date")` (imaplib Message)
2. Turnstile token NOT in initial HTML sitekey props — RSC payload only; wait for the hidden
   input to fill instead of parsing HTML
3. Magic link is `https://c.vani.ai/api/auth/...` OR contains `token_hash` — regex both
4. Gmail search by SINCE date only; filter by "vani" in From/Subject
5. Concurrency slot: a killed/timed-out request can leave the slot busy for minutes —
   pool gateway rotates keys instead of blocking
6. Cookie value from `page.context.cookies()` includes `base64-` prefix — keep as-is for
   reinjection; for manual Supabase use decode URL-safe b64 (fix padding)
