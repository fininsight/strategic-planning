from __future__ import annotations

import html
import json
import subprocess
from pathlib import Path

from .config import DOWNLOAD_SCRIPT, PROJECT_ROOT

NOTICE_KEYWORDS = ("공고서", "공고문", "입찰공고")


def _is_notice_document(path: Path) -> bool:
    return any(keyword in path.name for keyword in NOTICE_KEYWORDS)


def _cached_download_info(out_dir: Path) -> dict | None:
    if not out_dir.exists():
        return None

    all_files = [
        path
        for path in sorted(out_dir.iterdir())
        if path.is_file() and path.suffix.lower() in {".pdf", ".hwp", ".hwpx", ".zip"}
    ]
    if not all_files:
        return None
    has_notice_hwp = any(path.suffix.lower() in {".hwp", ".hwpx"} and _is_notice_document(path) for path in all_files)
    has_notice_pdf = any(path.suffix.lower() == ".pdf" and _is_notice_document(path) for path in all_files)
    if has_notice_hwp and not has_notice_pdf:
        return None

    downloads = []
    attachments = []
    for path in all_files:
        selected = {
            "orgnlAtchFileNm": path.name,
            "fileExtnNm": path.suffix.lower(),
            "fileSz": path.stat().st_size,
            "atchFileKndCd": "",
        }
        downloads.append(
            {
                "filePath": str(path),
                "pdfPath": str(path),
                "selected": selected,
            }
        )
        attachments.append(selected)

    return {
        "attachments": attachments,
        "downloads": downloads,
        "selected": attachments[0],
        "pdfPath": str(all_files[0]),
        "cacheHit": True,
    }


def download_g2b_attachments(bid_no: str, bid_ord: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cached = _cached_download_info(out_dir)
    if cached:
        return cached

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
            timeout=300,
        )
    except subprocess.CalledProcessError as exc:
        cached = _cached_download_info(out_dir)
        if cached:
            return cached
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"첨부파일 다운로드 실패: {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        cached = _cached_download_info(out_dir)
        if cached:
            return cached
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
