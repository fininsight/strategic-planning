from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import CHROME_PATH
from .hwpx_html_renderer import hwpx_to_html_viewer

HTML_TO_PDF_TIMEOUT_SECONDS = 120
HWP5HTML_TIMEOUT_SECONDS = 180
LIBREOFFICE_TIMEOUT_SECONDS = 180


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


def _convert_with_libreoffice(file_path: Path, label: str) -> tuple[Path | None, str]:
    soffice_candidates = [
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    soffice = next((candidate for candidate in soffice_candidates if candidate and Path(candidate).exists()), None)
    if not soffice:
        return None, f"{label} 변환 도구(LibreOffice)가 설치되어 있지 않습니다."

    output_dir, _, pdf_path = _output_paths(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if _valid_pdf_output(pdf_path):
        return pdf_path, ""

    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(file_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=LIBREOFFICE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, f"{label} LibreOffice PDF 변환 시간이 {LIBREOFFICE_TIMEOUT_SECONDS}초를 초과했습니다."
    except Exception as exc:
        return None, f"{label} LibreOffice PDF 변환 실패: {exc}"

    converted = output_dir / f"{file_path.stem}.pdf"
    if _valid_pdf_output(converted):
        return converted, ""
    return None, f"{label} LibreOffice PDF 변환 결과 파일이 생성되지 않았습니다."


def hwp_to_pdf(file_path: Path) -> tuple[Path | None, str]:
    return _convert_with_hwp5html(file_path, "HWP")


def hwpx_to_pdf(file_path: Path) -> tuple[Path | None, str]:
    # HWPX는 hwp5html 환경에 따라 지원이 불안정해서 LibreOffice를 먼저 시도한다.
    converted_pdf, libreoffice_error = _convert_with_libreoffice(file_path, "HWPX")
    if converted_pdf:
        return converted_pdf, ""
    converted_pdf, hwp5html_error = _convert_with_hwp5html(file_path, "HWPX")
    if converted_pdf:
        return converted_pdf, ""
    return None, f"{libreoffice_error} / {hwp5html_error}"


def cached_viewer_pdf(file_path: Path) -> Path | None:
    _, _, pdf_path = _output_paths(file_path)
    if _valid_pdf_output(pdf_path):
        return pdf_path
    return None


def cached_viewer_html(file_path: Path) -> Path | None:
    output_dir, _, _ = _output_paths(file_path)
    html_path = output_dir / f"{file_path.stem}.viewer.html"
    renderer_path = Path(__file__).with_name("hwpx_html_renderer.py")
    if (
        html_path.exists()
        and html_path.stat().st_size > 0
        and html_path.stat().st_mtime >= file_path.stat().st_mtime
        and html_path.stat().st_mtime >= renderer_path.stat().st_mtime
    ):
        return html_path
    return None


def viewer_file(file_path: Path, extension: str, *, allow_convert: bool = True) -> tuple[str, Path, str]:
    if extension.lower() == ".pdf":
        return "pdf", file_path, ""
    if extension.lower() in {".hwp", ".hwpx"} and _is_text_like_file(file_path):
        return "text", file_path, "실제 파일 내용이 XML/텍스트라 원문 텍스트로 표시합니다."
    if extension.lower() in {".hwp", ".hwpx"} and not allow_convert:
        converted_pdf = cached_viewer_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        if extension.lower() == ".hwpx":
            html_viewer = cached_viewer_html(file_path)
            if html_viewer:
                return "html", html_viewer, "PDF 변환 전 HWPX 표/문단 HTML 뷰어로 표시합니다."
            html_viewer, html_error = hwpx_to_html_viewer(file_path)
            if html_viewer:
                return "html", html_viewer, "PDF 변환 전 HWPX 표/문단 HTML 뷰어로 표시합니다."
            return "text", file_path, html_error or "PDF 변환 대기 중입니다."
        return "text", file_path, "PDF 변환 대기 중입니다."
    if extension.lower() == ".hwp":
        converted_pdf, error = hwp_to_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        return "text", file_path, error
    if extension.lower() == ".hwpx":
        converted_pdf, error = hwpx_to_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        html_viewer, html_error = hwpx_to_html_viewer(file_path)
        if html_viewer:
            return "html", html_viewer, "PDF 변환에 실패해 HWPX 표/문단 HTML 뷰어로 표시합니다."
        if html_error:
            error = f"{error} / {html_error}"
        return "text", file_path, error
    return "unsupported", file_path, f"{extension or 'unknown'} 파일은 현재 뷰어 변환을 지원하지 않습니다."
