"""Config — paths, constants, and the 23 tb-pro series list."""
from pathlib import Path

API_BASE = "https://api.repeatermock.com"
REPO_ROOT = Path(__file__).parent.parent
COOKIES_FILE = REPO_ROOT / "cookies" / "account_pro.json"
PROGRESS_FILE = REPO_ROOT / "data" / "progress.json"
TESTS_DIR = REPO_ROOT / "data" / "tests"
SUBMIT_FORMAT_FILE = REPO_ROOT / "data" / "submit_format.json"
REFRESH_EVERY_N_TESTS = 8
TARGET_PER_TEST_SECONDS = 3
START_MIN_INTERVAL = 0.5
PRO_TRIAL_HOURS = 24

TARGET_SERIES = [
    {"slug": "ssc-cgl", "name": "SSC CGL 2026 (Tier I & II)"},
    {"slug": "rrb-group-d", "name": "RRB Group D 2025-26"},
    {"slug": "ssc-maths-previous-year-questions", "name": "SSC Maths PYP (20k+)"},
    {"slug": "ssc-reasoning-previous-year-questions", "name": "SSC Reasoning PYP"},
    {"slug": "ssc-chsl", "name": "SSC CHSL 2026"},
    {"slug": "ssc-english-previous-year-questions", "name": "SSC English PYP"},
    {"slug": "ssc-mts", "name": "SSC MTS & Havaldar 2026"},
    {"slug": "ssc-gk-previous-year-questions", "name": "SSC GK PYP"},
    {"slug": "ssc-stenographer", "name": "SSC Stenographer 2026"},
    {"slug": "ssc-cpo-ranker", "name": "SSC CPO Rankers 2025"},
    {"slug": "ssc-selection-post", "name": "SSC Selection Post Phase 14 2026"},
    {"slug": "ssc-cpo", "name": "SSC CPO 2026 (Tier I & II)"},
    {"slug": "ssc-chsl-previous", "name": "SSC CHSL 2025"},
    {"slug": "ssc-cpo-previous", "name": "SSC CPO 2025 (DP SI & CAPF)"},
    {"slug": "ssc-je-ce", "name": "SSC JE Civil 2026"},
    {"slug": "ssc-mts-previous", "name": "SSC MTS 2025"},
    {"slug": "west-bengal-group-c", "name": "WB SSC Group C & D 2025"},
    {"slug": "rrb-maths-previous-year-questions", "name": "RRB Maths PYP"},
    {"slug": "rrb-reasoning-previous-year-questions", "name": "RRB Reasoning PYP"},
    {"slug": "rrb-gk-previous-year-questions", "name": "RRB GK PYP"},
    {"slug": "rrb-general-science-previous-year-questions", "name": "RRB GS PYP"},
    {"slug": "general-knowledge-ssc-railways-competitive-exams", "name": "Ace GK — SSC/Railways"},
    {"slug": "ssc-railways-polity", "name": "Polity Master Pack"},
    {"slug": "ssc-gd-constable", "name": "SSC GD Constable 2026"},
]
