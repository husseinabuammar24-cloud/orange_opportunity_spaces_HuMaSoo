#===========================================================
# GLOBAL CONFIGURATION CONSTANTS
#===========================================================

MAX_KEYWORDS = 15  # Provider keyword limit

VERTICAL_KEYWORDS = {
    "Manufacturing": ["manufacturing", "factory", "industrial", "supply chain", "forestry", "paper"],
    "Retail": ["retail", "consumer goods", "fmcg"],
    "Finance/Banking/Insurance": ["bank", "insurance", "finance", "insurer"],
    "Public/Gov": ["government", "public sector", "municipal", "eu regulation"],
    "Defense": ["defense", "defence", "military"],
    "Automotive": ["automotive", "vehicle", "ev", "electric vehicle"],
    "Transportation & Construction": ["transportation", "logistics", "construction", "shipping"],
    "Lifesciences": ["pharma", "biotech", "life sciences"],
    "Energy": ["energy", "power grid", "renewable", "solar", "wind power"],
    "Wholesale": ["wholesale", "distribution"],
    "Media & Entertainment": ["media", "streaming", "entertainment"],
    "Healthcare": ["healthcare", "hospital", "medical"],
    "Natural Resources": ["mining", "natural resources", "extraction"],
    "Aerospace & Defense": ["aerospace", "aviation"],
}

#===========================================================
# DEFAULT KEYWORDS PER DOMAIN (MAX 15 EACH)
#===========================================================

DEFAULT_SUSTAINABILITY_KEYWORDS = [
    "sustainability", "ESG", "carbon", "circular", "netzero",
    "decarbonization", "climate", "traceability", "passport",
    "carbontax", "renewable", "emissions", "green", "recycling", "biodiversity"
]

DEFAULT_CYBERSECURITY_KEYWORDS = [
    "cybersecurity", "zerotrust", "ransomware", "breach", "NIS2",
    "cloudsecurity", "SASE", "AIsecurity", "insurance", "phishing",
    "malware", "encryption", "firewalls", "vulnerabilities", "forensics"
]

DEFAULT_SMART_INDUSTRIES_KEYWORDS = [
    "automation", "robotics", "IoT", "analytics", "sensors",
    "manufacturing", "efficiency", "optimization", "machinery",
    "industrial", "predictive", "inspection", "production",
    "quality", "operations"
]

DEFAULT_CONNECTIVITY_KEYWORDS = [
    "connectivity", "networking", "wireless", "broadband", "fiber",
    "satellite", "latency", "bandwidth", "routing", "switching",
    "telecom", "infrastructure", "coverage", "protocols", "transmission"
]

# ⭐ IMPROVED CLOUD KEYWORDS
DEFAULT_CLOUD_KEYWORDS = [
    "cloud computing", "cloud migration", "cloud adoption",
    "public cloud", "private cloud", "multi cloud",
    "cloud services", "cloud infrastructure", "data center",
    "SaaS", "PaaS", "IaaS",
    "enterprise cloud", "cloud security", "digital transformation"
]

DEFAULT_CX_KEYWORDS = [
    "personalization", "engagement", "journeys", "feedback", "sentiment",
    "loyalty", "analytics", "touchpoints", "service", "support",
    "interaction", "experience", "design", "channels", "retention"
]

# ⭐ IMPROVED EX KEYWORDS
DEFAULT_EX_KEYWORDS = [
    "employee experience", "workforce", "talent management", "HR tech",
    "employee engagement", "employee wellbeing", "workplace culture",
    "hybrid work", "remote work", "skills development",
    "reskilling", "upskilling", "performance management",
    "employee retention", "labor market"
]

#===========================================================
# OTHER CONSTANTS
#===========================================================

DEFAULT_DATA_TYPES = ["news", "pr"]

EUROPEAN_COUNTRIES = [
    "Belgium", "France", "Germany", "Netherlands", "United Kingdom",
    "Ireland", "Spain", "Italy", "Portugal", "Switzerland", "Austria",
    "Sweden", "Norway", "Denmark", "Finland", "Poland", "Czech Republic",
    "Luxembourg", "Greece", "Romania", "Hungary",
]


DOMAIN_KEYWORD_MAP = {
    "sustainability": DEFAULT_SUSTAINABILITY_KEYWORDS,
    "cybersecurity": DEFAULT_CYBERSECURITY_KEYWORDS,
    "smart_industries": DEFAULT_SMART_INDUSTRIES_KEYWORDS,
    "connectivity": DEFAULT_CONNECTIVITY_KEYWORDS,
    "cloud": DEFAULT_CLOUD_KEYWORDS,
    "cx": DEFAULT_CX_KEYWORDS,
    "ex": DEFAULT_EX_KEYWORDS,
}
