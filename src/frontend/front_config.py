from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FRONTEND_PATH = PROJECT_ROOT / "src" / "frontend"

DB_PATH = PROJECT_ROOT / "data" / "New_signals.db"
DATA_PATH = PROJECT_ROOT / "data" / "os_example.json"
CSS_PATH = FRONTEND_PATH / "assets" / "alt_styles.css"
LOGO_PATH = FRONTEND_PATH / "assets" / "ob_logo.png"

ORANGE_BUSINESS_DOMAINS = [
    "Smart Industries",
    "Connectivity Solutions",
    "Cybersecurity",
    "Cloud",
    "Customer Experience",
    "Employee Experience",
    "Sustainability",
]
