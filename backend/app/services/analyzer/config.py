import os
import shutil
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in minimal local runtimes
    def load_dotenv(*args, **kwargs):
        return False

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

_analysis_dir = Path(
    os.getenv(
        "OPPORTUNITY_ANALYSIS_DIR",
        str(PROJECT_ROOT / "frontend" / "public" / "data" / "analyses"),
    )
)
WEB_ANALYSIS_DIR = _analysis_dir if _analysis_dir.is_absolute() else PROJECT_ROOT / _analysis_dir
_attachment_dir = Path(
    os.getenv(
        "OPPORTUNITY_ATTACHMENT_DIR",
        str(PROJECT_ROOT / ".cache" / "opportunity_analyzer" / "attachments"),
    )
)
CACHE_DIR = _attachment_dir if _attachment_dir.is_absolute() else PROJECT_ROOT / _attachment_dir
PUBLIC_FILE_BASE = os.getenv("OPPORTUNITY_PUBLIC_FILE_BASE", "")
_company_knowledge_dir = Path(
    os.getenv(
        "COMPANY_KNOWLEDGE_DIR",
        str(PROJECT_ROOT / ".local-data" / "company-knowledge"),
    )
)
COMPANY_KNOWLEDGE_DIR = _company_knowledge_dir if _company_knowledge_dir.is_absolute() else PROJECT_ROOT / _company_knowledge_dir
DOWNLOAD_SCRIPT = PROJECT_ROOT / "scripts" / "download-g2b-attachments.mjs"


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
ANALYSIS_VERSION = 30
API_ORIGIN = os.getenv("API_ORIGIN", "")
