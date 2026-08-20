"""
Innovation Radar - Sustainability & Multi-Domain Signal Collector
====================================================
Pulls recent domain-related news articles from NewsAPI.ai (Event Registry)
and stores them directly into a normalized SQLite database for Step 1 of the
Opportunity Discovery Process:
    Signals -> Themes -> Opportunity spaces -> Scoring -> Radar
"""

import time
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from dotenv import load_dotenv

# GLOBAL UNIQUE INTEGER COUNTER
GLOBAL_ID = 0

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from config import (
    MAX_KEYWORDS,
    VERTICAL_KEYWORDS,
    DEFAULT_SUSTAINABILITY_KEYWORDS,
    DEFAULT_CYBERSECURITY_KEYWORDS,
    DEFAULT_SMART_INDUSTRIES_KEYWORDS,
    DEFAULT_CONNECTIVITY_KEYWORDS,
    DEFAULT_CLOUD_KEYWORDS,
    DEFAULT_CX_KEYWORDS,
    DEFAULT_EX_KEYWORDS,
    DEFAULT_DATA_TYPES,
    EUROPEAN_COUNTRIES,
    DOMAIN_KEYWORD_MAP,
)

try:
    from eventregistry import (
        EventRegistry, QueryArticlesIter, QueryItems,
        ReturnInfo, ArticleInfoFlags,
    )
except ImportError:
    sys.exit("Missing dependency. Run: pip install eventregistry python-dotenv --break-system-packages")

load_dotenv(dotenv_path=ROOT / ".env")


#===========================================================
# DB TABLE CREATION
#===========================================================

def create_tables(cursor):
    cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            title TEXT,
            date TEXT,
            url TEXT,
            source_domain TEXT,
            signal_type_guess TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_bodies (
            article_id INTEGER PRIMARY KEY,
            body TEXT,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_verticals (
            id INTEGER,
            vertical TEXT,
            FOREIGN KEY(id) REFERENCES articles(id)
        );
    """)


#===========================================================
# DB INSERT FUNCTIONS
#===========================================================

def insert_article(cursor, signal):
    cursor.execute("""
        INSERT INTO articles (
            domain, title, date, url, source_domain, signal_type_guess
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        signal.get("domain"),
        signal.get("title"),
        signal.get("date"),
        signal.get("url"),
        signal.get("source_domain"),
        signal.get("signal_type_guess")
    ))
    return cursor.lastrowid


def insert_body(cursor, article_id, signal):
    cursor.execute("""
        INSERT INTO article_bodies (
            article_id, body
        ) VALUES (?, ?)
    """, (
        article_id,
        signal.get("body")
    ))


def insert_verticals(cursor, article_id, signal):
    verticals = signal.get("verticals", [])
    for v in verticals:
        cursor.execute("""
            INSERT INTO article_verticals (
                id, vertical
            ) VALUES (?, ?)
        """, (
            article_id,
            v
        ))


#===========================================================
# UTILITIES
#===========================================================

def get_european_location_uris(er):
    uris = []
    for country in EUROPEAN_COUNTRIES:
        uri = er.getLocationUri(country)
        if uri:
            uris.append(uri)
    return uris


def extract_domain(article):
    source_uri = (article.get("source") or {}).get("uri")
    if source_uri:
        return source_uri
    url = article.get("url") or ""
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def tag_verticals(text):
    text_lower = text.lower()
    return [v for v, kws in VERTICAL_KEYWORDS.items() if any(k in text_lower for k in kws)]


def classify_signal_type(title, categories):
    cat_text = " ".join(categories).lower()
    combined = f"{(title or '').lower()} {cat_text}"

    if any(w in combined for w in ["regulation", "policy", "law", "directive", "compliance", "mandate"]):
        return "regulation"
    if any(w in combined for w in ["deal", "partnership", "acquire", "acquisition", "invest", "funding", "contract"]):
        return "market move"
    if any(w in combined for w in ["launch", "release", "unveil", "pilot", "rollout"]):
        return "technology maturity"
    if any(w in combined for w in ["survey", "report", "study", "forecast", "market size", "growing"]):
        return "trend"
    return "unclassified"


def cap_keywords(keywords, limit=MAX_KEYWORDS):
    kept, dropped, total_words = [], [], 0
    for kw in keywords:
        wc = len(kw.split())
        if total_words + wc <= limit:
            kept.append(kw)
            total_words += wc
        else:
            dropped.append(kw)
    return kept


#===========================================================
# FETCH SIGNALS
#===========================================================

def fetch_signals(api_key, keywords, days, lang, max_articles, domain_label,
                  europe_only=True, data_types=None, full_body=False, category=None):

    keywords = cap_keywords(keywords)
    er = EventRegistry(apiKey=api_key, allowUseOfArchive=True)
    date_start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    if domain_label == "cloud":
        category = "Technology"
    elif domain_label == "ex":
        category = "Business"

    query_kwargs = dict(
        keywords=QueryItems.OR(keywords),
        lang=lang,
        dateStart=date_start,
        categoryUri=er.getCategoryUri(category) if category else None,
        isDuplicateFilter="skipDuplicates",
        ignoreSourceGroupUri="paywall/paywalled_sources",
        dataType=data_types or DEFAULT_DATA_TYPES,
    )

    if europe_only:
        loc_uris = get_european_location_uris(er)
        if loc_uris:
            query_kwargs["sourceLocationUri"] = loc_uris

    q = QueryArticlesIter(**query_kwargs)

    return_info = ReturnInfo(
        articleInfo=ArticleInfoFlags(
            bodyLen=-1 if full_body else 300,
            concepts=False,
            categories=False,
            sentiment=False,
            socialScore=False,
        )
    )

    signals = []
    for art in q.execQuery(er, sortBy="date", maxItems=max_articles, returnInfo=return_info):

        global GLOBAL_ID
        GLOBAL_ID += 1

        enriched = dict(art)

        # FIX: ensure body is always a string
        body = art.get("body")
        if isinstance(body, list):
            body = "\n".join(body)
        enriched["body"] = body

        enriched["id"] = GLOBAL_ID
        enriched["domain"] = domain_label
        enriched["source_domain"] = extract_domain(art)
        enriched["verticals"] = tag_verticals(f"{art.get('title', '')} {body}")
        enriched["signal_type_guess"] = classify_signal_type(art.get("title"), [])

        signals.append(enriched)

    return signals


#===========================================================
# RUN ALL DOMAINS (DIRECT TO DB)
#===========================================================

def run_all_domains(db_path="./data/signals.db"):
    api_key = os.environ.get("NEWSAPI_AI_KEY")
    if not api_key:
        sys.exit("NEWSAPI_AI_KEY not found. Add it to your .env file.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    create_tables(cursor)

    for domain, keywords in DOMAIN_KEYWORD_MAP.items():
        print(f"\n=== Fetching domain: {domain} ===")

        signals = fetch_signals(
            api_key=api_key,
            keywords=keywords,
            days=30,
            lang="eng",
            max_articles=200,
            domain_label=domain,
            europe_only=True,
            data_types=DEFAULT_DATA_TYPES,
            full_body=False,
            category=domain
        )

        for signal in signals:
            article_id = insert_article(cursor, signal)
            insert_body(cursor, article_id, signal)
            insert_verticals(cursor, article_id, signal)
        print(f"Inserted {len(signals)} signals for domain '{domain}'. Waiting 10 seconds...")
        time.sleep(10)

    conn.commit()
    conn.close()

    print(f"\nAll domains inserted directly into database: {db_path}")


#===========================================================
# ENTRY POINT
#===========================================================

if __name__ == "__main__":
    run_all_domains()
