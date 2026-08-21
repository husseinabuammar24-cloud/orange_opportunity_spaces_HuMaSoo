import argparse
import json
import logging
import json_repair
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from pydantic import BaseModel, ConfigDict, Field, field_validator
from rapidfuzz import fuzz, process

from config import DOMAIN_KEYWORD_MAP

# ==========================================
# 0. CONFIGURATION & INITIALIZATION
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    raise ValueError("HF_TOKEN environment variable is not set in .env")

# Must be a model actually served by an Inference Provider enabled on your
# HF account. "Qwen/Qwen2.5-1.5B-Instruct" was rejected with
# `model_not_supported` because no enabled provider serves it via the
# router. Qwen2.5-Coder-32B-Instruct is served and known to work here.
# If you need a different model, check availability first at:
# https://huggingface.co/settings/inference-providers
# Overridable via HF_MODEL_ID so a bad model choice doesn't require a code
# change to fix.
MODEL_ID = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-Coder-32B-Instruct")

# Don't pin `model=` on the client itself — it's passed per-call in
# safe_api_call() below. Binding it in both places can cause the router
# to resolve a provider differently than expected.
client = InferenceClient(api_key=HF_TOKEN)

DB_PATH = "./data/New_signals.db"

# Fixed retry delay is wasteful (3 x 10s = 30s per failed call before giving
# up) and identical whether the error was a network blip or a hard failure.
# Use exponential backoff for genuinely transient errors instead.
RETRY_BASE_DELAY_SECONDS = 5.0
DOMAIN_SLEEP_SECONDS = float(os.getenv("DOMAIN_SLEEP_SECONDS", "30"))

# Status codes that will NEVER succeed on retry with the same request/config
# (bad model, bad auth, exhausted credits, malformed request). Burning three
# retries x exponential backoff on these just delays the inevitable failure.
# 429 (rate limit) is deliberately excluded — that one is worth retrying.
NON_RETRYABLE_STATUS_CODES = {400, 401, 402, 403, 404, 422}

# Codes above that also mean "don't bother with the next domain either" —
# they're about the account/model/config, not this particular request, so
# every subsequent domain would fail identically.
FATAL_PIPELINE_STATUS_CODES = {400, 401, 402, 403}


class FatalPipelineError(RuntimeError):
    """Raised when an error means the whole run should stop, not just the
    current domain (e.g. exhausted HF credits, invalid model, bad auth)."""


# ==========================================
# 1. PYDANTIC SCHEMAS
# ==========================================


