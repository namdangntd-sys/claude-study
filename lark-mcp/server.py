"""Lark Calendar MCP server.

Wraps the Lark Open Platform Calendar API (open.larksuite.com) so Claude can
read and write Lark calendar data through MCP tools.

Required env vars:
    LARK_APP_ID, LARK_APP_SECRET    Custom app credentials
    LARK_BASE_URL (optional)        Defaults to https://open.larksuite.com
                                    Use https://open.feishu.cn for the China region
    LARK_USER_ACCESS_TOKEN (opt)    If set, calls are made on behalf of a user
                                    (needed to access a person's primary calendar).
                                    Otherwise tenant_access_token is used.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

LARK_BASE = os.environ.get("LARK_BASE_URL", "https://open.larksuite.com").rstrip("/")
APP_ID = os.environ.get("LARK_APP_ID", "")
APP_SECRET = os.environ.get("LARK_APP_SECRET", "")
USER_TOKEN = os.environ.get("LARK_USER_ACCESS_TOKEN", "")

mcp = FastMCP("lark-calendar")

_token_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}


async def _tenant_token(client: httpx.AsyncClient) -> str:
    now = time.time()
    if _token_cache["value"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["value"]
    resp = await client.post(
        f"{LARK_BASE}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Lark auth failed: {data}")
    _token_cache["value"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + int(data.get("expire", 7200))
    return _token_cache["value"]


async def _request(method: str, path: str, **kwargs: Any) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        token = USER_TOKEN or await _tenant_token(client)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        resp = await client.request(method, f"{LARK_BASE}{path}", headers=headers, **kwargs)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Lark API error {data.get('code')}: {data.get('msg')} | {data}")
        return data.get("data", {})


def _to_ts(value: str) -> str:
    """Accept ISO-8601 ('2026-05-07T09:00:00+07:00') or unix-seconds string."""
    if value.isdigit():
        return value
    return str(int(datetime.fromisoformat(value).timestamp()))


@mcp.tool()
async def lark_list_calendars() -> dict:
    """List all calendars the authenticated principal can see."""
    return await _request("GET", "/open-apis/calendar/v4/calendars")


@mcp.tool()
async def lark_primary_calendar() -> dict:
    """Get the user's primary calendar (requires user_access_token)."""
    return await _request("POST", "/open-apis/calendar/v4/calendars/primary")


@mcp.tool()
async def lark_list_events(
    calendar_id: str,
    start_time: str,
    end_time: str,
    page_size: int = 50,
    page_token: str = "",
) -> dict:
    """List events in a calendar within a time range.

    Args:
        calendar_id: Lark calendar id (use lark_list_calendars to find it)
        start_time: ISO-8601 datetime e.g. "2026-05-07T00:00:00+07:00", or unix seconds
        end_time:   ISO-8601 datetime, or unix seconds
        page_size:  Max events to return (default 50, max 500)
        page_token: Pagination cursor from a previous response
    """
    params: dict[str, Any] = {
        "start_time": _to_ts(start_time),
        "end_time": _to_ts(end_time),
        "page_size": page_size,
    }
    if page_token:
        params["page_token"] = page_token
    return await _request(
        "GET",
        f"/open-apis/calendar/v4/calendars/{calendar_id}/events",
        params=params,
    )


@mcp.tool()
async def lark_get_event(calendar_id: str, event_id: str) -> dict:
    """Get full details of a single event."""
    return await _request(
        "GET",
        f"/open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}",
    )


@mcp.tool()
async def lark_create_event(
    calendar_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    timezone_name: str = "Asia/Ho_Chi_Minh",
    location: str = "",
) -> dict:
    """Create a new event.

    Args:
        calendar_id: Target calendar id
        summary:     Event title
        start_time:  ISO-8601 datetime or unix seconds
        end_time:    ISO-8601 datetime or unix seconds
        description: Optional body text
        timezone_name: IANA timezone (default Asia/Ho_Chi_Minh)
        location:    Optional location name
    """
    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start_time": {"timestamp": _to_ts(start_time), "timezone": timezone_name},
        "end_time": {"timestamp": _to_ts(end_time), "timezone": timezone_name},
    }
    if location:
        body["location"] = {"name": location}
    return await _request(
        "POST",
        f"/open-apis/calendar/v4/calendars/{calendar_id}/events",
        json=body,
    )


@mcp.tool()
async def lark_delete_event(calendar_id: str, event_id: str) -> dict:
    """Delete an event."""
    return await _request(
        "DELETE",
        f"/open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}",
    )


if __name__ == "__main__":
    if not (USER_TOKEN or (APP_ID and APP_SECRET)):
        raise SystemExit(
            "Set LARK_USER_ACCESS_TOKEN, or both LARK_APP_ID and LARK_APP_SECRET."
        )
    mcp.run()
