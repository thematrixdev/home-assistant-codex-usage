# OpenAI Codex Usage - Home Assistant Integration

A custom Home Assistant integration that monitors OpenAI Codex usage limits from the ChatGPT Codex backend endpoint used by Codex CLI.

## Sensors

- **5 Hours Usage Limit** (%)
- **Weekly Usage Limit** (%)
- **Code Review Limit** (%)
- **API Error** (0 = healthy, 1 = failing)

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Restart Home Assistant
3. Install "OpenAI Codex Usage"
4. Go to Settings -> Devices & Services -> Add Integration -> "OpenAI Codex Usage"
5. Follow the instructions

### Manual

1. Copy `custom_components/hass_codex_usage/` to your HA `custom_components/` directory
2. Restart Home Assistant
3. Add the integration via the UI

## Setup

This integration accepts credentials generated on another machine where Codex CLI is logged in.

### Required credentials

- `Access Token` (required)
- `Account ID` (optional but recommended)
- `Refresh Token` (optional but strongly recommended)

### How to obtain credentials (from another machine)

1. On the Codex machine, run: `codex login --device-auth`
2. Confirm login: `codex login status`
3. Open `~/.codex/auth.json`
4. Copy:
   - `tokens.access_token` -> Home Assistant `Access Token`
   - `tokens.account_id` -> Home Assistant `Account ID` (optional)
   - `tokens.refresh_token` -> Home Assistant `Refresh Token` (recommended)
5. After copying into Home Assistant, remove any generated/exported credential file you created for transfer.
   - This avoids the same credential file being reused on multiple hosts.

## Options

- **Update interval** - How often to poll usage (default: 300 seconds, min: 60, max: 3600)
- **Access Token** - Credential used for `/backend-api/codex/usage`
- **Account ID** - Optional header value (`ChatGPT-Account-Id`)
- **Refresh Token** - Used to auto-refresh expired access tokens via OpenAI OAuth

## Notes

- This integration reads from `https://chatgpt.com/backend-api/codex/usage` (fallback: `/backend-api/wham/usage`).
- This endpoint is not officially documented for third-party integrations and may change.
- If access token expires and refresh token is set, the integration refreshes tokens automatically.

## License

MIT License - see [LICENSE](LICENSE) file for details.