class TechnologyExtract(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    rank: int
    technology_name: str
    rationale: str = Field(default="")
    source_article_ids: List[str] = Field(default_factory=list)

    @field_validator("source_article_ids", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, (str, int, float)):
            return [str(v)]
        if isinstance(v, list):
            return [str(item) for item in v]
        return v

class Step1Response(BaseModel):
    domain: str
    top_5_emerging_technologies: List[TechnologyExtract]


# ==========================================
# 2. PROMPTS
# ==========================================

STEP1_SYSTEM_PROMPT = """You are an expert technology foresight analyst.
Your task is to analyze articles (JSON with ID and Title) and identify top 5 hot technologies.

CRITICAL REQUIREMENT: Output your entire response as a single valid JSON object following this exact schema:
{
  "domain": "target_domain",
  "top_5_emerging_technologies": [
    {
      "rank": 1,
      "technology_name": "Name",
      "rationale": "Reasoning",
      "source_article_ids": ["1", "2"]
    }
  ]
}
"""

STEP2_SYSTEM_PROMPT = """You are a strategic analyst mapping technology opportunities.
Return a single valid JSON object matching this schema:
{
  "opportunity_space": [
    {
      "technology_name": "Name",
      "overview_definition": "Description",
      "signals_and_sources": {
        "market_trends": [{"url": "URL", "insight": "Insight"}],
        "buying_signals": [{"url": "URL", "insight": "Insight"}],
        "regulation": [{"url": "URL", "insight": "Insight"}]
      },
      "use_cases_and_value_drivers": [
        {"use_case": "Case", "value_driver": "Value"}
      ],
      "target_audience": {
        "personas": ["Persona"],
        "verticals": ["Vertical"],
        "geographies": ["Geography"]
      },
      "scoring": {
        "attractiveness_score": 8.0,
        "attractiveness_rationale": "Reason",
        "urgency_score": 7.0,
        "urgency_rationale": "Reason"
      }
    }
  ]
}
"""


# ==========================================
# 3. JSON REPAIR UTILITIES
# ==========================================

def repair_json(raw_json_str: str, fallback: dict) -> dict:
    try:
        data = json_repair.loads(raw_json_str)
        if not isinstance(data, dict):
            return fallback
        return data
    except Exception as e:
        logging.error(f"JSON repair failed: {e}")
        return fallback


def normalize_step1(data: dict) -> dict:
    if "domain" not in data:
        data["domain"] = "unknown"

    techs = data.get("top_5_emerging_technologies") or data.get("technologies") or []
    normalized = []

    for idx, tech in enumerate(techs, start=1):
        t = {}
        t["rank"] = tech.get("rank", idx)
        t["technology_name"] = (
            tech.get("technology_name")
            or tech.get("technology")
            or tech.get("name")
            or "Unknown Technology"
        )
        t["rationale"] = tech.get("rationale") or tech.get("description") or "No rationale provided."

        raw_ids = tech.get("source_article_ids") or tech.get("article_ids") or []
        if isinstance(raw_ids, (str, int, float)):
            raw_ids = [str(raw_ids)]
        elif isinstance(raw_ids, list):
            raw_ids = [str(x) for x in raw_ids]

        t["source_article_ids"] = raw_ids
        normalized.append(t)

    data["top_5_emerging_technologies"] = normalized
    return data


def normalize_step2(data: dict) -> dict:
    if "opportunity_space" not in data or not isinstance(data["opportunity_space"], list):
        return {"opportunity_space": []}

    cleaned_list = []
    for opp in data["opportunity_space"]:
        if not isinstance(opp, dict):
            continue

        opp.setdefault("technology_name", "Unknown Technology")
        opp.setdefault("overview_definition", "No overview provided.")
        opp.setdefault("signals_and_sources", {})
        opp.setdefault("use_cases_and_value_drivers", [])
        opp.setdefault("target_audience", {"personas": [], "verticals": [], "geographies": []})
        opp.setdefault("scoring", {
            "attractiveness_score": 0,
            "attractiveness_rationale": "No rationale.",
            "urgency_score": 0,
            "urgency_rationale": "No rationale."
        })

        cleaned_list.append(opp)

    return {"opportunity_space": cleaned_list}


# ==========================================
# 4. SAFE API CALL — CHAT COMPLETIONS
# ==========================================

def _get_status_code(exc: Exception) -> Optional[int]:
    """Best-effort extraction of an HTTP status code from huggingface_hub /
    httpx exceptions, which expose it differently depending on error type."""
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if code is not None:
            return code
    return getattr(exc, "status_code", None)


def safe_api_call(messages: list, max_tokens: int = 4096, retries: int = 3) -> str:
    last_exc: Optional[Exception] = None

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_ID,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            # `message` is a ChatCompletionOutputMessage object, not a dict —
            # use attribute access, not subscripting.
            return response.choices[0].message.content
        except Exception as e:
            last_exc = e
            status = _get_status_code(e)

            if status in NON_RETRYABLE_STATUS_CODES:
                msg = f"Non-retryable API error (HTTP {status}): {e}"
                logging.error(msg)
                if status in FATAL_PIPELINE_STATUS_CODES:
                    raise FatalPipelineError(msg) from e
                raise RuntimeError(msg) from e

            delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
            logging.warning(
                f"API attempt {attempt + 1}/{retries} failed: {e}. "
                f"Retrying in {delay:.0f}s..."
            )
            if attempt < retries - 1:
                time.sleep(delay)

    raise RuntimeError(f"API completion failed after {retries} attempts.") from last_exc


# ==========================================
# 5. STEP 1 EXTRACTION
# ==========================================

def extract_technologies(domain: str, raw_articles: List[dict]) -> dict:
    logging.info(f"Executing Step 1: Extracting Top Technologies from {domain}")

    articles_payload = [{"id": a["id"], "title": a["title"]} for a in raw_articles[:30]]
    user_content = f"Target Domain: {domain}\n\nArticles:\n{json.dumps(articles_payload, indent=2)}"

    messages = [
        {"role": "system", "content": STEP1_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw_json_str = safe_api_call(messages)
    repaired = repair_json(raw_json_str, fallback={"domain": domain, "top_5_emerging_technologies": []})
    normalized = normalize_step1(repaired)

    validated = Step1Response.model_validate(normalized)
    return validated.model_dump()


# ==========================================
# 6. STEP 1 → ARTICLE RESOLUTION
# ==========================================

def resolve_and_filter_articles(
    step1_output: dict, raw_articles: List[dict], fuzzy_threshold: float = 70.0
    ) -> Tuple[dict, List[dict]]:

    valid_id_map = {article["id"]: article for article in raw_articles}
    valid_ids_set = set(valid_id_map.keys())

    title_to_id_map = { article["title"]: article["id"] for article in raw_articles }
    all_titles = list(title_to_id_map.keys())

    collected_valid_ids = set()

    for tech in step1_output.get("top_5_emerging_technologies", []):
        tech_name = tech.get("technology_name", "")
        raw_ids = tech.get("source_article_ids", [])

        valid_ids = list(set(raw_ids).intersection(valid_ids_set))

        hallucinated_ids = set(raw_ids) - valid_ids_set
        if hallucinated_ids:
            logging.warning( f"LLM hallucinated IDs for '{tech_name}': {hallucinated_ids}" )

        if not valid_ids and all_titles:
            match_result = process.extractOne(tech_name, all_titles, scorer=fuzz.WRatio)
            if match_result and match_result[1] >= fuzzy_threshold:
                matched_title, score, _ = match_result
                valid_ids.append(title_to_id_map[matched_title])
            else:
                logging.warning(f"No fuzzy match found for '{tech_name}'")

        tech["source_article_ids"] = valid_ids
        collected_valid_ids.update(valid_ids)

    filtered_articles = [ valid_id_map[aid] for aid in collected_valid_ids if aid in valid_id_map ]

    if not filtered_articles:
        filtered_articles = raw_articles[:10]

    return step1_output, filtered_articles[:10]


# ==========================================
# 7. STEP 2 GENERATION
# ==========================================

def generate_opportunity_space(domain: str, step1_result: dict, filtered_articles: List[dict]) -> dict:
    logging.info(f"Executing Step 2: Building Opportunity Space for {domain}...")

    articles_formatted = "".join(
        f"---\nID: {a['id']}\nURL: {a['url']}\nContent: {a['content'][:600]}...\n\n"
        for a in filtered_articles
    )

    user_content = (
        f"Target Domain: {domain}\n\n"
        f"Technologies:\n{json.dumps(step1_result, indent=2)}\n\n"
        f"Articles:\n{articles_formatted}"
    )

    messages = [
        {"role": "system", "content": STEP2_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    raw_json_str = safe_api_call(messages)
    repaired = repair_json(raw_json_str, fallback={"opportunity_space": []})
    normalized = normalize_step2(repaired)

    return normalized


# ==========================================
# 8. DATABASE OPERATIONS
# ==========================================

SIGNAL_TYPE_MAP = {
    "market_drivers": "market_trends",
    "market_trends": "market_trends",
    "buying_signals": "buying_signals",
    "buying_signal": "buying_signals",
    "regulation": "regulation",
    "regulations": "regulation",
    "regulatory": "regulation"
}

def init_db(db_path: str = DB_PATH):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # NOTE: `domain` was previously missing from this table entirely,
        # meaning saved opportunity spaces had no way to be traced back to
        # the domain (sustainability, cybersecurity, ...) they came from.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_space (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT,
                technology_name TEXT,
                overview_definition TEXT
            )
        """)
        # Tracks per-domain pipeline progress so a crashed/interrupted run
        # (see the repeated Ctrl-C restarts) can resume instead of
        # reprocessing and re-inserting domains that already succeeded.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_state (
                domain TEXT PRIMARY KEY,
                status TEXT,
                updated_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER,
                article_id TEXT,
                signal_type TEXT,
                insight TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS use_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER,
                use_case TEXT,
                value_driver TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS target_audience (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER,
                persona TEXT,
                vertical TEXT,
                geography TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scoring (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id INTEGER,
                attractiveness_score REAL,
                attractiveness_rationale TEXT,
                urgency_score REAL,
                urgency_rationale TEXT
            )
        """)

        # Migration for DBs created before `domain` existed on this table.
        cursor.execute("PRAGMA table_info(opportunity_space)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if "domain" not in existing_cols:
            cursor.execute("ALTER TABLE opportunity_space ADD COLUMN domain TEXT")

        conn.commit()


def get_domain_status(db_path: str, domain: str) -> Optional[str]:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM pipeline_state WHERE domain = ?", (domain,))
        row = cursor.fetchone()
        return row[0] if row else None


def set_domain_status(db_path: str, domain: str, status: str):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pipeline_state (domain, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
        """, (domain, status, datetime.now(timezone.utc).isoformat()))
        conn.commit()


def fetch_raw_articles(db_path: str, domain: str) -> List[dict]:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.title, a.url, b.body
            FROM articles a
            JOIN article_bodies b ON a.id = b.article_id
            WHERE a.domain = ?
        """, (domain,))
        rows = cursor.fetchall()

    return [
        {"id": str(row[0]), "title": row[1], "url": row[2], "content": row[3]}
        for row in rows
    ]


def save_opportunity_data(db_path: str, domain: str, opportunity_space_list: List[dict]):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for opp in opportunity_space_list:
            if not isinstance(opp, dict):
                continue

            cursor.execute("""
                INSERT INTO opportunity_space (domain, technology_name, overview_definition)
                VALUES (?, ?, ?)
            """, (domain, opp.get("technology_name"), opp.get("overview_definition")))
            opp_id = cursor.lastrowid

            signals = opp.get("signals_and_sources", {})
            if isinstance(signals, dict):
                for raw_category, items in signals.items():
                    normalized_signal_type = SIGNAL_TYPE_MAP.get(raw_category.lower(), "market_trends")
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                cursor.execute("""
                                    INSERT INTO opportunity_signals (opportunity_id, article_id, signal_type, insight)
                                    VALUES (?, ?, ?, ?)
                                """, (
                                    opp_id,
                                    item.get("url"),
                                    normalized_signal_type,
                                    item.get("insight")
                                ))

            for uc in opp.get("use_cases_and_value_drivers", []):
                if isinstance(uc, dict):
                    cursor.execute("""
                        INSERT INTO use_cases (opportunity_id, use_case, value_driver)
                        VALUES (?, ?, ?)
                    """, (opp_id, uc.get("use_case"), uc.get("value_driver")))

            audience = opp.get("target_audience", {})
            if isinstance(audience, dict):
                for persona in audience.get("personas", []):
                    cursor.execute("""
                        INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
                        VALUES (?, ?, ?, ?)
                    """, (opp_id, persona, None, None))
                for vertical in audience.get("verticals", []):
                    cursor.execute("""
                        INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
                        VALUES (?, ?, ?, ?)
                    """, (opp_id, None, vertical, None))
                for geo in audience.get("geographies", []):
                    cursor.execute("""
                        INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
                        VALUES (?, ?, ?, ?)
                    """, (opp_id, None, None, geo))

            scoring = opp.get("scoring", {})
            if isinstance(scoring, dict):
                cursor.execute("""
                    INSERT INTO scoring (
                        opportunity_id, attractiveness_score, attractiveness_rationale, urgency_score, urgency_rationale
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    opp_id,
                    scoring.get("attractiveness_score"),
                    scoring.get("attractiveness_rationale"),
                    scoring.get("urgency_score"),
                    scoring.get("urgency_rationale")
                ))

        conn.commit()


# ==========================================
# 9. MAIN PIPELINE
# ==========================================

def parse_args():
    parser = argparse.ArgumentParser(description="Run the opportunity-space generation pipeline.")
    parser.add_argument(
        "--domains",
        type=str,
        default=None,
        help="Comma-separated subset of domains to run (default: all domains in DOMAIN_KEYWORD_MAP).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess domains even if they already succeeded in a previous run.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=DB_PATH,
        help=f"Path to the SQLite database (default: {DB_PATH}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = args.db_path

    init_db(db_path)

    domains_to_run = list(DOMAIN_KEYWORD_MAP.keys())
    if args.domains:
        requested = {d.strip() for d in args.domains.split(",") if d.strip()}
        unknown = requested - set(domains_to_run)
        if unknown:
            logging.warning(f"Ignoring unknown domain(s) not in DOMAIN_KEYWORD_MAP: {unknown}")
        domains_to_run = [d for d in domains_to_run if d in requested]

    for domain in domains_to_run:
        if not args.force and get_domain_status(db_path, domain) == "success":
            logging.info(f"Skipping domain '{domain}' — already completed in a previous run (use --force to redo).")
            continue

        logging.info(f"--- Starting Processing for Domain: {domain} ---")

        raw_articles = fetch_raw_articles(db_path, domain)
        if not raw_articles:
            logging.warning(f"No articles found for domain '{domain}'. Skipping...")
            continue

        try:
            step1_raw = extract_technologies(domain, raw_articles)

            if not step1_raw.get("top_5_emerging_technologies"):
                logging.warning(f"No technologies extracted for domain '{domain}'. Skipping Step 2.")
                set_domain_status(db_path, domain, "failed")
                continue

            step1_sanitized, filtered_articles = resolve_and_filter_articles(step1_raw, raw_articles)
            step2_final = generate_opportunity_space(domain, step1_sanitized, filtered_articles)

            if step2_final.get("opportunity_space"):
                save_opportunity_data(db_path, domain, step2_final["opportunity_space"])
                logging.info(f"Successfully saved Opportunity Space for domain: {domain}")
                set_domain_status(db_path, domain, "success")
            else:
                logging.warning(f"Step 2 produced no opportunity spaces for domain '{domain}'.")
                set_domain_status(db_path, domain, "failed")

        except FatalPipelineError as e:
            # Same model/account/config issue would hit every remaining
            # domain identically (e.g. exhausted credits, bad auth) — stop
            # the whole run now rather than burning retries on each one.
            set_domain_status(db_path, domain, "failed")
            logging.error(f"Fatal pipeline error on domain '{domain}': {e}")
            logging.error("Stopping the run — this error will not resolve by moving to the next domain. "
                           "Fix the underlying issue (credits, auth, or model config) and rerun; "
                           "already-completed domains will be skipped automatically.")
            sys.exit(1)

        except Exception as e:
            logging.error(f"Pipeline execution error for domain {domain}: {e}", exc_info=True)
            set_domain_status(db_path, domain, "failed")

        time.sleep(DOMAIN_SLEEP_SECONDS)

    logging.info("Pipeline run complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Progress so far is saved — rerun to resume from where you left off.")
        sys.exit(130)