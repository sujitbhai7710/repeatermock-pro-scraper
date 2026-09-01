"""D1 sync — minimal writes to avoid hitting free tier limit (100k writes/day)."""
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
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        if "free tier daily row write limit" in err:
            print("  ⚠ D1 free tier write limit hit — skipping sync until tomorrow UTC")
        else:
            print(f"  ⚠ D1 query error: HTTP {e.code}: {err[:200]}")
        return None
    except Exception as e:
        print(f"  ⚠ D1 query error: {e}")
        return None


def sync(progress, only_changed=None):
    """Sync to D1. only_changed = set of test_ids that changed (to minimize writes)."""
    env = get_env()
    if not env["CLOUDFLARE_API_TOKEN"]:
        print("  ⚠ CLOUDFLARE_API_TOKEN not set — skipping D1 sync")
        return False

    scraped_set = set(progress.get("scraped_test_ids", []))
    partial_set = set(progress.get("partial_test_ids", []))
    failed_set = set(progress.get("failed_test_ids", []))
    tests_status = progress.get("tests_status", {})

    # 1. Sync series (only 24 rows — cheap)
    for s in TARGET_SERIES:
        slug = s["slug"]
        url = f"https://repeatermock.com/tb-pro/test-series/{slug}"
        inv = [t for t in progress.get("test_inventory", []) if t.get("_slug") == slug]
        total = len(inv)
        scraped = len([t for t in inv if t["id"] in scraped_set])
        partial = len([t for t in inv if t["id"] in partial_set])
        failed = len([t for t in inv if t["id"] in failed_set])
        pending = max(0, total - scraped - partial - failed)

        sql = """INSERT INTO series (platform, slug, name, series_url, total_tests, scraped_count, partial_count, failed_count, pending_count, updated_at)
                 VALUES ('tb-pro', ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                 ON CONFLICT(platform, slug) DO UPDATE SET
                   total_tests=excluded.total_tests, scraped_count=excluded.scraped_count,
                   partial_count=excluded.partial_count, failed_count=excluded.failed_count,
                   pending_count=excluded.pending_count, updated_at=unixepoch()"""
        d1_query(env, sql, [slug, s["name"], url, total, scraped, partial, failed, pending])

    # 2. Sync ONLY changed tests (not all 7000+)
    if only_changed:
        for tid in only_changed:
            # Find in inventory
            test = None
            for t in progress.get("test_inventory", []):
                if t["id"] == tid:
                    test = t
                    break
            if not test:
                continue

            status = "scraped" if tid in scraped_set else ("partial" if tid in partial_set else ("failed" if tid in failed_set else "pending"))
            ts = tests_status.get(tid, {})
            file_path = f"data/tests/{tid}.json"
            file_size = Path(file_path).stat().st_size if Path(file_path).exists() else None

            sql = """INSERT INTO tests (test_id, series_slug, title, status, has_questions, has_answers, has_solutions, has_analysis, last_attempted_at, file_path, file_size_bytes, updated_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())
                     ON CONFLICT(test_id) DO UPDATE SET
                       status=excluded.status, has_questions=excluded.has_questions,
                       has_answers=excluded.has_answers, has_solutions=excluded.has_solutions,
                       has_analysis=excluded.has_analysis, last_attempted_at=excluded.last_attempted_at,
                       file_path=excluded.file_path, file_size_bytes=excluded.file_size_bytes,
                       updated_at=unixepoch()"""
            d1_query(env, sql, [
                tid, test.get("_slug", ""), test.get("title", ""),
                status,
                1 if ts.get("has_questions") or tid in scraped_set else 0,
                1 if tid in scraped_set else 0,
                1 if tid in scraped_set else 0,
                1 if tid in scraped_set else 0,
                int(ts.get("last_attempted_at", 0)) if ts.get("last_attempted_at") else None,
                file_path if file_path else None,
                file_size,
            ])

    # 3. Sync runs (max 10 rows)
    for r in progress.get("run_history", [])[-3:]:
        sql = """INSERT INTO runs (started_at, ended_at, time_minutes, tests_scraped, status)
                 VALUES (?, ?, ?, ?, 'completed')
                 ON CONFLICT(id) DO NOTHING"""
        d1_query(env, sql, [int(r.get("start", 0)), int(r.get("end", 0)),
                           r.get("time_minutes", 0), r.get("tests_scraped", 0)])

    print(f"  ✓ D1 sync complete ({len(only_changed) if only_changed else 0} tests synced)")
    return True


if __name__ == "__main__":
    progress = json.loads(PROGRESS_FILE.read_text())
    sync(progress)
