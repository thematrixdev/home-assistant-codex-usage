"""Constants for OpenAI Codex Usage integration."""

DOMAIN = "hass_codex_usage"

# API
CODEX_USAGE_API_URL = "https://chatgpt.com/backend-api/codex/usage"
WHAM_USAGE_API_URL = "https://chatgpt.com/backend-api/wham/usage"
OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

# Defaults
DEFAULT_UPDATE_INTERVAL = 300  # seconds

# Config keys
CONF_ACCESS_TOKEN = "access_token"
CONF_ACCOUNT_ID = "account_id"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_UPDATE_INTERVAL = "update_interval"

# Sensor definitions: (key, name, unit, icon, device_class)
SENSOR_DEFINITIONS = [
    ("five_hour_limit_percent", "5 Hours Usage Limit", "%", "mdi:timer-sand", None),
    ("five_hour_reset_time", "5 Hours Reset Time", None, "mdi:timer-refresh", "timestamp"),
    ("weekly_limit_percent", "Weekly Usage Limit", "%", "mdi:calendar-week", None),
    ("weekly_reset_time", "Weekly Reset Time", None, "mdi:calendar-clock", "timestamp"),
    ("code_review_limit_percent", "Code Review Limit", "%", "mdi:file-search", None),
    ("api_error", "API Error", "errors", "mdi:alert-circle", None),
]
