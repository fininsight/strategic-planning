from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[3]
NOTICES_JSON = PROJECT_ROOT / "frontend" / "public" / "data" / "notices.json"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/api/notices":
            try:
                self._send_json(200, json.loads(NOTICES_JSON.read_text(encoding="utf-8")))
            except Exception as exc:
                self._send_json(500, {"error": "notices_failed", "message": str(exc)})
            return

        file_match = re.fullmatch(r"/api/notices/([^/]+)/([^/]+)/(files|original-files)/(\d+)", path)
        if file_match:
            self._send_file(*file_match.groups())
            return

        proposal_match = re.fullmatch(r"/api/notices/([^/]+)/([^/]+)/proposal-analysis", path)
        if proposal_match:
            bid_no, bid_ord = proposal_match.groups()
            try:
                from app.services.analyzer.analysis_cache import analyze_notice

                self._send_json(200, analyze_notice(bid_no, bid_ord).get("proposalSheets", {}))
            except Exception as exc:
                self._send_json(500, {"error": "proposal_analysis_failed", "message": str(exc)})
            return

        documents_match = re.fullmatch(r"/api/notices/([^/]+)/([^/]+)/documents", path)
        if documents_match:
            bid_no, bid_ord = documents_match.groups()
            try:
                from app.services.analyzer.analysis_cache import prepare_notice_documents

                self._send_json(200, prepare_notice_documents(bid_no, bid_ord))
            except Exception as exc:
                self._send_json(500, {"error": "documents_failed", "message": str(exc)})
            return

        match = re.fullmatch(r"/api/notices/([^/]+)/([^/]+)/analysis", path)
        if not match:
            self._send_json(404, {"error": "not_found"})
            return

        bid_no, bid_ord = match.groups()
        try:
            from app.services.analyzer.analysis_cache import analyze_notice

            self._send_json(200, analyze_notice(bid_no, bid_ord))
        except Exception as exc:
            self._send_json(500, {"error": "analysis_failed", "message": str(exc)})

    def _send_file(self, bid_no: str, bid_ord: str, file_kind: str, document_id: str):
        try:
            from app.services.analyzer.analysis_cache import prepare_notice_documents
            from app.services.analyzer.config import CACHE_DIR

            payload = prepare_notice_documents(bid_no, bid_ord)
            document = next(item for item in payload.get("documents", []) if item.get("id") == document_id)
            path_key = "filePath" if file_kind == "original-files" else "viewerPath"
            file_path = Path(document.get(path_key) or document.get("filePath") or document["pdfPath"]).resolve()
            cache_root = CACHE_DIR.resolve()
            if cache_root not in file_path.parents or not file_path.exists():
                self._send_json(404, {"error": "file_not_found"})
                return

            body = file_path.read_bytes()
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            disposition = "inline" if content_type == "application/pdf" else "attachment"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f"{disposition}; filename*=UTF-8''{quote(file_path.name)}")
            self.end_headers()
            self.wfile.write(body)
        except StopIteration:
            self._send_json(404, {"error": "document_not_found"})
        except Exception as exc:
            self._send_json(500, {"error": "file_failed", "message": str(exc)})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8787), Handler)
    print("Analysis API listening on http://127.0.0.1:8787")
    server.serve_forever()


if __name__ == "__main__":
    main()
