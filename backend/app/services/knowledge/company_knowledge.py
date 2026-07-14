from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.analyzer.config import COMPANY_KNOWLEDGE_DIR

SOURCE_DIR = COMPANY_KNOWLEDGE_DIR / "sources"
INDEX_PATH = COMPANY_KNOWLEDGE_DIR / "index.json"
INDEX_VERSION = 3
SUPPORTED_EXTENSIONS = {".pdf", ".hwp", ".hwpx", ".txt", ".md", ".html", ".htm", ".xml"}
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 220

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clip(text: str, limit: int = 260) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def retrieve_company_evidence(payload: dict[str, Any], *, limit: int = 14) -> dict[str, Any]:
    """Return company evidence chunks relevant to the current notice.

    This is a local, no-network RAG baseline. It intentionally keeps internal company
    material separate from web-search facts so proposal claims can label their source.
    """
    index = load_or_build_index()
    query = _build_query(payload)
    results = search_company_knowledge(query, index=index, limit=limit)
    overview = build_company_overview(index, results)
    return {
        "sourceMode": "local_company_knowledge" if results else "empty",
        "storageMode": "file_index",
        "isPersistent": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDir": str(SOURCE_DIR),
        "indexPath": str(INDEX_PATH),
        "query": clip(query, 500),
        "overview": overview,
        "results": results,
        "warnings": _knowledge_warnings(index, results),
    }


def load_or_build_index() -> dict[str, Any]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    COMPANY_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    manifest = _source_manifest()
    if INDEX_PATH.exists():
        try:
            cached = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            if cached.get("manifest") == manifest and cached.get("indexVersion") == INDEX_VERSION:
                return cached
        except Exception:
            pass

    return build_company_index(manifest)


