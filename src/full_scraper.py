"""Full scraper — Q + A + Sol + Analysis per test. No page.goto."""
import asyncio
import json
import time
from pathlib import Path
from src.config import TESTS_DIR
from src.question_parser import extract_flight_payload, parse_question_objects, clean_question, thorough_unescape
from src.submit_attempt import start_attempt, submit_attempt, RateLimited, AuthExpired


def extract_json_object(payload: str, key: str) -> dict | None:
    search = f'"{key}":{{'
    idx = payload.find(search)
    if idx < 0:
        return None
    start = payload.find('{', idx + len(key) + 2)
    depth = 0; in_str = False; esc = False
    for j in range(start, len(payload)):
        c = payload[j]
        if esc: esc = False; continue
        if c == '\\': esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                try: return json.loads(payload[start:j+1])
                except: return None
    return None


async def scrape_test_full(context, test: dict, cookies: list[dict]) -> dict:
    """Scrape one test: questions + start + submit + solution + analysis."""
    test_id = test["id"]
    slug = test.get("_slug", "")
    base_url = f"https://repeatermock.com/tb-pro/test-series/{slug}/test/{test_id}"
    cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if "repeatermock" in c.get("domain", ""))

    result = {
        "test_id": test_id,
        "title": test.get("title", ""),
        "platform": "tb-pro",
        "slug": slug,
        "series_url": f"https://repeatermock.com/tb-pro/test-series/{slug}",
        "section": test.get("_section", ""),
        "subsection": test.get("_subsection", ""),
        "duration_minutes": test.get("duration", 60),
        "total_marks": test.get("totalMark", 200),
        "question_count": test.get("questionCount", 100),
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "questions": [],
        "answers": {},
        "analysis": {},
        "has_questions": False,
        "has_answers": False,
        "has_analysis": False,
    }

    # 1. Fetch /attempt → questions
    resp = await context.request.get(f"{base_url}/attempt", headers={
        "Accept": "text/html", "Cookie": cookie_str, "Referer": "https://repeatermock.com/"
    })
    html = await resp.text()
    if resp.status == 200 and len(html) > 5000:
        payload = extract_flight_payload(html)
        raw_qs = parse_question_objects(payload)
        result["questions"] = [clean_question(q) for q in raw_qs]
        result["has_questions"] = len(result["questions"]) > 0
        print(f"    ✓ {len(result['questions'])} questions", flush=True)
    else:
        print(f"    ✗ /attempt {resp.status} ({len(html)} bytes)", flush=True)
        return result

    # 2. Start attempt (fast API call — no page.goto)
    started = await start_attempt(context, test_id, cookie_str)
    if not started:
        print(f"    ⚠ Start failed", flush=True)
        return result

    # 3. Submit empty answers
    submitted = await submit_attempt(context, test_id, cookie_str)
    if submitted:
        print(f"    ✓ Submitted", flush=True)
        await asyncio.sleep(1)
    else:
        print(f"    ⚠ Submit failed", flush=True)
        return result

    # 4. Fetch /solution → answers + solutions
    resp = await context.request.get(f"{base_url}/solution", headers={
        "Accept": "text/html", "Cookie": cookie_str, "Referer": "https://repeatermock.com/"
    })
    sol_html = await resp.text()
    if resp.status == 200 and len(sol_html) > 30000:
        sol_payload = extract_flight_payload(sol_html)
        answers_data = extract_json_object(sol_payload, "answersData")
        if answers_data and len(answers_data) > 5:
            for qid, ans in answers_data.items():
                sol = ans.get("sol", {})
                for lang_code, lang_data in sol.items():
                    if isinstance(lang_data, dict) and lang_data.get("value"):
                        lang_data["value"] = thorough_unescape(lang_data["value"])
            result["answers"] = answers_data
            result["has_answers"] = True
            print(f"    ✓ {len(answers_data)} answers + solutions", flush=True)

    # 5. Fetch /analysis → rank, percentile, cutoffs
    resp = await context.request.get(f"{base_url}/analysis", headers={
        "Accept": "text/html", "Cookie": cookie_str, "Referer": "https://repeatermock.com/"
    })
    ana_html = await resp.text()
    if resp.status == 200 and len(ana_html) > 30000:
        ana_payload = extract_flight_payload(ana_html)
        analysis_data = extract_json_object(ana_payload, "analysisData")
        if analysis_data:
            result["analysis"] = analysis_data
            result["has_analysis"] = True
            ts = analysis_data.get("ts", {})
            an = analysis_data.get("analysis", {})
            print(f"    ✓ rank={ts.get('rank')}, percentile={ts.get('percentile')}, avg={an.get('avgMarks')}", flush=True)

    # 6. Save only if fully scraped
    if result["has_questions"] and result["has_answers"] and result["has_analysis"]:
        TESTS_DIR.mkdir(parents=True, exist_ok=True)
        out_file = TESTS_DIR / f"{test_id}.json"
        out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"    ✓ Saved FULL ({out_file.name})", flush=True)
    else:
        missing = []
        if not result["has_questions"]: missing.append("Q")
        if not result["has_answers"]: missing.append("A")
        if not result["has_analysis"]: missing.append("Ana")
        print(f"    ⚠ PARTIAL (missing: {','.join(missing)})", flush=True)

    return result
