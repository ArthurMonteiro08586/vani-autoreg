# vani-autoreg — Vani.ai account farm + OpenAI-compatible API access

Reverse-engineered automation for [vani.ai](https://vani.ai): mass account
registration and official API key harvesting. **47 frontier models**
(Claude Opus 5.5, GPT-6.1 Sol, Gemini 3.1 Pro, Grok 4.7, Kimi K3, GLM 5.3...)
through a stock OpenAI API — no card, no waitlist.

## What's inside

| File | Purpose |
|------|---------|
| `vani_autoreg.py` | Full reg pipeline: camoufox + Gmail alias + invisible Turnstile + IMAP magic link + auto API-key creation |
| `pool_gateway.py` | OpenAI-compatible pool gateway over N harvested `vani_` keys (rotates on concurrency limit) |
| `GUIDE.md` | Protocol notes, pitfalls, API docs |

## The flow (per account, ~90s)

1. `camoufox` opens `c.vani.ai/login` (Firefox-based stealth, passes invisible Turnstile)
2. Wait for `input[name=turnstile_token]` to fill (invisible challenge, ~3-10s)
3. Submit Gmail **alias** (`base+vaniN@gmail.com`) → magic link/code sent
4. IMAP poll → open verify link → Supabase session cookie `sb-bfwynudfpppahxozcexw-auth-token`
5. `/settings/developer` → Create key → No expiry → scrape `vani_...` (shown once, regex from DOM)
6. Append JSONL record: `{alias, cookie, api_key, status}`

## API

```
Base URL: https://api.vani.ai/v1        (OpenAI-compatible: /chat/completions, /models)
Anthropic SDK origin: https://api.vani.ai  (x-api-key header)
Auth: Authorization: Bearer vani_...
```

- Free plan: 1,000,000 micro-units allowance (chat+API shared), concurrency=1
- 402 `usage_limit_exceeded`, 429 `weekly_limit_reached`, 429 `concurrency_limit`
- N accounts = N parallel slots → `pool_gateway.py` rotates keys on 429

## Run

```bash
# deps: pip install camoufox httpx fastapi uvicorn && camoufox fetch
python vani_autoreg.py 10          # register 10 accounts
python pool_gateway.py             # serve pool on :3300 (OpenAI-compatible)
```

Secrets (`imap_pass.txt`, `*.jsonl`, keys) are gitignored. Bring your own Gmail app password.

## Verified

- reg pipeline: `registered key=YES` on first try after fixes
- new account key → `/v1/models` = 47 models → chat completion `NEWACC_OK` (glm-5.3)
- Turnstile sitekey `0x4AAAAAAFM_3cPV7Jg5kRlB` (action=signup) solved invisibly by camoufox
