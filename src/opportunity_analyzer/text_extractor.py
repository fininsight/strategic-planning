from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_text(pdf_path: Path) -> tuple[str, int]:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return clean_text("\n".join(parts)), len(reader.pages)


def extract_hwp_text(file_path: Path) -> tuple[str, str]:
    hwp5txt = Path(sys.executable).with_name("hwp5txt")
    command = str(hwp5txt) if hwp5txt.exists() else shutil.which("hwp5txt")
    if not command:
        return "", "HWP 텍스트 추출 도구(hwp5txt)가 설치되어 있지 않습니다."

    try:
        result = subprocess.run(
            [command, str(file_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return clean_text(result.stdout), ""
    except Exception as exc:
        return "", f"HWP 텍스트 추출 실패: {exc}"


def extract_document_text(file_path: Path, extension: str) -> tuple[str, int, str, str]:
    extension = extension.lower()
    if extension == ".pdf":
        text, page_count = extract_pdf_text(file_path)
        return text, page_count, "pdf-text", ""
    if extension in {".hwp", ".hwpx"}:
        text, error = extract_hwp_text(file_path)
        return text, 0, "hwp-text" if text else "unavailable", error
    return "", 0, "unavailable", f"{extension or 'unknown'} 파일은 현재 텍스트 추출을 지원하지 않습니다."
