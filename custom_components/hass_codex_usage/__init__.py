"""OpenAI Codex Usage integration for Home Assistant."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CODEX_USAGE_API_URL,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_ID,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    OAUTH_CLIENT_ID,
    OAUTH_TOKEN_URL,
    WHAM_USAGE_API_URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type CodexUsageConfigEntry = ConfigEntry[CodexUsageCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Set up OpenAI Codex Usage from a config entry."""
    coordinator = CodexUsageCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
    """Handle options update."""
    coordinator: CodexUsageCoordinator = entry.runtime_data
    interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)


class CodexUsageCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch OpenAI Codex usage data."""

    config_entry: CodexUsageConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CodexUsageConfigEntry) -> None:
        """Initialize the coordinator."""
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch usage data from the API."""
        access_token = _normalize_credential_value(
            self.config_entry.options.get(
                CONF_ACCESS_TOKEN,
                self.config_entry.data.get(CONF_ACCESS_TOKEN, ""),
            )
        )
        account_id = _normalize_credential_value(
            self.config_entry.options.get(
                CONF_ACCOUNT_ID,
                self.config_entry.data.get(CONF_ACCOUNT_ID, ""),
            )
        )
        refresh_token = _normalize_credential_value(
            self.config_entry.options.get(
                CONF_REFRESH_TOKEN,
                self.config_entry.data.get(CONF_REFRESH_TOKEN, ""),
            )
        )

        if not access_token:
            raise ConfigEntryAuthFailed("Missing access token")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        if account_id:
            headers["ChatGPT-Account-Id"] = account_id

        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            raw = await _fetch_codex_usage(session=session, headers=headers)
        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                if refresh_token:
                    try:
                        new_access_token, new_refresh_token = await _refresh_access_token(
                            session=aiohttp_client.async_get_clientsession(self.hass),
                            refresh_token=refresh_token,
                        )
                    except aiohttp.ClientError as refresh_err:
                        raise ConfigEntryAuthFailed(
                            "Token refresh failed - run codex login --device-auth on codex machine and update credentials"
                        ) from refresh_err
                    access_token = new_access_token
                    if new_refresh_token:
                        refresh_token = new_refresh_token

                    self._update_stored_credentials(
                        access_token=access_token,
                        refresh_token=refresh_token,
                    )
                    headers["Authorization"] = f"Bearer {access_token}"
                    raw = await _fetch_codex_usage(session=session, headers=headers)
                else:
                    raise ConfigEntryAuthFailed(
                        "Authentication failed - run codex login --device-auth on codex machine and update credentials"
                    ) from err
            else:
                raise UpdateFailed(f"Error fetching usage data: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error fetching usage data: {err}") from err

        return _parse_limit_percents(raw)

    def _update_stored_credentials(self, access_token: str, refresh_token: str) -> None:
        """Persist newly refreshed credentials."""
        new_data = {
            **self.config_entry.data,
            CONF_ACCESS_TOKEN: access_token,
            CONF_REFRESH_TOKEN: refresh_token,
        }
        new_options = {
            **self.config_entry.options,
            CONF_ACCESS_TOKEN: access_token,
            CONF_REFRESH_TOKEN: refresh_token,
        }
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data=new_data,
            options=new_options,
        )


def _normalize_credential_value(value: Any) -> str:
    """Accept plain tokens, quoted tokens, or JSON object with `data`."""
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, str):
        return parsed.strip()
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, str):
            return data.strip()
    return raw


async def _refresh_access_token(
    session: aiohttp.ClientSession,
    refresh_token: str,
) -> tuple[str, str | None]:
    """Refresh ChatGPT auth tokens using OpenAI OAuth token endpoint."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": OAUTH_CLIENT_ID,
    }
    resp = await session.post(
        OAUTH_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=aiohttp.ClientTimeout(total=15),
    )
    resp.raise_for_status()
    token_data = await resp.json()
    access_token = token_data.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ConfigEntryAuthFailed("Token refresh response missing access_token")
    new_refresh_token = token_data.get("refresh_token")
    if isinstance(new_refresh_token, str) and new_refresh_token:
        return access_token, new_refresh_token
    return access_token, None


async def _fetch_codex_usage(
    session: aiohttp.ClientSession,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Fetch Codex usage limits from ChatGPT backend."""
    last_error_status: int | None = None
    for url in (CODEX_USAGE_API_URL, WHAM_USAGE_API_URL):
        resp = await session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        )
        if resp.ok:
            payload = await resp.json()
            if isinstance(payload, dict):
                return payload
            raise UpdateFailed("Unexpected Codex usage response format")

        last_error_status = resp.status
        # codex/usage may be forbidden while wham/usage is allowed
        if resp.status in (401, 403, 404):
            continue
        resp.raise_for_status()

    if last_error_status is not None:
        raise aiohttp.ClientResponseError(
            request_info=resp.request_info,
            history=resp.history,
            status=last_error_status,
            message="All Codex usage endpoints failed",
            headers=resp.headers,
        )
    raise UpdateFailed("Unable to contact Codex usage endpoint")


