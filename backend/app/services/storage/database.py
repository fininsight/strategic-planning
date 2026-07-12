from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[4]
CHECKLIST_STATE_DIR = Path(
    os.getenv("OPPORTUNITY_CHECKLIST_STATE_DIR", str(PROJECT_ROOT / ".local-data" / "checklist-states"))
)

try:
    import psycopg
except ImportError:  # pragma: no cover - optional until DATABASE_URL is configured
    psycopg = None

_SCHEMA_READY = False


def database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def is_enabled() -> bool:
    return bool(database_url() and psycopg)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def attachment_key(item: dict) -> str:
    if item.get("attachmentKey"):
        return str(item["attachmentKey"])
    parts = [
        item.get("untyAtchFileNo"),
        item.get("atchFileSqno"),
        item.get("atchFileNm"),
        item.get("orgnlAtchFileNm") or item.get("fileName"),
        item.get("fileSz") or item.get("size"),
    ]
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


@contextmanager
def connect() -> Iterator[Any]:
    if not database_url():
        raise RuntimeError("DATABASE_URL is not configured")
    if not psycopg:
        raise RuntimeError("psycopg is not installed")
    with psycopg.connect(database_url()) as conn:
        ensure_schema(conn)
        yield conn


def ensure_schema(conn: Any | None = None) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    if not is_enabled() and conn is None:
        return

    owns_connection = conn is None
    if owns_connection:
        conn = psycopg.connect(database_url())

    ddl = """
    CREATE TABLE IF NOT EXISTS notices (
      id BIGSERIAL PRIMARY KEY,
      bid_ntce_no TEXT NOT NULL,
      bid_ntce_ord TEXT NOT NULL DEFAULT '000',
      notice_number TEXT,
      title TEXT,
      agency TEXT,
      demand_agency TEXT,
      region TEXT,
      industry TEXT,
      method TEXT,
      category TEXT,
      qualification_source TEXT,
      budget BIGINT DEFAULT 0,
      score INTEGER DEFAULT 0,
      grade TEXT,
      deep_link TEXT,
      status TEXT NOT NULL DEFAULT 'listed',
      raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (bid_ntce_no, bid_ntce_ord)
    );

    CREATE TABLE IF NOT EXISTS notice_attachments (
      id BIGSERIAL PRIMARY KEY,
      notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
      attachment_key TEXT NOT NULL,
      original_file_name TEXT NOT NULL,
      extension TEXT,
      size BIGINT DEFAULT 0,
      kind_code TEXT,
      source_download_url TEXT,
      source_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      status TEXT NOT NULL DEFAULT 'discovered',
      discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (notice_id, attachment_key)
    );

    CREATE TABLE IF NOT EXISTS attachment_files (
      id BIGSERIAL PRIMARY KEY,
      attachment_id BIGINT NOT NULL REFERENCES notice_attachments(id) ON DELETE CASCADE,
      file_role TEXT NOT NULL,
      storage_path TEXT NOT NULL,
      mime_type TEXT,
      size BIGINT DEFAULT 0,
      checksum TEXT,
      status TEXT NOT NULL DEFAULT 'downloaded',
      error TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (attachment_id, file_role, storage_path)
    );

    CREATE TABLE IF NOT EXISTS document_extractions (
      id BIGSERIAL PRIMARY KEY,
      attachment_id BIGINT NOT NULL REFERENCES notice_attachments(id) ON DELETE CASCADE,
      text_storage_path TEXT,
      text_length INTEGER DEFAULT 0,
      page_count INTEGER DEFAULT 0,
      extraction_method TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      error TEXT,
      extracted_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    CREATE TABLE IF NOT EXISTS document_analyses (
      id BIGSERIAL PRIMARY KEY,
      attachment_id BIGINT NOT NULL REFERENCES notice_attachments(id) ON DELETE CASCADE,
      analysis_version INTEGER NOT NULL,
      analysis_type TEXT NOT NULL DEFAULT 'rule',
      analysis_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      status TEXT NOT NULL DEFAULT 'pending',
      error TEXT,
      analyzed_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (attachment_id, analysis_version, analysis_type)
    );

    CREATE TABLE IF NOT EXISTS notice_analyses (
      id BIGSERIAL PRIMARY KEY,
      notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
      analysis_version INTEGER NOT NULL,
      summary_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      proposal_sheets_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      combined_text_storage_path TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      error TEXT,
      analyzed_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (notice_id, analysis_version)
    );

    CREATE TABLE IF NOT EXISTS proposal_checklist_states (
      id BIGSERIAL PRIMARY KEY,
      notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
      checks_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE (notice_id)
    );

    CREATE TABLE IF NOT EXISTS crawl_jobs (
      id BIGSERIAL PRIMARY KEY,
      job_type TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'running',
      target_count INTEGER DEFAULT 0,
      success_count INTEGER DEFAULT 0,
      failed_count INTEGER DEFAULT 0,
      duration_seconds NUMERIC,
      details JSONB NOT NULL DEFAULT '{}'::jsonb,
      error TEXT,
      started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      finished_at TIMESTAMPTZ
    );

    CREATE INDEX IF NOT EXISTS idx_notices_score ON notices(score DESC);
    CREATE INDEX IF NOT EXISTS idx_notices_status ON notices(status);
    CREATE INDEX IF NOT EXISTS idx_notice_attachments_notice ON notice_attachments(notice_id);
    CREATE INDEX IF NOT EXISTS idx_attachment_files_attachment ON attachment_files(attachment_id);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_type_started ON crawl_jobs(job_type, started_at DESC);
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    _SCHEMA_READY = True
    if owns_connection:
        conn.close()


def best_effort(operation: str, func, *args, **kwargs):
    if not is_enabled():
        return None
    try:
        with connect() as conn:
            return func(conn, *args, **kwargs)
    except Exception as exc:  # pragma: no cover - keeps legacy JSON flow alive
        logger.warning("DB persistence skipped during %s: %s", operation, exc)
        return None


def upsert_notice(conn: Any, notice: dict) -> int:
    bid_no = str(notice.get("bidNtceNo") or notice.get("bid_ntce_no") or notice.get("number") or "")
    bid_ord = str(notice.get("bidNtceOrd") or notice.get("bid_ntce_ord") or "000")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notices (
              bid_ntce_no, bid_ntce_ord, notice_number, title, agency, demand_agency,
              region, industry, method, category, qualification_source, budget,
              score, grade, deep_link, status, raw_payload, updated_at
            )
            VALUES (
              %(bid_no)s, %(bid_ord)s, %(notice_number)s, %(title)s, %(agency)s, %(demand_agency)s,
              %(region)s, %(industry)s, %(method)s, %(category)s, %(qualification_source)s,
              %(budget)s, %(score)s, %(grade)s, %(deep_link)s, %(status)s, %(raw_payload)s::jsonb, now()
            )
            ON CONFLICT (bid_ntce_no, bid_ntce_ord) DO UPDATE SET
              notice_number = COALESCE(NULLIF(EXCLUDED.notice_number, ''), notices.notice_number),
              title = COALESCE(NULLIF(EXCLUDED.title, ''), notices.title),
              agency = COALESCE(NULLIF(EXCLUDED.agency, ''), notices.agency),
              demand_agency = COALESCE(NULLIF(EXCLUDED.demand_agency, ''), notices.demand_agency),
              region = COALESCE(NULLIF(EXCLUDED.region, ''), notices.region),
              industry = COALESCE(NULLIF(EXCLUDED.industry, ''), notices.industry),
              method = COALESCE(NULLIF(EXCLUDED.method, ''), notices.method),
              category = COALESCE(NULLIF(EXCLUDED.category, ''), notices.category),
              qualification_source = COALESCE(NULLIF(EXCLUDED.qualification_source, ''), notices.qualification_source),
              budget = CASE WHEN EXCLUDED.budget = 0 THEN notices.budget ELSE EXCLUDED.budget END,
              score = CASE WHEN EXCLUDED.score = 0 THEN notices.score ELSE EXCLUDED.score END,
              grade = COALESCE(NULLIF(EXCLUDED.grade, ''), notices.grade),
              deep_link = COALESCE(NULLIF(EXCLUDED.deep_link, ''), notices.deep_link),
              status = CASE
                WHEN notices.status = 'analysis_ready' THEN notices.status
                WHEN EXCLUDED.status = 'listed' THEN notices.status
                ELSE EXCLUDED.status
              END,
              raw_payload = CASE
                WHEN EXCLUDED.raw_payload ? 'title' OR EXCLUDED.raw_payload ? 'bidNtceNm' OR EXCLUDED.raw_payload ? 'number'
                  THEN EXCLUDED.raw_payload
                ELSE notices.raw_payload
              END,
              updated_at = now()
            RETURNING id
            """,
            {
                "bid_no": bid_no,
                "bid_ord": bid_ord,
                "notice_number": notice.get("number") or notice.get("bidNtceFullNo") or bid_no,
                "title": notice.get("title") or notice.get("bidNtceNm") or "",
                "agency": notice.get("agency") or notice.get("ntceInsttNm") or "",
                "demand_agency": notice.get("demandAgency") or notice.get("dmndInsttNm") or "",
                "region": notice.get("region") or "",
                "industry": notice.get("industry") or "",
                "method": notice.get("method") or notice.get("bidMthdNm") or "",
                "category": notice.get("category") or "",
                "qualification_source": notice.get("qualificationSource") or "",
                "budget": int(notice.get("budget") or 0),
                "score": int(notice.get("score") or notice.get("_score") or 0),
                "grade": notice.get("grade") or notice.get("_grade") or "",
                "deep_link": notice.get("deepLink") or "",
                "status": notice.get("status") or "listed",
                "raw_payload": json_dumps(notice),
            },
        )
        row = cur.fetchone()
    conn.commit()
    return int(row[0])


