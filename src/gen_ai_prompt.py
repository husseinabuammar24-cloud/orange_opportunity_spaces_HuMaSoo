import json
import logging
import os
from typing import List
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, Field, field_validator
from rapidfuzz import fuzz, process

# pip install groq python-dotenv pydantic rapidfuzz
# Setup Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load Environment Variables from project root .env
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set. Please set it in your WSL session.")

client = Groq(api_key=GROQ_API_KEY)
models = ["qwen/qwen3.6-27b", "meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]
MODEL_ID = "openai/gpt-oss-120b"


# ==========================================
# 1. PYDANTIC SCHEMAS FOR STRICT TYPING
# ==========================================


class TechnologyExtract(BaseModel):
    rank: int
    technology_name: str
    rationale: str
    source_article_ids: List[str] = Field(default_factory=list)

    @field_validator("source_article_ids", mode="before")
    @classmethod
    def ensure_list(cls, v):
        """Converts raw string, null, or invalid single values into a valid list."""
        if isinstance(v, str):
            return [v]
        if v is None:
            return []
        return v


class Step1Response(BaseModel):
    domain: str
    top_5_emerging_technologies: List[TechnologyExtract]


# ==========================================
# 2. STEP 1: EXTRACT TECH & SOURCE IDs
# ==========================================

STEP1_SYSTEM_PROMPT = """You are an expert technology foresight analyst specializing in domain innovation mapping.
Your task is to analyze a list of articles (provided as JSON with ID and Title) and identify the top 5 hot, emerging technologies.

Rules:
1. Focus strictly on specific, actionable technologies (e.g., "Sodium-Ion Batteries", not generic "Clean Energy").
2. Ensure all 5 technologies belong strictly to the target domain provided.
3. Base your selection on frequency, market buzz, and operational novelty implied by the titles.
4. For each identified technology, include the `source_article_ids` array containing exact article IDs from the input that support it.
5. Output your response ONLY as a JSON object adhering strictly to the schema below.

Expected JSON Schema:
{
  "domain": "string",
  "top_5_emerging_technologies": [
    {
      "rank": 1,
      "technology_name": "string",
      "rationale": "Brief 1-sentence explanation.",
      "source_article_ids": ["art_01", "art_02"]
    }
  ]
}
"""


def extract_technologies(domain: str, raw_articles: list[dict]) -> dict:
    """Sends light article payloads (ID + Title) to Step 1 and returns validated JSON."""
    logging.info("Executing Step 1: Extracting Top Technologies...")

    # Lighten input payload to save tokens
    articles_payload = [
        {"id": a["id"], "title": a["title"]} for a in raw_articles
    ]

    user_content = f"Target Domain: {domain}\n\nArticles List:\n{json.dumps(articles_payload, indent=2)}"

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

    # Validate schema using Pydantic
    validated_model = Step1Response.model_validate_json(raw_json_str)
    return validated_model.model_dump()


# ==========================================
# 3. DEFENSIVE ID RESOLUTION & RAPIDFUZZ
# ==========================================


def resolve_and_filter_articles(
    step1_output: dict,
    raw_articles: list[dict],
    fuzzy_threshold: float = 70.0,
) -> tuple[dict, list[dict]]:
    """Resolves IDs via Set Intersection first, falling back to RapidFuzz title-matching

    if LLM hallucinates or omits valid IDs.
    """
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

        # 1. Direct Set Intersection Validation
        valid_ids = list(set(raw_ids).intersection(valid_ids_set))

        # Log hallucinated IDs if present
        hallucinated_ids = set(raw_ids) - valid_ids_set
        if hallucinated_ids:
            logging.warning(
                f"LLM generated invalid IDs for '{tech_name}': {hallucinated_ids}"
            )

        # 2. RapidFuzz Fallback if direct ID lookup failed
        if not valid_ids:
            logging.info(
                f"Attempting RapidFuzz title fallback for tech: '{tech_name}'..."
            )
            match_result = process.extractOne(
                tech_name, all_titles, scorer=fuzz.WRatio
            )

            if match_result and match_result[1] >= fuzzy_threshold:
                matched_title, score, _ = match_result
                matched_id = title_to_id_map[matched_title]
                valid_ids.append(matched_id)
                logging.info(
                    f"RapidFuzz matched '{tech_name}' -> '{matched_title}' (ID: {matched_id}, Score: {score:.1f})"
                )
            else:
                logging.warning(
                    f"No fuzzy match found above threshold {fuzzy_threshold}% for '{tech_name}'"
                )

        # Sync resolved IDs back to Step 1 payload
        tech["source_article_ids"] = valid_ids
        collected_valid_ids.update(valid_ids)

    # Filter raw article dictionaries by matched IDs
    filtered_articles = [
        valid_id_map[aid]
        for aid in collected_valid_ids
        if aid in valid_id_map
    ]

    # Global safety net: Avoid sending zero articles to Step 2
    if not filtered_articles and raw_articles:
        logging.error(
            "Global resolution failed. Defaulting to all articles for Step 2."
        )
        filtered_articles = raw_articles

    logging.info(
        f"Filtered input: Passing {len(filtered_articles)} of {len(raw_articles)} full articles to Step 2."
    )
    return step1_output, filtered_articles


# ==========================================
# 4. STEP 2: BUILD OPPORTUNITY SPACE
# ==========================================

STEP2_SYSTEM_PROMPT = """You are a senior strategic analyst creating an Opportunity Space for emerging technologies.
Analyze the provided article contents and URLs to evaluate the target technologies across key strategic dimensions.

Rules:
1. Only extract signals and facts explicitly present in the provided article content.
2. Ensure exact URL links from the input are preserved under the relevant signal categories.
3. Provide objective scoring (1-10 scale) based on signal density and immediacy in the sources.
4. Return ONLY valid JSON adhering strictly to the provided schema.

Expected JSON Schema:
{
  "opportunity_space": [
    {
      "technology_name": "string",
      "overview_definition": "2-3 sentence clear, high-level technical overview",
      "signals_and_sources": {
        "regulation": [{"url": "string", "insight": "string"}],
        "buying_signals": [{"url": "string", "insight": "string"}],
        "market_trends": [{"url": "string", "insight": "string"}]
      },
      "use_cases_and_value_drivers": [
        {
          "use_case": "string",
          "value_driver": "e.g., 40% cost reduction, zero emissions"
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
  ]
}
"""


def generate_opportunity_space(
    domain: str, step1_result: dict, filtered_articles: list[dict]
) -> dict:
    """Sends sanitized output and filtered full articles to generate opportunity space."""
    logging.info("Executing Step 2: Building Opportunity Space...")

    # Format filtered articles cleanly
    articles_formatted = ""
    for article in filtered_articles:
        articles_formatted += f"---\nID: {article['id']}\nURL: {article['url']}\nContent: {article['content']}\n\n"

    user_content = (
        f"Target Domain: {domain}\n\n"
        f"Target Emerging Technologies:\n{json.dumps(step1_result, indent=2)}\n\n"
        f"Filtered Articles Data:\n{articles_formatted}"
    )

    response = client.chat.completions.create(
        model=MODEL_ID,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": STEP2_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )

    return json.loads(response.choices[0].message.content)


# ==========================================
# 5. MAIN PIPELINE EXECUTION
# ==========================================

if __name__ == "__main__":
    DOMAIN = "Sustainability"

    with open('./data/sustainability_signals.json', 'r') as file:
        data = json.load(file)


    # Input dataset (including deliberate LLM edge cases like art_03)
    RAW_ARTICLES = [{'id': article['id'], 'title': article['title'], 'url': article['url'], 'content': article['body']} for article in data['articles']['results']
    ]
    try:
        # Step 1: Extract Technologies
        step1_raw = extract_technologies(DOMAIN, RAW_ARTICLES)

        # Intermediate Step: Defensive Filtering & RapidFuzz Fallback
        step1_sanitized, filtered_articles = resolve_and_filter_articles(
            step1_raw, RAW_ARTICLES
        )

        print("\n=== STEP 1 SANITIZED OUTPUT ===")
        print(json.dumps(step1_sanitized, indent=2))

        # Step 2: Build Opportunity Space
        step2_final = generate_opportunity_space(
            DOMAIN, step1_sanitized, filtered_articles
        )

        print("\n=== STEP 2 FINAL OPPORTUNITY SPACE ===")
        print(json.dumps(step2_final, indent=2))

    except Exception as e:
        logging.error(f"Pipeline execution error: {e}", exc_info=True)