from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import CHROME_PATH

HTML_TO_PDF_TIMEOUT_SECONDS = 120
HWP5HTML_TIMEOUT_SECONDS = 180


def _is_text_like_file(file_path: Path) -> bool:
    try:
        head = file_path.read_bytes()[:4096]
    except Exception:
        return False
    if not head or b"\x00" in head:
        return False
    return head.lstrip().startswith((b"<?xml", b"<html", b"<body", b"<section")) or b"<" in head[:100]


def _hwp5html_command() -> str | None:
    hwp5html = Path(sys.executable).with_name("hwp5html")
    return str(hwp5html) if hwp5html.exists() else shutil.which("hwp5html")


def _output_paths(file_path: Path) -> tuple[Path, Path, Path]:
    output_dir = file_path.parent / "converted"
    html_path = output_dir / f"{file_path.stem}.html"
    pdf_path = output_dir / f"{file_path.stem}.pdf"
    return output_dir, html_path, pdf_path


def _html_entry(html_path: Path) -> Path:
    return html_path / "index.xhtml" if html_path.is_dir() else html_path


def _valid_html_output(html_path: Path) -> bool:
    browser_input = _html_entry(html_path)
    return browser_input.exists() and browser_input.stat().st_size > 0


def _valid_pdf_output(pdf_path: Path) -> bool:
    # Chrome can create a tiny PDF from an empty/broken XHTML page. Treat that as invalid.
    return pdf_path.exists() and pdf_path.stat().st_size > 20_000


def _print_html_to_pdf(html_path: Path, pdf_path: Path) -> tuple[Path | None, str]:
    if not CHROME_PATH.exists():
        return None, "PDF 변환용 Chrome을 찾지 못했습니다."

    browser_input = _html_entry(html_path)
    if not _valid_html_output(html_path):
        return None, "HTML 변환 결과(index.xhtml)가 비어 있거나 생성되지 않았습니다."

    try:
        subprocess.run(
            [
                str(CHROME_PATH),
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                browser_input.as_uri(),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=HTML_TO_PDF_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"HTML PDF 변환 시간이 {HTML_TO_PDF_TIMEOUT_SECONDS}초를 초과했습니다."
    except Exception as exc:
        return None, f"HTML PDF 변환 실패: {exc}"
    if _valid_pdf_output(pdf_path):
        return pdf_path, ""
    return None, "PDF 변환 결과 파일이 비어 있거나 너무 작습니다."


def _convert_with_hwp5html(file_path: Path, label: str) -> tuple[Path | None, str]:
    hwp5html_command = _hwp5html_command()
    if not hwp5html_command:
        return None, f"{label} 변환 도구(hwp5html)가 설치되어 있지 않습니다."

    output_dir, html_path, pdf_path = _output_paths(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if _valid_pdf_output(pdf_path):
        return pdf_path, ""
    if html_path.exists() and _valid_html_output(html_path):
        converted_pdf, error = _print_html_to_pdf(html_path, pdf_path)
        if converted_pdf:
            return converted_pdf, ""
    elif html_path.exists():
        shutil.rmtree(html_path, ignore_errors=True) if html_path.is_dir() else html_path.unlink(missing_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    try:
        subprocess.run(
            [hwp5html_command, "--output", str(html_path), str(file_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=HWP5HTML_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, (
            f"{label} HTML 변환 시간이 {HWP5HTML_TIMEOUT_SECONDS}초를 초과했습니다. "
            "원본 다운로드와 텍스트 미리보기로 표시합니다."
        )
    except Exception as exc:
        return None, f"{label} HTML 변환 실패: {exc}"
    if not _valid_html_output(html_path):
        return None, f"{label} HTML 변환 결과가 비어 있습니다."
    return _print_html_to_pdf(html_path, pdf_path)


def hwp_to_pdf(file_path: Path) -> tuple[Path | None, str]:
    return _convert_with_hwp5html(file_path, "HWP")


def hwpx_to_pdf(file_path: Path) -> tuple[Path | None, str]:
    return _convert_with_hwp5html(file_path, "HWPX")


def cached_viewer_pdf(file_path: Path) -> Path | None:
    _, _, pdf_path = _output_paths(file_path)
    if _valid_pdf_output(pdf_path):
        return pdf_path
    return None


def viewer_file(file_path: Path, extension: str, *, allow_convert: bool = True) -> tuple[str, Path, str]:
    normalized_extension = extension.lower()
    if normalized_extension == ".pdf":
        return "pdf", file_path, ""
    if normalized_extension == ".hwp" and _is_text_like_file(file_path):
        return "text", file_path, "실제 파일 내용이 XML/텍스트라 원문 텍스트로 표시합니다."
    if normalized_extension == ".hwpx" and _is_text_like_file(file_path):
        return "rhwp", file_path, "실제 파일 내용이 XML/텍스트지만 HWPX 전용 뷰어로 먼저 표시합니다."
    if normalized_extension in {".hwp", ".hwpx"} and not allow_convert:
        converted_pdf = cached_viewer_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        return "rhwp", file_path, "PDF 변환 전 HWP/HWPX 전용 뷰어로 표시합니다."
    if normalized_extension == ".hwp":
        converted_pdf, error = hwp_to_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        return "rhwp", file_path, f"PDF 변환에 실패해 HWP/HWPX 전용 뷰어로 표시합니다. ({error})"
    if normalized_extension == ".hwpx":
        converted_pdf, error = hwpx_to_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        return "rhwp", file_path, f"PDF 변환에 실패해 HWP/HWPX 전용 뷰어로 표시합니다. ({error})"
    return "unsupported", file_path, f"{extension or 'unknown'} 파일은 현재 뷰어 변환을 지원하지 않습니다."