def persist_dashboard_payload(payload: dict) -> int:
    def _persist(conn: Any) -> int:
        count = 0
        for notice in payload.get("notices", []):
            if notice.get("bidNtceNo") or notice.get("number"):
                upsert_notice(conn, notice)
                count += 1
        return count

    return int(best_effort("persist_dashboard_payload", _persist) or 0)


def load_dashboard_payload_from_db() -> dict | None:
    def _load(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT raw_payload
                FROM notices
                WHERE raw_payload ? 'title'
                   OR raw_payload ? 'bidNtceNm'
                   OR raw_payload ? 'number'
                ORDER BY score DESC, updated_at DESC
                """
            )
            notices = [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in cur.fetchall()]
        if not notices:
            return None
        return {
            "generatedAt": utc_now().isoformat(),
            "summary": {
                "qualified": len(notices),
                "disqualified": 0,
                "keywords": sorted({kw for notice in notices for kw in (notice.get("keywords") or [])}),
            },
            "notices": notices,
        }

    return best_effort("load_dashboard_payload_from_db", _load)


def upsert_attachments(bid_no: str, bid_ord: str, attachments: list[dict]) -> int:
    def _persist(conn: Any) -> int:
        notice_id = upsert_notice(conn, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord, "status": "attachments_ready"})
        count = 0
        with conn.cursor() as cur:
            for item in attachments:
                key = attachment_key(item)
                cur.execute(
                    """
                    INSERT INTO notice_attachments (
                      notice_id, attachment_key, original_file_name, extension, size,
                      kind_code, source_download_url, source_payload, status, updated_at
                    )
                    VALUES (
                      %(notice_id)s, %(attachment_key)s, %(original_file_name)s, %(extension)s,
                      %(size)s, %(kind_code)s, %(source_download_url)s, %(source_payload)s::jsonb,
                      'discovered', now()
                    )
                    ON CONFLICT (notice_id, attachment_key) DO UPDATE SET
                      original_file_name = EXCLUDED.original_file_name,
                      extension = EXCLUDED.extension,
                      size = EXCLUDED.size,
                      kind_code = EXCLUDED.kind_code,
                      source_download_url = EXCLUDED.source_download_url,
                      source_payload = EXCLUDED.source_payload,
                      updated_at = now()
                    """,
                    {
                        "notice_id": notice_id,
                        "attachment_key": key,
                        "original_file_name": item.get("orgnlAtchFileNm") or item.get("fileName") or "",
                        "extension": item.get("fileExtnNm") or item.get("extension") or "",
                        "size": int(item.get("fileSz") or item.get("size") or 0),
                        "kind_code": item.get("atchFileKndCd") or item.get("kindCode") or "",
                        "source_download_url": item.get("downloadUrl") or item.get("url") or "",
                        "source_payload": json_dumps(item),
                    },
                )
                count += 1
        conn.commit()
        return count

    return int(best_effort("upsert_attachments", _persist) or 0)


def _attachment_id(conn: Any, bid_no: str, bid_ord: str, selected: dict) -> int:
    notice_id = upsert_notice(conn, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
    key = attachment_key(selected)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO notice_attachments (
              notice_id, attachment_key, original_file_name, extension, size,
              kind_code, source_payload, status, updated_at
            )
            VALUES (
              %(notice_id)s, %(attachment_key)s, %(original_file_name)s, %(extension)s,
              %(size)s, %(kind_code)s, %(source_payload)s::jsonb, 'downloaded', now()
            )
            ON CONFLICT (notice_id, attachment_key) DO UPDATE SET
              original_file_name = EXCLUDED.original_file_name,
              extension = EXCLUDED.extension,
              size = EXCLUDED.size,
              kind_code = EXCLUDED.kind_code,
              status = CASE
                WHEN notice_attachments.status IN ('analyzed', 'extracted') THEN notice_attachments.status
                ELSE 'downloaded'
              END,
              updated_at = now()
            RETURNING id
            """,
            {
                "notice_id": notice_id,
                "attachment_key": key,
                "original_file_name": selected.get("orgnlAtchFileNm") or selected.get("fileName") or "",
                "extension": selected.get("fileExtnNm") or selected.get("extension") or "",
                "size": int(selected.get("fileSz") or selected.get("size") or 0),
                "kind_code": selected.get("atchFileKndCd") or selected.get("kindCode") or "",
                "source_payload": json_dumps(selected),
            },
        )
        row = cur.fetchone()
    return int(row[0])


