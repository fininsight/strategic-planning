import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

WEB_ANALYSIS_DIR = PROJECT_ROOT / "web" / "public" / "data" / "analyses"
_attachment_dir = Path(
    os.getenv(
        "OPPORTUNITY_ATTACHMENT_DIR",
        str(PROJECT_ROOT / ".cache" / "opportunity_scanner" / "attachments"),
    )
)
CACHE_DIR = _attachment_dir if _attachment_dir.is_absolute() else PROJECT_ROOT / _attachment_dir
PUBLIC_FILE_BASE = os.getenv("OPPORTUNITY_PUBLIC_FILE_BASE", "")
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
ANALYSIS_VERSION = 20
API_ORIGIN = "http://127.0.0.1:8787"