def _parse_limit_percents(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract requested usage percentages from codex usage payload."""
    data: dict[str, Any] = {}

    # Fast path for /backend-api/wham/usage schema.
    five_hour = _extract_wham_window_percent(raw.get("rate_limit"), window_seconds=5 * 60 * 60)
    weekly = _extract_wham_window_percent(raw.get("rate_limit"), window_seconds=7 * 24 * 60 * 60)
    review = _extract_wham_window_percent(
        raw.get("code_review_rate_limit"),
        window_seconds=7 * 24 * 60 * 60,
    )
    if five_hour is not None:
        data["five_hour_limit_percent"] = five_hour
    five_hour_reset = _extract_wham_window_reset_time(
        raw.get("rate_limit"),
        window_seconds=5 * 60 * 60,
    )
    if five_hour_reset is not None:
        data["five_hour_reset_time"] = five_hour_reset
    if weekly is not None:
        data["weekly_limit_percent"] = weekly
    weekly_reset = _extract_wham_window_reset_time(
        raw.get("rate_limit"),
        window_seconds=7 * 24 * 60 * 60,
    )
    if weekly_reset is not None:
        data["weekly_reset_time"] = weekly_reset
    if review is not None:
        data["code_review_limit_percent"] = review
    if (
        "five_hour_limit_percent" in data
        and "weekly_limit_percent" in data
        and "code_review_limit_percent" in data
    ):
        return data

    if "five_hour_limit_percent" not in data:
        data["five_hour_limit_percent"] = _extract_limit_percent(
            raw,
            target_name_tokens=("five", "hour"),
            window_minutes=300,
        )
    if "weekly_limit_percent" not in data:
        data["weekly_limit_percent"] = _extract_limit_percent(
            raw,
            target_name_tokens=("week",),
            window_minutes=7 * 24 * 60,
        )
    if "code_review_limit_percent" not in data:
        data["code_review_limit_percent"] = _extract_limit_percent(
            raw,
            target_name_tokens=("review",),
            window_minutes=None,
        )
    return data


def _extract_wham_window_percent(rate_limit: Any, window_seconds: int) -> float | None:
    """Extract used_percent from wham window entries."""
    if not isinstance(rate_limit, dict):
        return None
    for key in ("primary_window", "secondary_window"):
        window = rate_limit.get(key)
        if not isinstance(window, dict):
            continue
        limit_window = window.get("limit_window_seconds")
        if not isinstance(limit_window, (int, float)) or int(limit_window) != window_seconds:
            continue
        parsed = _as_percent(window.get("used_percent"))
        if parsed is not None:
            return parsed
    return None


def _extract_wham_window_reset_time(rate_limit: Any, window_seconds: int) -> datetime | None:
    """Extract reset timestamp from wham window entries."""
    if not isinstance(rate_limit, dict):
        return None
    for key in ("primary_window", "secondary_window"):
        window = rate_limit.get(key)
        if not isinstance(window, dict):
            continue
        limit_window = window.get("limit_window_seconds")
        if not isinstance(limit_window, (int, float)) or int(limit_window) != window_seconds:
            continue
        reset_at = window.get("reset_at")
        if isinstance(reset_at, (int, float)) and reset_at > 0:
            return datetime.fromtimestamp(float(reset_at), tz=timezone.utc)
    return None


def _extract_limit_percent(
    raw: dict[str, Any],
    target_name_tokens: tuple[str, ...],
    window_minutes: int | None,
) -> float | None:
    """Find best matching percent value in nested payload."""
    best_match: float | None = None
    best_score = -1

    for obj in _walk_dicts(raw):
        score = _match_score(obj, target_name_tokens, window_minutes)
        if score < 0:
            continue

        percent = _extract_percent_value(obj)
        if percent is None:
            continue

        if score > best_score:
            best_score = score
            best_match = percent

    return best_match


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    """Return all nested dicts from value."""
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        out.append(value)
        for v in value.values():
            out.extend(_walk_dicts(v))
    elif isinstance(value, list):
        for v in value:
            out.extend(_walk_dicts(v))
    return out


def _match_score(
    obj: dict[str, Any],
    target_name_tokens: tuple[str, ...],
    window_minutes: int | None,
) -> int:
    """Score how likely this object represents a requested limit."""
    text = " ".join(str(v).lower() for v in obj.values())
    score = 0

    for token in target_name_tokens:
        if token in text:
            score += 2

    if "limit_name" in obj and isinstance(obj["limit_name"], str):
        name = obj["limit_name"].lower()
        if all(token in name for token in target_name_tokens):
            score += 4

    if window_minutes is not None:
        for key in ("window_minutes", "window", "window_minutes_count"):
            val = obj.get(key)
            if isinstance(val, (int, float)) and int(val) == window_minutes:
                score += 3
        for key in ("primary_window_minutes", "secondary_window_minutes"):
            val = obj.get(key)
            if isinstance(val, (int, float)) and int(val) == window_minutes:
                score += 2

    if score == 0:
        return -1
    return score


def _extract_percent_value(obj: dict[str, Any]) -> float | None:
    """Extract a percent value from one candidate limit object."""
    percent_keys = (
        "used_percent",
        "usage_percent",
        "percent",
        "utilization",
        "primary_used_percent",
        "secondary_used_percent",
        "used-percent",
        "primary-used-percent",
        "secondary-used-percent",
    )
    for key in percent_keys:
        value = obj.get(key)
        parsed = _as_percent(value)
        if parsed is not None:
            return parsed

    used_keys = ("used", "used_tokens", "count", "used_count")
    limit_keys = ("limit", "max", "total_limit", "capacity")
    used = next((obj.get(k) for k in used_keys if obj.get(k) is not None), None)
    limit = next((obj.get(k) for k in limit_keys if obj.get(k) is not None), None)
    if isinstance(used, (int, float)) and isinstance(limit, (int, float)) and limit > 0:
        return round((float(used) / float(limit)) * 100, 2)

    return None


def _as_percent(value: Any) -> float | None:
    """Parse a raw value into a 0..100 percentage."""
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        text = value.strip().rstrip("%")
        try:
            numeric = float(text)
        except ValueError:
            return None
    else:
        return None

    if 0 <= numeric <= 1:
        numeric *= 100
    if numeric < 0:
        return None
    if numeric > 1000:
        return None
    return round(numeric, 2)