def record_downloads(bid_no: str, bid_ord: str, downloads: list[dict]) -> int:
    def _persist(conn: Any) -> int:
        count = 0
        for item in downloads:
            selected = item.get("selected") or {}
            attachment_id = _attachment_id(conn, bid_no, bid_ord, selected)
            file_path = Path(item.get("filePath") or item.get("pdfPath") or "")
            size = file_path.stat().st_size if file_path.exists() else int(selected.get("fileSz") or 0)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO attachment_files (
                      attachment_id, file_role, storage_path, size, status, updated_at
                    )
                    VALUES (%s, 'original', %s, %s, 'downloaded', now())
                    ON CONFLICT (attachment_id, file_role, storage_path) DO UPDATE SET
                      size = EXCLUDED.size,
                      status = 'downloaded',
                      error = NULL,
                      updated_at = now()
                    """,
                    (attachment_id, str(file_path), size),
                )
                cur.execute(
                    """
                    UPDATE notices
                    SET status = CASE WHEN status = 'analysis_ready' THEN status ELSE 'files_ready' END,
                        updated_at = now()
                    WHERE id = (SELECT notice_id FROM notice_attachments WHERE id = %s)
                    """,
                    (attachment_id,),
                )
            count += 1
        conn.commit()
        return count

    return int(best_effort("record_downloads", _persist) or 0)


def record_document_payloads(bid_no: str, bid_ord: str, documents: list[dict], analysis_version: int) -> int:
    def _persist(conn: Any) -> int:
        count = 0
        for document in documents:
            selected = {
                "attachmentKey": document.get("attachmentKey"),
                "orgnlAtchFileNm": document.get("fileName"),
                "fileExtnNm": document.get("extension"),
                "fileSz": document.get("textLength") or 0,
            }
            attachment_id = _attachment_id(conn, bid_no, bid_ord, selected)
            with conn.cursor() as cur:
                viewer_path = document.get("viewerPath") or document.get("pdfPath") or ""
                if viewer_path:
                    cur.execute(
                        """
                        INSERT INTO attachment_files (
                          attachment_id, file_role, storage_path, size, status, error, updated_at
                        )
                        VALUES (%s, 'viewer', %s, 0, %s, %s, now())
                        ON CONFLICT (attachment_id, file_role, storage_path) DO UPDATE SET
                          status = EXCLUDED.status,
                          error = EXCLUDED.error,
                          updated_at = now()
                        """,
                        (
                            attachment_id,
                            viewer_path,
                            "ready" if not document.get("viewerError") else "failed",
                            document.get("viewerError") or None,
                        ),
                    )
                cur.execute(
                    """
                    INSERT INTO document_extractions (
                      attachment_id, text_length, page_count, extraction_method,
                      status, error, extracted_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, now(), now())
                    """,
                    (
                        attachment_id,
                        int(document.get("textLength") or 0),
                        int(document.get("pageCount") or 0),
                        document.get("extractionMethod") or "",
                        "extracted" if document.get("documentText") else "pending",
                        document.get("extractionError") or None,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO document_analyses (
                      attachment_id, analysis_version, analysis_type, analysis_payload,
                      status, error, analyzed_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, now(), now())
                    ON CONFLICT (attachment_id, analysis_version, analysis_type) DO UPDATE SET
                      analysis_payload = EXCLUDED.analysis_payload,
                      status = EXCLUDED.status,
                      error = EXCLUDED.error,
                      analyzed_at = EXCLUDED.analyzed_at,
                      updated_at = now()
                    """,
                    (
                        attachment_id,
                        analysis_version,
                        (document.get("analysis") or {}).get("analysisSource", "rule"),
                        json_dumps(document.get("analysis") or {}),
                        "analyzed" if document.get("analysis") else "pending",
                        (document.get("analysis") or {}).get("analysisError"),
                    ),
                )
            count += 1
        conn.commit()
        return count

    return int(best_effort("record_document_payloads", _persist) or 0)


