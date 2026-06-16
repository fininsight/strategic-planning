from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

from .config import DOWNLOAD_SCRIPT, PROJECT_ROOT


def download_g2b_attachments(bid_no: str, bid_ord: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "node",
        str(DOWNLOAD_SCRIPT),
        "--bid-no",
        bid_no,
        "--bid-ord",
        bid_ord,
        "--out-dir",
        str(out_dir),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"첨부파일 다운로드 실패: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"첨부파일 다운로드 시간 초과: {detail}") from exc
    return json.loads(result.stdout)


def attachment_payload(item: dict) -> dict:
    return {
        "fileName": html.unescape(item.get("orgnlAtchFileNm", "")),
        "extension": item.get("fileExtnNm", ""),
        "size": item.get("fileSz", 0),
        "kindCode": item.get("atchFileKndCd", ""),
    }
