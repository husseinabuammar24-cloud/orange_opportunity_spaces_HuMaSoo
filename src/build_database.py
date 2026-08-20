"""
Innovation Radar - Database Schema Creator
==========================================
Creates all normalized tables required for:
- Raw signals (articles, bodies, verticals)
- Opportunity Space (technologies, signals, use cases, audience, scoring)

Run this once to initialize the SQLite database.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("./data/signals.db")


def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    # ---------------------------------------------------------
    # 1. ARTICLES (raw signals metadata)
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # 2. ARTICLE BODIES (full text)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_bodies (
            article_id INTEGER PRIMARY KEY,
            body TEXT,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
    """)

    # ---------------------------------------------------------
    # 3. ARTICLE VERTICALS (1-to-many)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_verticals (
            id INTEGER,
            vertical TEXT,
            FOREIGN KEY(id) REFERENCES articles(id) ON DELETE CASCADE
        );
    """)

    # ---------------------------------------------------------
    # 4. OPPORTUNITY SPACE (root table)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_space (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technology_name TEXT NOT NULL,
            overview_definition TEXT
        );
    """)

    # ---------------------------------------------------------
    # 5. OPPORTUNITY SIGNALS (links opportunity → articles)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS opportunity_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            signal_type TEXT CHECK(signal_type IN (
                'regulation', 'buying_signals', 'market_trends'
            )),
            insight TEXT,
            FOREIGN KEY(opportunity_id) REFERENCES opportunity_space(id) ON DELETE CASCADE,
            FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
        );
    """)

    # ---------------------------------------------------------
    # 6. USE CASES & VALUE DRIVERS
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS use_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            use_case TEXT,
            value_driver TEXT,
            FOREIGN KEY(opportunity_id) REFERENCES opportunity_space(id) ON DELETE CASCADE
        );
    """)

    # ---------------------------------------------------------
    # 7. TARGET AUDIENCE (personas, verticals, geographies)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS target_audience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            persona TEXT,
            vertical TEXT,
            geography TEXT,
            FOREIGN KEY(opportunity_id) REFERENCES opportunity_space(id) ON DELETE CASCADE
        );
    """)

    # ---------------------------------------------------------
    # 8. SCORING (attractiveness + urgency)
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scoring (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opportunity_id INTEGER NOT NULL,
            attractiveness_score INTEGER,
            attractiveness_rationale TEXT,
            urgency_score INTEGER,
            urgency_rationale TEXT,
            FOREIGN KEY(opportunity_id) REFERENCES opportunity_space(id) ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()

    print(f"Database initialized successfully at: {DB_PATH}")


if __name__ == "__main__":
    create_tables()
