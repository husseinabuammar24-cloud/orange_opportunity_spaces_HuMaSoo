-- Enable foreign keys in SQLite
PRAGMA foreign_keys = ON;

-- ==========================================
-- 1. DOMAINS & RAW ARTICLES TABLES
-- ==========================================

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    datatype TEXT NOT NULL,
    published_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT 0,
    FOREIGN KEY (domain_id) REFERENCES domains (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS content (
    article_id INTEGER PRIMARY KEY UNIQUE NOT NULL,
    body TEXT NOT NULL,
    raw_html TEXT,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

-- ==========================================
-- 2. OPPORTUNITY SPACES TABLES
-- ==========================================

CREATE TABLE IF NOT EXISTS opportunity_spaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id INTEGER NOT NULL,
    technology_name TEXT NOT NULL,
    overview_definition TEXT NOT NULL,
    target_audience_json TEXT, -- Stores personas, verticals, geographies as JSON
    signals_json TEXT,         -- Stores regulation, buying, and trend signals as JSON
    attractiveness_score INTEGER NOT NULL,
    attractiveness_rationale TEXT,
    urgency_score INTEGER NOT NULL,
    urgency_rationale TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (domain_id) REFERENCES domains (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS opportunity_use_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opportunity_space_id INTEGER NOT NULL,
    use_case TEXT NOT NULL,
    value_driver TEXT NOT NULL,
    FOREIGN KEY (opportunity_space_id) REFERENCES opportunity_spaces (id) ON DELETE CASCADE
);

-- Junction table linking Opportunity Spaces to supporting Raw Article IDs
CREATE TABLE IF NOT EXISTS opportunity_article_sources (
    opportunity_space_id INTEGER NOT NULL,
    article_id INTEGER NOT NULL,
    PRIMARY KEY (opportunity_space_id, article_id),
    FOREIGN KEY (opportunity_space_id) REFERENCES opportunity_spaces (id) ON DELETE CASCADE,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

-- ==========================================
-- 3. INDEXES FOR FAST PIPELINE LOOKUPS
-- ==========================================

CREATE INDEX IF NOT EXISTS idx_articles_domain_id ON articles(domain_id);
CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);

CREATE INDEX IF NOT EXISTS idx_opp_spaces_domain ON opportunity_spaces(domain_id);
CREATE INDEX IF NOT EXISTS idx_opp_spaces_tech ON opportunity_spaces(technology_name);