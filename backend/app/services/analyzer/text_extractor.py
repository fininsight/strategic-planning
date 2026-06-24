from __future__ import annotations

import html
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


def clean_legal_xml_text(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"\{이미지파일목록\}", " ", text)
    text = re.sub(r"\{이미지파일\}", " ", text)
    text = re.sub(r"\b[A-Za-z0-9+/]{120,}={0,2}\b", " ", text)
    text = re.sub(r"Qk[0-9A-Za-z+/]{80,}={0,2}", " ", text)
    text = re.sub(r"iVBORw0KGgo[0-9A-Za-z+/=]+", " ", text)
    text = re.sub(r"(?m)^\s*\^?\d+[.)]?\s*$", " ", text)
    text = re.sub(r"(?m)^\s*[-/]\s*$", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    marker_match = re.search(r"\{전문\}", text)
    if marker_match:
        header = text[: marker_match.start()]
        body = text[marker_match.end() :]
        title_lines = []
        for line in header.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(keyword in line for keyword in ("국가종합전자조달시스템", "용역계약", "입찰유의서", "법령정보센터", "시행", "조달청")):
                if line not in title_lines:
                    title_lines.append(line)
        text = "\n".join(title_lines[-5:] + [body])

    return clean_text(text)


def _read_text_like_file(file_path: Path) -> tuple[str, str]:
    try:
        head = file_path.read_bytes()[:4096]
    except Exception as exc:
        return "", f"파일 확인 실패: {exc}"
    if b"\x00" in head:
        return "", ""

    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            raw = file_path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            return "", f"텍스트 파일 읽기 실패: {exc}"
    else:
        return "", ""

    text = raw
    is_markup = re.search(r"<\?xml|<html|<body|<section|<p[>\s]", raw[:1000], re.I)
    if is_markup:
        text = re.sub(r"<[^>]+>", " ", raw)
        return clean_legal_xml_text(text), ""
    return clean_text(text), ""


def is_text_like_document(file_path: Path) -> bool:
    try:
        head = file_path.read_bytes()[:4096]
    except Exception:
        return False
    if not head or b"\x00" in head:
        return False
    stripped = head.lstrip()
    return stripped.startswith((b"<?xml", b"<html", b"<body", b"<section")) or b"<" in head[:100]


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
    text, text_error = _read_text_like_file(file_path)
    if text:
        return text, 0, "plain-text", ""
    if extension in {".hwp", ".hwpx"}:
        text, error = extract_hwp_text(file_path)
        return text, 0, "hwp-text" if text else "unavailable", error
    return "", 0, "unavailable", text_error or f"{extension or 'unknown'} 파일은 현재 텍스트 추출을 지원하지 않습니다."
