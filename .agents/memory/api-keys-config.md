---
name: API keys & feature flags
description: Which env vars auto-enable features via model_validator vs. require explicit boolean flags; known gaps.
---

# API Keys & Feature Flag Wiring

## Auto-enabled by key presence (no extra flag needed)
- `SLACK_WEBHOOK_URL` → `notification_slack_enabled = True`
- `DISCORD_WEBHOOK_URL` → `notification_discord_enabled = True`
- `INSTAGRAM_ACCESS_TOKEN` + `INSTAGRAM_BUSINESS_ACCOUNT_ID` → `instagram_enabled = True`
  - Note: config field is `meta_access_token`, but aliased to accept `INSTAGRAM_ACCESS_TOKEN` env var
- Email: `NOTIFICATION_EMAIL_FROM` + `NOTIFICATION_EMAIL_PASSWORD` + `NOTIFICATION_EMAIL_TO` → `notification_email_enabled = True`

## Require explicit env var (not auto-detected)
- `LLM_PROVIDER=groq` — defaults to `mock`; must be set explicitly even when GROQ_API_KEY is present
- `VOICE_ENABLED=true` — voice stage defaults to False; set to activate pipeline voice stage
- `AUTO_UPLOAD=true` — defaults to False; set when YouTube creds are present

## Incomplete without additional value
- Telegram: needs both `TELEGRAM_BOT_TOKEN` **and** `TELEGRAM_CHAT_ID`. Bot token alone does not activate it.
  - `TELEGRAM_CHAT_ID` was not provided in the initial key setup — notifications to Telegram remain disabled.

## LLM fallback chain
- When both `GROQ_API_KEY` and `GEMINI_API_KEY` are set and `LLM_PROVIDER=groq`, the factory creates a `groq → gemini` FallbackProvider automatically.

**Why:** These facts are not visible in the running code and required reading config + model_validator to discover.
