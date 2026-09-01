"""
Mass scraper — main orchestrator.

Scrapes ALL PRO tests (6,803 across 23 tb-pro series) using a 1-day trial account.
- Force-refreshes every 8 tests (preserves token chain)
- Auto-commits rotated cookies to git
- Only saves fully-scraped tests (Q+A+Sol+Ana)
- Handles 429 rate limiting + 401 auth expiry
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import *
from src.cookie_manager import load_cookies, save_cookies, cookies_to_string
from src.token_rotation import create_browser_session, verify_auth, force_refresh, auth_and_refresh
from src.submit_attempt import RateLimited, AuthExpired
from src.full_scraper import scrape_test_full


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {
        "scraped_test_ids": [],
        "partial_test_ids": [],
        "failed_test_ids": [],
        "tests_status": {},
        "series_progress": {},
        "test_inventory": [],
        "run_history": [],
        "last_run_start": None,
        "last_run_end": None,
    }


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


def git_commit():
    """Commit rotated cookies + progress to git."""
    try:
        subprocess.run(["git", "add", "cookies/account_pro.json", "data/progress.json"],
                      capture_output=True, cwd=str(REPO_ROOT))
        r = subprocess.run(["git", "diff", "--staged", "--quiet"],
                          capture_output=True, cwd=str(REPO_ROOT))
        if r.returncode != 0:
            subprocess.run(["git", "commit", "-m", "chore: rotate cookies + progress [skip ci]"],
                          capture_output=True, cwd=str(REPO_ROOT))
            subprocess.run(["git", "push"], capture_output=True, cwd=str(REPO_ROOT))
            print("  ✓ Git committed cookies + progress", flush=True)
    except Exception as e:
        print(f"  ⚠ Git commit failed: {e}", flush=True)


async def fetch_test_inventory(context, cookies):
    """Fetch all test IDs for all 23 tb-pro series."""
    cookie_str = cookies_to_string(cookies)
    inventory = []
    for series in TARGET_SERIES:
        slug = series["slug"]
        print(f"  Fetching tests: {series['name'][:50]}...", flush=True)
        try:
            resp = await context.request.get(
                f"{API_BASE}/api/v1/test-series/{slug}?variant=tb-pro",
                headers={"Accept": "application/json", "Cookie": cookie_str}
            )
            if resp.status != 200:
                print(f"    ⚠ HTTP {resp.status}", flush=True)
                continue
            data = json.loads(await resp.text())
            details = data.get("data", {}).get("details", {})
            series_id = details.get("id", "")
            if not series_id:
                continue

            for sec in details.get("sections", []):
                subs = sec.get("subsections", [])
                if not subs:
                    url = f"{API_BASE}/api/v1/test-series/{series_id}/sections/{sec['id']}/tests?limit=500&variant=tb-pro"
                    r = await context.request.get(url, headers={"Accept": "application/json", "Cookie": cookie_str})
                    if r.status == 200:
                        for t in json.loads(await r.text()).get("data", []):
                            t["_slug"] = slug
                            t["_section"] = sec.get("name", "")
                            inventory.append(t)
                else:
                    for sub in subs:
                        url = f"{API_BASE}/api/v1/test-series/{series_id}/sections/{sec['id']}/tests?limit=500&variant=tb-pro&subSectionId={sub['id']}"
                        r = await context.request.get(url, headers={"Accept": "application/json", "Cookie": cookie_str})
                        if r.status == 200:
                            for t in json.loads(await r.text()).get("data", []):
                                t["_slug"] = slug
                                t["_section"] = sec.get("name", "")
                                t["_subsection"] = sub.get("name", "")
                                inventory.append(t)
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"    ✗ Error: {e}", flush=True)

    # Dedupe by test ID
    seen = set()
    deduped = []
    for t in inventory:
        if t["id"] not in seen:
            seen.add(t["id"])
            deduped.append(t)

    print(f"  ✓ Total: {len(deduped)} tests across {len(TARGET_SERIES)} series", flush=True)
    return deduped


async def run(time_limit_minutes: int = 0, max_tests: int = 0):
    start_time = time.time()
    time_limit_seconds = time_limit_minutes * 60 if time_limit_minutes > 0 else 0

    print(f"\n{'='*60}")
    print(f"REPEATERMOCK PRO MASS SCRAPER")
    print(f"{'='*60}")
    print(f"  Time limit: {time_limit_minutes} min" + (" (no limit)" if time_limit_minutes == 0 else ""))
    print(f"  Max tests: {max_tests if max_tests > 0 else 'unlimited'}")
    print(f"  Start: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    cookies = load_cookies()
    if not cookies:
        print("✗ No cookies found in cookies/account_pro.json")
        print("  Set REPEATERMOCK_COOKIES env var or create cookies/account_pro.json")
        return

    p = browser = context = None
    try:
        p, browser, context = await create_browser_session(cookies)
        page = await context.new_page()

        # Startup auth + force-refresh
        print("\n→ Authenticating...", flush=True)
        cookies = await auth_and_refresh(context, cookies)
        if cookies is None:
            print("✗ Auth failed — cookies expired. Re-export from browser.")
            return

        # Load/build test inventory
        progress = load_progress()
        if not progress.get("test_inventory"):
            print("\n→ Building test inventory (first run)...", flush=True)
            inventory = await fetch_test_inventory(context, cookies)
            progress["test_inventory"] = [
                {"id": t["id"], "title": t.get("title",""), "_slug": t.get("_slug",""),
                 "_section": t.get("_section",""), "_subsection": t.get("_subsection",""),
                 "duration": t.get("duration",60), "totalMark": t.get("totalMark",200),
                 "questionCount": t.get("questionCount",100)}
                for t in inventory
            ]
            save_progress(progress)
        else:
            print(f"\n✓ Using cached inventory: {len(progress['test_inventory'])} tests", flush=True)

        inventory = progress["test_inventory"]
        scraped_ids = set(progress["scraped_test_ids"])
        partial_ids = set(progress["partial_test_ids"])
        failed_ids = set(progress["failed_test_ids"])

        # Filter to pending
        pending = [t for t in inventory
                   if t["id"] not in scraped_ids
                   or t["id"] in partial_ids
                   or t["id"] in failed_ids]
        print(f"  Scraped: {len(scraped_ids)} | Pending: {len(pending)}", flush=True)

        if not pending:
            print("\n✓ ALL TESTS SCRAPED! Done.")
            return

        # Scrape loop
        tests_done = 0
        tests_since_refresh = 0
        run_start = time.time()

        for i, test in enumerate(pending):
            elapsed = time.time() - start_time
            if time_limit_seconds > 0 and elapsed >= time_limit_seconds:
                print(f"\n⏰ Time limit reached ({elapsed/60:.1f} min)")
                break
            if max_tests > 0 and tests_done >= max_tests:
                print(f"\n Max tests reached ({max_tests})")
                break
            # Abort before trial expires (95% of 24h)
            if elapsed > PRO_TRIAL_HOURS * 3600 * 0.95:
                print(f"\n⚠ Trial expiring soon — aborting")
                break

            mins_left = int((time_limit_seconds - elapsed) / 60) if time_limit_seconds > 0 else "∞"
            print(f"\n  [{tests_done+1}] ({mins_left}m left) {test.get('title','')[:50]}", flush=True)

            try:
                result = await scrape_test_full(context, test, cookies)

                has_q = result.get("has_questions", False)
                has_a = result.get("has_answers", False)
                has_ana = result.get("has_analysis", False)

                if has_q and has_a and has_ana:
                    scraped_ids.add(test["id"])
                    partial_ids.discard(test["id"])
                    failed_ids.discard(test["id"])
                    tests_since_refresh += 1
                elif has_q:
                    partial_ids.add(test["id"])
                else:
                    failed_ids.add(test["id"])

                tests_done += 1

            except AuthExpired as e:
                print(f"    ↻ Auth expired — force-refreshing...", flush=True)
                try:
                    cookies = await force_refresh(context, cookies)
                    save_cookies(cookies)
                    tests_since_refresh = 0
                    continue  # retry same test
                except Exception as e2:
                    print(f"    ✗ Refresh failed: {e2}", flush=True)
                    break

            except RateLimited as e:
                print(f"    ⏸ Rate limited ({e.scope}) — sleeping {e.retry_after}s", flush=True)
                await asyncio.sleep(e.retry_after)
                continue  # retry same test

            except Exception as e:
                print(f"    ✗ Error: {e}", flush=True)
                failed_ids.add(test["id"])

            # Update progress
            progress["scraped_test_ids"] = list(scraped_ids)
            progress["partial_test_ids"] = list(partial_ids)
            progress["failed_test_ids"] = list(failed_ids)
            progress["tests_status"][test["id"]] = {
                "status": "scraped" if test["id"] in scraped_ids else ("partial" if test["id"] in partial_ids else "failed"),
                "last_attempted_at": time.time(),
            }
            save_progress(progress)

            # Force-refresh every 8 tests
            if tests_since_refresh >= REFRESH_EVERY_N_TESTS:
                print(f"\n  → Force-refresh (every {REFRESH_EVERY_N_TESTS} tests)...", flush=True)
                try:
                    cookies = await force_refresh(context, cookies)
                    save_cookies(cookies)
                    git_commit()  # preserve chain
                    tests_since_refresh = 0
                    print(f"  ✓ Token refreshed + committed", flush=True)
                except Exception as e:
                    print(f"  ⚠ Refresh failed: {e}", flush=True)

            await asyncio.sleep(START_MIN_INTERVAL)

        # Summary
        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"RUN SUMMARY")
        print(f"{'='*60}")
        print(f"  Tests scraped: {tests_done}")
        print(f"  Total scraped (all runs): {len(scraped_ids)}")
        print(f"  Partial: {len(partial_ids)}")
        print(f"  Failed: {len(failed_ids)}")
        print(f"  Time: {elapsed/60:.1f} min")

        progress["last_run_end"] = time.time()
        progress["run_history"].append({
            "start": run_start, "end": progress["last_run_end"],
            "tests_scraped": tests_done, "time_minutes": elapsed/60,
        })
        progress["run_history"] = progress["run_history"][-20:]
        save_progress(progress)

        # Final git commit
        save_cookies(cookies)
        git_commit()

    finally:
        if browser:
            await browser.close()
        if p:
            await p.stop()

    print(f"\n✓ Done.")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--time-limit-minutes", type=int, default=0)
    parser.add_argument("--max-tests", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(run(args.time_limit_minutes, args.max_tests))


if __name__ == "__main__":
    main()
