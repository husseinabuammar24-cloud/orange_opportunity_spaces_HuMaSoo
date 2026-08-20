import json
import logging
import os
import sqlite3
import time
from typing import List

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, field_validator
from rapidfuzz import fuzz, process

# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set.")

client = Groq(api_key=GROQ_API_KEY)
MODEL_ID = "openai/gpt-oss-120b"


# ==========================================
# 1. PYDANTIC SCHEMAS
# ==========================================


class TechnologyExtract(BaseModel):
    rank: int = Field(default=1) # Defaults to 1 if the LLM omits it
    technology_name: str
    rationale: str = Field(default="")
    source_article_ids: List[str] = Field(default_factory=list)

    @field_validator("source_article_ids", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if isinstance(v, str):
            return [v]
        if v is None:
            return []
        return v

class Step1Response(BaseModel):
    domain: str
    top_5_emerging_technologies: List[TechnologyExtract]


# ==========================================
# 2. STEP 1: EXTRACT TECHNOLOGIES
# ==========================================

STEP1_SYSTEM_PROMPT = """You are an expert technology foresight analyst specializing in domain innovation mapping.
Your task is to analyze a list of articles (provided as JSON with ID and Title) and identify the top 5 hot, emerging technologies.

If you output any key other than "domain" or "top_5_emerging_technologies", your answer is invalid. 
You MUST follow the exact schema. No alternative keys are allowed.

Rules:
1. Focus strictly on specific, actionable technologies.
2. Ensure all 5 technologies belong strictly to the target domain.
3. Base your selection on frequency, market buzz, and novelty.
4. Include exact article IDs supporting each technology.
5. Output ONLY valid JSON following the schema.
"""


def force_step1_schema(raw_json_str: str) -> dict:
    data = json.loads(raw_json_str)

    # 1. Fix root-level technologies key variations
    if "technologies" in data and "top_5_emerging_technologies" not in data:
        data["top_5_emerging_technologies"] = data.pop("technologies")

    tech_list = data.get("top_5_emerging_technologies", [])

    # 2. Iterate and sanitize item-level keys
    for index, tech in enumerate(tech_list, start=1):
        # Auto-assign rank if missing
        if "rank" not in tech or tech["rank"] is None:
            tech["rank"] = index

        # Fix technology_name key aliases
        if "technology" in tech and "technology_name" not in tech:
            tech["technology_name"] = tech.pop("technology")
        elif "name" in tech and "technology_name" not in tech:
            tech["technology_name"] = tech.pop("name")

        # Fix source_article_ids key aliases
        if "article_ids" in tech and "source_article_ids" not in tech:
            tech["source_article_ids"] = tech.pop("article_ids")
        elif "articles" in tech and "source_article_ids" not in tech:
            tech["source_article_ids"] = tech.pop("articles")

        # Ensure string representations for IDs
        if "source_article_ids" in tech:
            tech["source_article_ids"] = [
                str(aid) for aid in tech["source_article_ids"]
            ]

        # Fix rationale if missing
        if "rationale" not in tech or not tech["rationale"]:
            tech["rationale"] = "Identified from signals."

    # 3. Ensure root domain key exists
    if "domain" not in data:
        data["domain"] = "unknown"

    return data


def extract_technologies(domain: str, raw_articles: list[dict]) -> dict:
    logging.info(f"Executing Step 1: Extracting Top Technologies from {domain}")

    articles_payload = [
        {"id": a["id"], "title": a["title"]} for a in raw_articles
    ]

    # Compact JSON string to conserve token count
    user_content = f"Target Domain: {domain}\n\nArticles:\n{json.dumps(articles_payload, separators=(',', ':'))}"

    response = client.chat.completions.create(
        model=MODEL_ID,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": STEP1_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    raw_json_str = response.choices[0].message.content
    safe_json = force_step1_schema(raw_json_str)
    validated_model = Step1Response.model_validate(safe_json)
    return validated_model.model_dump()


# ==========================================
# 3. DEFENSIVE ID RESOLUTION
# ==========================================


def resolve_and_filter_articles(
    step1_output: dict,
    raw_articles: list[dict],
    fuzzy_threshold: float = 70.0,
):
    valid_id_map = {article["id"]: article for article in raw_articles}
    valid_ids_set = set(valid_id_map.keys())

    title_to_id_map = {
        article["title"]: article["id"] for article in raw_articles
    }
    all_titles = list(title_to_id_map.keys())

    collected_valid_ids = set()

    for tech in step1_output.get("top_5_emerging_technologies", []):
        tech_name = tech.get("technology_name", "")
        raw_ids = tech.get("source_article_ids", [])

        valid_ids = list(set(raw_ids).intersection(valid_ids_set))

        hallucinated_ids = set(raw_ids) - valid_ids_set
        if hallucinated_ids:
            logging.warning(
                f"LLM hallucinated IDs for '{tech_name}': {hallucinated_ids}"
            )

        if not valid_ids:
            match_result = process.extractOne(
                tech_name, all_titles, scorer=fuzz.WRatio
            )
            if match_result and match_result[1] >= fuzzy_threshold:
                matched_title, score, _ = match_result
                valid_ids.append(title_to_id_map[matched_title])
            else:
                logging.warning(f"No fuzzy match found for '{tech_name}'")

        tech["source_article_ids"] = valid_ids
        collected_valid_ids.update(valid_ids)

    filtered_articles = [
        valid_id_map[aid]
        for aid in collected_valid_ids
        if aid in valid_id_map
    ]

    if not filtered_articles:
        filtered_articles = raw_articles

    return step1_output, filtered_articles


# ==========================================
# 4. STEP 2: BATCHED OPPORTUNITY SPACE GENERATION
# ==========================================

STEP2_SINGLE_SYSTEM_PROMPT = """You are a senior strategic analyst evaluating ONE emerging technology.
Analyze the provided article contents and URLs to evaluate the target technology across key dimensions.

Rules:
1. Extract ONLY signals explicitly present in the article content.
2. Preserve exact URLs.
3. Provide objective scoring (1-10).
4. Output ONLY valid JSON for this single technology adhering strictly to the schema below.

Expected Schema:
{
  "technology_name": "string",
  "overview_definition": "2-3 sentence clear technical overview",
  "signals_and_sources": {
    "regulation": [{"url": "string", "insight": "string"}],
    "buying_signals": [{"url": "string", "insight": "string"}],
    "market_trends": [{"url": "string", "insight": "string"}]
  },
  "use_cases_and_value_drivers": [
    {
      "use_case": "string",
      "value_driver": "e.g., 40% cost reduction"
    }
  ],
  "target_audience": {
    "personas": ["string"],
    "verticals": ["string"],
    "geographies": ["string"]
  },
  "scoring": {
    "attractiveness_score": 8,
    "attractiveness_rationale": "string",
    "urgency_score": 7,
    "urgency_rationale": "string"
  }
}
"""


def process_single_technology(
    domain: str, tech_item: dict, target_articles: list[dict]
) -> dict:
    """Processes a single technology against its supporting articles (~1,500 - 2,500 tokens)."""
    tech_name = tech_item["technology_name"]
    logging.info(f"Processing Step 2 for target tech: '{tech_name}'")

    articles_formatted = ""
    for article in target_articles:
        # Truncate content to first 1200 chars to avoid token inflation
        truncated_body = article["content"][:1200]
        articles_formatted += f"ID: {article['id']}\nURL: {article['url']}\nContent: {truncated_body}\n---\n"

    user_content = (
        f"Target Domain: {domain}\n"
        f"Target Technology: {tech_name}\n"
        f"Initial Rationale: {tech_item.get('rationale', '')}\n\n"
        f"Supporting Articles:\n{articles_formatted}"
    )

    response = client.chat.completions.create(
        model=MODEL_ID,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": STEP2_SINGLE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    return json.loads(response.choices[0].message.content)


def generate_opportunity_space(
    domain: str, step1_result: dict, filtered_articles: list[dict]
) -> dict:
    """Map-Reduce Step 2: Processes each technology sequentially with rate-limit throttling."""
    logging.info("Executing Step 2: Building Opportunity Spaces (Batched)...")

    article_lookup = {a["id"]: a for a in filtered_articles}
    opportunity_spaces = []

    technologies = step1_result.get("top_5_emerging_technologies", [])
    
    for index, tech in enumerate(technologies):
        source_ids = tech.get("source_article_ids", [])
        mapped_articles = [
            article_lookup[aid] for aid in source_ids if aid in article_lookup
        ]

        # Safety Fallback: If LLM hallucinated IDs and fuzzy match failed, use top 3 articles
        if not mapped_articles:
            logging.warning(
                f"No valid articles mapped for '{tech.get('technology_name')}'. Falling back to default articles."
            )
            mapped_articles = filtered_articles[:3] if filtered_articles else []

        # Process the single technology
        opp_space = process_single_technology(domain, tech, mapped_articles)
        opportunity_spaces.append(opp_space)

        # Throttle: Sleep for 4 seconds between calls to prevent Groq 429 Rate Limits
        if index < len(technologies) - 1:
            logging.info("Throttling request to respect Groq rate limits...")
            time.sleep(4)

    return {"opportunity_space": opportunity_spaces}


# ==========================================
# 5. INSERT INTO DB TABLES
# ==========================================


def insert_opportunity_space(cursor, opp):
    cursor.execute(
        """
        INSERT INTO opportunity_space (technology_name, overview_definition)
        VALUES (?, ?)
    """,
        (opp["technology_name"], opp["overview_definition"]),
    )
    return cursor.lastrowid


def insert_signals(cursor, opportunity_id, signals):
    for category, items in signals.items():
        for item in items:
            cursor.execute(
                """
                INSERT INTO opportunity_signals (opportunity_id, article_id, signal_type, insight)
                VALUES (?, ?, ?, ?)
            """,
                (
                    opportunity_id,
                    item.get("url", ""),
                    category,
                    item.get("insight", ""),
                ),
            )


def insert_use_cases(cursor, opportunity_id, use_cases):
    for uc in use_cases:
        cursor.execute(
            """
            INSERT INTO use_cases (opportunity_id, use_case, value_driver)
            VALUES (?, ?, ?)
        """,
            (opportunity_id, uc["use_case"], uc["value_driver"]),
        )


def insert_target_audience(cursor, opportunity_id, audience):
    for persona in audience.get("personas", []):
        cursor.execute(
            """
            INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
            VALUES (?, ?, ?, ?)
        """,
            (opportunity_id, persona, None, None),
        )

    for vertical in audience.get("verticals", []):
        cursor.execute(
            """
            INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
            VALUES (?, ?, ?, ?)
        """,
            (opportunity_id, None, vertical, None),
        )

    for geo in audience.get("geographies", []):
        cursor.execute(
            """
            INSERT INTO target_audience (opportunity_id, persona, vertical, geography)
            VALUES (?, ?, ?, ?)
        """,
            (opportunity_id, None, None, geo),
        )


def insert_scoring(cursor, opportunity_id, scoring):
    cursor.execute(
        """
        INSERT INTO scoring (
            opportunity_id, 
            attractiveness_score, 
            attractiveness_rationale, 
            urgency_score, 
            urgency_rationale
        ) VALUES (?, ?, ?, ?, ?)
    """,
        (
            opportunity_id,
            scoring["attractiveness_score"],
            scoring["attractiveness_rationale"],
            scoring["urgency_score"],
            scoring["urgency_rationale"],
        ),
    )


# ==========================================
# 6. MAIN PIPELINE
# ==========================================

if __name__ == "__main__":
    from config import DOMAIN_KEYWORD_MAP

    for DOMAIN in DOMAIN_KEYWORD_MAP.keys():

        conn = sqlite3.connect("./data/signals.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT a.id, a.title, a.url, b.body
            FROM articles a
            JOIN article_bodies b ON a.id = b.article_id
            WHERE a.domain = ?
        """,
            (DOMAIN,),
        )

        rows = cursor.fetchall()

        RAW_ARTICLES = [
            {"id": row[0], "title": row[1], "url": row[2], "content": row[3]}
            for row in rows
        ]

        conn.close()

        if not RAW_ARTICLES:
            logging.info(f"No articles found for domain: {DOMAIN}. Skipping...")
            continue

        try:
            # Step 1: Extract Top Technologies
            step1_raw = extract_technologies(DOMAIN, RAW_ARTICLES)
            step1_sanitized, filtered_articles = resolve_and_filter_articles(
                step1_raw, RAW_ARTICLES
            )

            # Step 2: Batched Execution
            step2_final = generate_opportunity_space(
                DOMAIN, step1_sanitized, filtered_articles
            )

            # Database Insertion
            conn = sqlite3.connect("./data/signals.db")
            cursor = conn.cursor()

            for opp in step2_final["opportunity_space"]:
                opp_id = insert_opportunity_space(cursor, opp)
                insert_signals(
                    cursor, opp_id, opp.get("signals_and_sources", {})
                )
                insert_use_cases(
                    cursor
                )
                insert_target_audience(
                    cursor, opp_id, opp.get("target_audience", {})
                )
                insert_scoring(cursor, opp_id, opp.get("scoring", {}))

            conn.commit()
            conn.close()
            logging.info(f"Successfully processed domain: {DOMAIN}")

        except Exception as e:
            logging.error(f"Pipeline execution error: {e}", exc_info=True)

        time.sleep(10)