def record_notice_analysis(bid_no: str, bid_ord: str, payload: dict, analysis_version: int) -> None:
    def _persist(conn: Any) -> None:
        notice_id = upsert_notice(
            conn,
            {
                "bidNtceNo": bid_no,
                "bidNtceOrd": bid_ord,
                "status": "analysis_ready" if payload.get("status") == "completed" else payload.get("status", "files_ready"),
            },
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notice_analyses (
                  notice_id, analysis_version, summary_payload, proposal_sheets_payload,
                  status, error, analyzed_at, updated_at
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, NULL, now(), now())
                ON CONFLICT (notice_id, analysis_version) DO UPDATE SET
                  summary_payload = EXCLUDED.summary_payload,
                  proposal_sheets_payload = EXCLUDED.proposal_sheets_payload,
                  status = EXCLUDED.status,
                  error = NULL,
                  analyzed_at = EXCLUDED.analyzed_at,
                  updated_at = now()
                """,
                (
                    notice_id,
                    analysis_version,
                    json_dumps(payload.get("summary") or {}),
                    json_dumps(payload.get("proposalSheets") or {}),
                    payload.get("status") or "completed",
                ),
            )
        conn.commit()

    best_effort("record_notice_analysis", _persist)


def _checklist_state_path(bid_no: str, bid_ord: str) -> Path:
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{bid_no}-{bid_ord}")
    return CHECKLIST_STATE_DIR / f"{safe_key}.json"


def _normalize_checks_payload(checks: Any) -> dict[str, bool]:
    if not isinstance(checks, dict):
        return {}
    return {str(key): bool(value) for key, value in checks.items() if str(key).strip()}


def load_checklist_state(bid_no: str, bid_ord: str) -> dict:
    try:
        from app.repositories.checklist_repository import load_checklist_state as orm_load_checklist_state

        loaded = orm_load_checklist_state(bid_no, bid_ord)
        if loaded is not None:
            return loaded
    except Exception as exc:
        logger.warning("SQLAlchemy checklist load skipped: %s", exc)

    def _load(conn: Any) -> dict | None:
        notice_id = upsert_notice(conn, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT checks_payload, updated_at
                FROM proposal_checklist_states
                WHERE notice_id = %s
                """,
                (notice_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        checks = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        return {"checks": _normalize_checks_payload(checks), "updatedAt": row[1].isoformat() if row[1] else ""}

    loaded = best_effort("load_checklist_state", _load)
    if loaded is not None:
        return loaded
    path = _checklist_state_path(bid_no, bid_ord)
    if not path.exists():
        return {"checks": {}, "updatedAt": ""}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {
            "checks": _normalize_checks_payload(payload.get("checks")),
            "updatedAt": str(payload.get("updatedAt") or ""),
        }
    except Exception:
        return {"checks": {}, "updatedAt": ""}


def save_checklist_state(bid_no: str, bid_ord: str, checks: dict) -> dict:
    normalized_checks = _normalize_checks_payload(checks)
    try:
        from app.repositories.checklist_repository import save_checklist_state as orm_save_checklist_state

        saved = orm_save_checklist_state(bid_no, bid_ord, normalized_checks)
        if saved is not None:
            return saved
    except Exception as exc:
        logger.warning("SQLAlchemy checklist save skipped: %s", exc)

    def _save(conn: Any) -> dict:
        notice_id = upsert_notice(conn, {"bidNtceNo": bid_no, "bidNtceOrd": bid_ord})
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO proposal_checklist_states (notice_id, checks_payload, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (notice_id) DO UPDATE SET
                  checks_payload = EXCLUDED.checks_payload,
                  updated_at = now()
                RETURNING updated_at
                """,
                (notice_id, json_dumps(normalized_checks)),
            )
            row = cur.fetchone()
        conn.commit()
        return {"checks": normalized_checks, "updatedAt": row[0].isoformat() if row and row[0] else ""}

    saved = best_effort("save_checklist_state", _save)
    if saved is not None:
        return saved

    payload = {"checks": normalized_checks, "updatedAt": utc_now().isoformat()}
    path = _checklist_state_path(bid_no, bid_ord)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload), encoding="utf-8")
    return payload


def start_job(job_type: str, target_count: int = 0, details: dict | None = None) -> int | None:
    def _start(conn: Any) -> int:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawl_jobs (job_type, status, target_count, details)
                VALUES (%s, 'running', %s, %s::jsonb)
                RETURNING id
                """,
                (job_type, target_count, json_dumps(details or {})),
            )
            row = cur.fetchone()
        conn.commit()
        return int(row[0])

    return best_effort("start_job", _start)


def finish_job(
    job_id: int | None,
    *,
    status: str,
    success_count: int = 0,
    failed_count: int = 0,
    started_monotonic: float | None = None,
    details: dict | None = None,
    error: str = "",
) -> None:
    if not job_id:
        return

    def _finish(conn: Any) -> None:
        duration = time.monotonic() - started_monotonic if started_monotonic else None
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawl_jobs
                SET status = %s,
                    success_count = %s,
                    failed_count = %s,
                    duration_seconds = %s,
                    details = COALESCE(details, '{}'::jsonb) || %s::jsonb,
                    error = NULLIF(%s, ''),
                    finished_at = now()
                WHERE id = %s
                """,
                (
                    status,
                    success_count,
                    failed_count,
                    duration,
                    json_dumps(details or {}),
                    error,
                    job_id,
                ),
            )
        conn.commit()

    best_effort("finish_job", _finish)
