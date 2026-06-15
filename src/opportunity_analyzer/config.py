import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ANALYSIS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "analyses"
CACHE_DIR = PROJECT_ROOT / ".cache" / "opportunity_scanner" / "attachments"
DOWNLOAD_SCRIPT = PROJECT_ROOT / "web" / "scripts" / "download-g2b-attachments.mjs"
def _chrome_path() -> Path:
    candidates = [
        os.getenv("CHROME_PATH", ""),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome-stable") or "",
        shutil.which("google-chrome") or "",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(candidates[0] or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


CHROME_PATH = _chrome_path()
ANALYSIS_VERSION = 19
API_ORIGIN = "http://127.0.0.1:8787"

load_dotenv(PROJECT_ROOT / ".env")
