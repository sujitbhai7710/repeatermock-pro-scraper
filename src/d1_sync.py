"""D1 sync — push progress.json to Cloudflare D1."""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from src.config import PROGRESS_FILE, TESTS_DIR, TARGET_SERIES

API_BASE_CF = "https://api.cloudflare.com/client/v4"


def get_env():
    return {
        "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
        "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        "D1_DATABASE_ID": os.environ.get("D1_DATABASE_ID", ""),
    }


def d1_query(env, sql, params=None):
    token = env["CLOUDFLARE_API_TOKEN"]
    account = env["CLOUDFLARE_ACCOUNT_ID"]
    db_id = env["D1_DATABASE_ID"]
    if not all([token, account, db_id]):
        return None
    url = f"{API_BASE_CF}/accounts/{account}/d1/database/{db_id}/query"
    body = json.dumps({"sql": sql, "params": params or []}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠ D1 query error: {e}")
        return None


def sync(progress):
    env = get_env()
    if not env["CLOUDFLARE_API_TOKEN"]:
        print("  ⚠ CLOUDFLARE_API_TOKEN not set — skipping D1 sync")
        return False

    # Sync series
    for s in TARGET_SERIES:
        slug = s["slug"]
        url = f"https://repeatermock.com/tb-pro/test-series/{slug}"
        # Count from inventory
        inv = [t for t in progress.get("test_inventory", []) if t.get("_slug") == slug]
        total = len(inv)
        scraped = len([t for t in inv if t["id"] in set(progress.get("scraped_test_ids", []))])
        partial = len([t for t in inv if t["id"] in set(progress.get("partial_test_ids", []))])
        failed = len([t for t in inv if t["id"] in set(progress.get("failed_test_ids", []))])
        pending = total - scraped - partial - failed

        sql = """INSERT INTO series (platform, slug, name, series_url, total_tests, scraped_count, partial_count, failed_count, pending_count, updated_at)
                 VALUES ('tb-pro', ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                 ON CONFLICT(platform, slug) DO UPDATE SET
                   name=excluded.name, total_tests=excluded.total_tests,
                   scraped_count=excluded.scraped_count, partial_count=excluded.partial_count,
                   failed_count=excluded.failed_count, pending_count=excluded.pending_count,
                   updated_at=unixepoch()"""
        d1_query(env, sql, [slug, s["name"], url, total, scraped, partial, failed, pending])

    # Sync tests
    scraped_set = set(progress.get("scraped_test_ids", []))
    partial_set = set(progress.get("partial_test_ids", []))
    failed_set = set(progress.get("failed_test_ids", []))
    tests_status = progress.get("tests_status", {})

    for t in progress.get("test_inventory", []):
        tid = t["id"]
        slug = t.get("_slug", "")
        title = t.get("title", "")
        section = t.get("_section", "")
        subsection = t.get("_subsection", "")
        status = "scraped" if tid in scraped_set else ("partial" if tid in partial_set else ("failed" if tid in failed_set else "pending"))
        ts = tests_status.get(tid, {})

        sql = """INSERT INTO tests (test_id, series_slug, title, section, subsection, status, has_questions, has_answers, has_solutions, has_analysis, last_attempted_at, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                 ON CONFLICT(test_id) DO UPDATE SET
                   series_slug=excluded.series_slug, title=excluded.title,
                   status=excluded.status, has_questions=excluded.has_questions,
                   has_answers=excluded.has_answers, has_solutions=excluded.has_solutions,
                   has_analysis=excluded.has_analysis, last_attempted_at=excluded.last_attempted_at,
                   updated_at=unixepoch()"""
        d1_query(env, sql, [tid, slug, title, section, subsection, status,
                            1 if ts.get("has_questions") else (1 if tid in scraped_set else 0),
                            1 if tid in scraped_set else 0,
                            1 if tid in scraped_set else 0,
                            1 if tid in scraped_set else 0,
                            int(ts.get("last_attempted_at", 0)) if ts.get("last_attempted_at") else None])

    # Sync runs
    for r in progress.get("run_history", [])[-10:]:
        sql = """INSERT INTO runs (started_at, ended_at, time_minutes, tests_scraped, status)
                 VALUES (?, ?, ?, ?, 'completed')
                 ON CONFLICT(id) DO NOTHING"""
        d1_query(env, sql, [int(r.get("start", 0)), int(r.get("end", 0)),
                           r.get("time_minutes", 0), r.get("tests_scraped", 0)])

    print("  ✓ D1 sync complete")
    return True


if __name__ == "__main__":
    progress = json.loads(PROGRESS_FILE.read_text())
    sync(progress)
