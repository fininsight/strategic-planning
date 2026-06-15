from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ANALYSIS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "analyses"
CACHE_DIR = PROJECT_ROOT / ".cache" / "opportunity_scanner" / "attachments"
DOWNLOAD_SCRIPT = PROJECT_ROOT / "web" / "scripts" / "download-g2b-attachments.mjs"
CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
ANALYSIS_VERSION = 19
API_ORIGIN = "http://127.0.0.1:8787"

load_dotenv(PROJECT_ROOT / ".env")
