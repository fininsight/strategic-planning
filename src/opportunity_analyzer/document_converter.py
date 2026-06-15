from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .config import CHROME_PATH


def hwp_to_pdf(file_path: Path) -> tuple[Path | None, str]:
    hwp5html = Path(sys.executable).with_name("hwp5html")
    hwp5html_command = str(hwp5html) if hwp5html.exists() else shutil.which("hwp5html")
    if not hwp5html_command:
        return None, "HWP 변환 도구(hwp5html)가 설치되어 있지 않습니다."
    if not CHROME_PATH.exists():
        return None, "PDF 변환용 Chrome을 찾지 못했습니다."

    output_dir = file_path.parent / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{file_path.stem}.html"
    pdf_path = output_dir / f"{file_path.stem}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()

    try:
        subprocess.run(
            [hwp5html_command, "--output", str(html_path), str(file_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        browser_input = html_path / "index.xhtml" if html_path.is_dir() else html_path
        if not browser_input.exists():
            return None, "HWP HTML 변환 결과(index.xhtml)를 찾지 못했습니다."

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
            timeout=90,
        )
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return pdf_path, ""
        return None, "HWP PDF 변환 결과 파일이 생성되지 않았습니다."
    except Exception as exc:
        return None, f"HWP PDF 변환 실패: {exc}"


def viewer_file(file_path: Path, extension: str) -> tuple[str, Path, str]:
    if extension.lower() == ".pdf":
        return "pdf", file_path, ""
    if extension.lower() in {".hwp", ".hwpx"}:
        converted_pdf, error = hwp_to_pdf(file_path)
        if converted_pdf:
            return "pdf", converted_pdf, ""
        return "text", file_path, error
    return "unsupported", file_path, f"{extension or 'unknown'} 파일은 현재 뷰어 변환을 지원하지 않습니다."

