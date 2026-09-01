"""
Token rotation — THE CRITICAL PIECE.

Captures rotated refreshToken from Set-Cookie headers using headers_array()
(NOT resp.headers dict, which merges duplicate Set-Cookie and loses the token).
"""
import asyncio
import base64
import json
import re
import time
from typing import Any
from playwright.async_api import async_playwright
from src.config import API_BASE
from src.cookie_manager import cookies_to_string, save_cookies, load_cookies, get_cookie_value
from src.config import COOKIES_FILE


async def create_browser_session(cookies: list[dict[str, Any]]):
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    clean = []
    for c in cookies:
        cc = {
            "name": c["name"], "value": c["value"],
            "domain": c.get("domain", ".repeatermock.com"),
            "path": c.get("path", "/"),
        }
        ss = c.get("sameSite", "Lax")
        cc["sameSite"] = ss if ss in ("Strict", "Lax", "None") else "Lax"
        if c.get("secure"): cc["secure"] = True
        if c.get("httpOnly"): cc["httpOnly"] = True
        clean.append(cc)
    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    )
    if clean:
        await context.add_cookies(clean)
    await context.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        window.chrome = {runtime:{}};
        window.console.clear = function(){};
        Object.defineProperty(window,'close',{value:function(){},writable:true});
    """)
    return p, browser, context


def get_set_cookie_headers(resp) -> list[str]:
    """Return ALL Set-Cookie headers individually.
    CRITICAL: resp.headers dict merges duplicate Set-Cookie → loses rotated refreshToken."""
    out = []
    try:
        arr = resp.headers_array()
        if callable(arr):
            arr = arr()
        for h in arr or []:
            if str(h.get("name", "")).lower() == "set-cookie":
                out.append(h.get("value", ""))
    except Exception:
        pass
    if not out:
        merged = resp.headers.get("set-cookie", "")
        if merged:
            out = [merged]
    return out


def extract_rotated_tokens(resp, body: str) -> dict[str, str]:
    """Extract accessToken/refreshToken/totpVerified from Set-Cookie headers + JSON body."""
    tokens = {}
    wanted = ("accessToken", "refreshToken", "totpVerified")
    for raw in get_set_cookie_headers(resp):
        for name in wanted:
            m = re.search(rf'(?:^|[;\s]){name}\s*=\s*([^;]+)', raw)
            if m:
                val = m.group(1).strip()
                if val and val.lower() not in ("deleted", "", "null"):
                    tokens[name] = val
    try:
        data = json.loads(body)
        def _walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in wanted and isinstance(v, str) and v.strip():
                        tokens.setdefault(k, v.strip())
                    elif isinstance(v, (dict, list)):
                        _walk(v)
            elif isinstance(o, list):
                for i in o: _walk(i)
        _walk(data)
    except Exception:
        pass
    return tokens


def access_token_seconds_left(cookies: list[dict]) -> int:
    """Decode JWT exp claim."""
    at = get_cookie_value(cookies, "accessToken")
    if not at:
        return 0
    try:
        parts = at.split(".")
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return max(0, data.get("exp", 0) - int(time.time()))
    except Exception:
        return 0


async def verify_auth(context, cookies) -> bool:
    """Check if access token is valid via /auth/me."""
    resp = await context.request.get(f"{API_BASE}/auth/me", headers={
        "Accept": "application/json",
        "Cookie": cookies_to_string(cookies),
    })
    body = await resp.text()
    return resp.status == 200 and '"success":true' in body


async def force_refresh(context, original_cookies: list[dict]) -> list[dict]:
    """Force-refresh access token. Captures rotated refreshToken from Set-Cookie.
    Returns updated cookies list (mutated in place)."""
    cookie_str = cookies_to_string(original_cookies)
    if "refreshToken" not in cookie_str:
        raise RuntimeError("No refreshToken — cannot refresh, account dead")

    resp = await context.request.post(f"{API_BASE}/auth/refresh", headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Origin": "https://repeatermock.com",
        "Referer": "https://repeatermock.com/",
    }, data="{}")
    body = await resp.text()
    if resp.status != 200:
        raise RuntimeError(f"/auth/refresh → {resp.status}: {body[:100]}")

    new_tokens = extract_rotated_tokens(resp, body)
    if "refreshToken" not in new_tokens:
        raise RuntimeError(
            "⚠⚠⚠ CHAIN BROKEN: /auth/refresh → 200 but no new refreshToken captured! "
            "Old refresh token consumed. Manual cookie re-export required."
        )
    for c in original_cookies:
        if c.get("name") in new_tokens:
            c["value"] = new_tokens[c["name"]]
    return original_cookies


async def auth_and_refresh(context, cookies):
    """Startup auth: verify, if expired force-refresh. Returns updated cookies or None."""
    if await verify_auth(context, cookies):
        print("  ✓ Access token valid")
        # Still force-refresh to get fresh 15-min window
        try:
            cookies = await force_refresh(context, cookies)
            save_cookies(cookies)
            print("  ✓ Force-refreshed at startup (fresh 15-min window)")
        except Exception as e:
            print(f"  ⚠ Force-refresh failed: {e} — continuing with existing token")
        return cookies

    print("  ⚠ Access token expired — force-refreshing...")
    try:
        cookies = await force_refresh(context, cookies)
        save_cookies(cookies)
        print("  ✓ Refreshed successfully")
        return cookies
    except Exception as e:
        print(f"  ✗ Refresh failed: {e}")
        return None