def build_company_index(manifest: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    manifest = manifest if manifest is not None else _source_manifest()
    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in manifest:
        path = Path(item["path"])
        text, method, error = _extract_source_text(path)
        if error:
            warnings.append(f"{path.name}: {error}")
        if not text:
            continue

        doc_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
        file_name = _normalize_file_name(path.name)
        doc_type = _infer_doc_type(file_name)
        documents.append(
            {
                "id": doc_id,
                "fileName": file_name,
                "docType": doc_type,
                "path": str(path),
                "textLength": len(text),
                "extractionMethod": method,
            }
        )
        for index, chunk_text in enumerate(_chunk_text(text), start=1):
            chunks.append(
                {
                    "id": f"{doc_id}-{index}",
                    "documentId": doc_id,
                    "fileName": file_name,
                    "docType": doc_type,
                    "chunkIndex": index,
                    "text": chunk_text,
                    "tokens": _token_counts(chunk_text),
                }
            )

    index = {
        "indexVersion": INDEX_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDir": str(SOURCE_DIR),
        "manifest": manifest,
        "documents": documents,
        "chunks": chunks,
        "warnings": warnings[:20],
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def search_company_knowledge(query: str, *, index: dict[str, Any] | None = None, limit: int = 8) -> list[dict[str, Any]]:
    index = index or load_or_build_index()
    query_counts = _token_counts(query)
    if not query_counts:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in index.get("chunks", []):
        if not isinstance(chunk, dict):
            continue
        score = _cosine_similarity(query_counts, chunk.get("tokens") or {})
        if score <= 0:
            continue
        scored.append((score, chunk))

    rows: list[dict[str, Any]] = []
    for score, chunk in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]:
        rows.append(
            {
                "fileName": chunk.get("fileName", ""),
                "docType": chunk.get("docType", "기타"),
                "chunkId": chunk.get("id", ""),
                "score": round(score, 4),
                "text": clip(str(chunk.get("text") or ""), 900),
            }
        )
    return rows


def build_company_overview(index: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    documents = [
        {
            "fileName": item.get("fileName", ""),
            "docType": item.get("docType", "기타 회사자료"),
            "textLength": item.get("textLength", 0),
            "extractionMethod": item.get("extractionMethod", ""),
        }
        for item in index.get("documents", [])
        if isinstance(item, dict)
    ]
    doc_types = sorted({str(item.get("docType", "")) for item in documents if item.get("docType")})
    evidence_by_type: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        doc_type = str(item.get("docType") or "기타 회사자료")
        evidence_by_type.setdefault(doc_type, []).append(
            {
                "fileName": item.get("fileName", ""),
                "text": item.get("text", ""),
                "score": item.get("score", 0),
            }
        )
    return {
        "documentCount": len(documents),
        "docTypes": doc_types,
        "documents": documents,
        "evidenceByType": {key: value[:4] for key, value in evidence_by_type.items()},
    }


def _source_manifest() -> list[dict[str, Any]]:
    if not SOURCE_DIR.exists():
        return []
    rows = []
    for path in sorted(SOURCE_DIR.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            continue
        stat = path.stat()
        rows.append(
            {
                "path": str(path),
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "sha256": _file_hash(path),
            }
        )
    return rows


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _extract_source_text(path: Path) -> tuple[str, str, str]:
    try:
        from app.services.analyzer.text_extractor import extract_document_text

        text, _, method, error = extract_document_text(path, path.suffix.lower())
        return clean_text(text), method, error
    except Exception as exc:
        return "", "failed", str(exc)


def _chunk_text(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _build_query(payload: dict[str, Any]) -> str:
    notice = payload.get("notice") or {}
    proposal_sheets = payload.get("proposalSheets") or {}
    notice_info = proposal_sheets.get("noticeInfo") or {}
    summary = notice_info.get("summary") or {}
    requirements = notice_info.get("requirements") or []
    scoring = proposal_sheets.get("scoring", {}).get("items") or []
    documents = payload.get("documents") or []

    parts = [
        str(summary.get("projectName") or notice.get("title") or ""),
        str(notice.get("agency") or notice.get("demandAgency") or ""),
        str(notice.get("industry") or ""),
        str(payload.get("summary", {}).get("summary") or ""),
    ]
    parts.extend(str(item.get("requirement") or item.get("detail") or "") for item in requirements[:20] if isinstance(item, dict))
    parts.extend(" ".join(str(item.get(key) or "") for key in ("major", "middle", "minor", "detail")) for item in scoring[:10] if isinstance(item, dict))
    parts.extend(str(item.get("documentText") or "")[:800] for item in documents[:3] if isinstance(item, dict))
    parts.append("Krayon InsightStudio InsightPage 인증 수행실적 데이터 AI RAG 보안 공공 시스템 구축")
    return clean_text("\n".join(part for part in parts if part))


def _token_counts(text: str) -> dict[str, int]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    return dict(Counter(tokens))


def _cosine_similarity(left: dict[str, int], right: dict[str, int]) -> float:
    shared = set(left) & set(right)
    dot = sum(left[token] * int(right[token]) for token in shared)
    if not dot:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(int(value) * int(value) for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _infer_doc_type(file_name: str) -> str:
    lowered = _normalize_file_name(file_name).lower()
    if any(keyword in lowered for keyword in ("회사소개", "회사정보", "핀인사이트 정보", "company", "introduction", "profile")):
        return "회사소개서"
    if any(keyword in lowered for keyword in ("실적", "수행", "reference", "portfolio")):
        return "주요 수행실적"
    if any(keyword in lowered for keyword in ("인력", "조직", "personnel", "organization")):
        return "인력/조직"
    if any(keyword in lowered for keyword in ("krayon", "insightstudio", "insightpage", "솔루션", "기술")):
        return "보유 기술/솔루션"
    if any(keyword in lowered for keyword in ("인증", "certificate", "certification")):
        return "인증/자격"
    return "기타 회사자료"


def _normalize_file_name(file_name: str) -> str:
    return unicodedata.normalize("NFC", file_name)


def _knowledge_warnings(index: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    warnings = [str(item) for item in index.get("warnings", []) if str(item).strip()]
    if not index.get("documents"):
        warnings.append(f"회사자료가 없습니다. {SOURCE_DIR} 아래에 회사소개서, 실적, 솔루션 자료를 넣어주세요.")
    elif not results:
        warnings.append("현재 공고와 매칭되는 회사자료 검색 결과가 없습니다.")
    return warnings[:8]
