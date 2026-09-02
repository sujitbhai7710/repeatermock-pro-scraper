"""Submit attempt — /start + /submit using the known working payload format."""
import asyncio
import json
from src.config import API_BASE


class RateLimited(Exception):
    def __init__(self, retry_after: int, scope: str):
        self.retry_after = retry_after or 60
        self.scope = scope


class AuthExpired(Exception):
    pass


async def start_attempt(context, test_id: str, cookie_str: str):
    """POST /api/v1/attempts/{testId}/start"""
    url = f"{API_BASE}/api/v1/attempts/{test_id}/start"
    resp = await context.request.post(url, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Origin": "https://repeatermock.com",
        "Referer": "https://repeatermock.com/",
    }, data="{}")
    body = await resp.text()

    if resp.status == 429:
        retry_after = int(resp.headers.get("retry-after", "60"))
        retry_after = min(retry_after, 120)  # cap at 2 min — server sometimes sends 56000s
        raise RateLimited(retry_after, "start")
    if resp.status == 402:
        raise AuthExpired(f"Payment required — PRO trial expired for {test_id}")
    if resp.status == 401:
        raise AuthExpired(f"401 session_expired on /start for {test_id}")
    if resp.status != 200:
        print(f"  ⚠ /start → {resp.status}: {body[:100]}")
        return False
    return True


async def submit_attempt(context, test_id: str, cookie_str: str):
    """POST /api/v1/attempts/{testId}/submit with known working format."""
    url = f"{API_BASE}/api/v1/attempts/{test_id}/submit"
    payload = {"answers": [], "timeTaken": 1, "language": "en", "interface": "classic"}
    resp = await context.request.post(url, headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": cookie_str,
        "Origin": "https://repeatermock.com",
        "Referer": "https://repeatermock.com/",
    }, data=json.dumps(payload))
    body = await resp.text()

    if resp.status == 429:
        retry_after = int(resp.headers.get("retry-after", "10"))
        retry_after = min(retry_after, 120)  # cap at 2 min
        raise RateLimited(retry_after, "submit")
    if resp.status == 401 or "session_expired" in body:
        raise AuthExpired(f"401 session_expired on /submit for {test_id}")
    if resp.status != 200:
        print(f"  ⚠ /submit → {resp.status}: {body[:100]}")
        return False
    return True
