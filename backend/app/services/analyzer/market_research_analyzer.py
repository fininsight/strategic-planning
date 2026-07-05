from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from .llm_analyzer import api_key, clip


def generate_market_research(payload: dict[str, Any]) -> dict[str, Any]:
    notice = payload.get("notice") or {}
    proposal_sheets = payload.get("proposalSheets") or {}
    project_name = (
        proposal_sheets.get("noticeInfo", {}).get("summary", {}).get("projectName")
        or notice.get("title")
        or "선택 공고"
    )
    base = _fallback_payload(payload, "")

    if not api_key():
        base["warnings"].append("OPENAI_API_KEY 또는 LLM_API_KEY가 없어 웹검색 AI 리서치를 실행하지 않았습니다.")
        return base

    prompt = _research_prompt(payload, project_name)
    try:
        result = _responses_web_search_json(prompt)
    except Exception as exc:
        base["sourceMode"] = "fallback"
        base["status"] = "failed"
        base["warnings"].append(f"웹검색 AI 리서치 실패: {exc}")
        return base

    normalized = _normalize_research(result, base)
    normalized["sourceMode"] = "web_ai"
    normalized["researchPrompt"] = prompt
    normalized["warnings"].append("회사 인증·실적은 현재 RAG 미연동 상태이므로 사내 증빙으로 재확인해야 합니다.")
    return normalized


def _responses_web_search_json(prompt: str) -> dict[str, Any]:
    response = requests.post(
        os.getenv("LLM_RESPONSES_URL", "https://api.openai.com/v1/responses"),
        headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
        json={
            "model": os.getenv("WEB_RESEARCH_MODEL") or os.getenv("LLM_MODEL", "gpt-4.1-mini"),
            "tools": [{"type": "web_search_preview"}],
            "input": prompt,
        },
        timeout=int(os.getenv("WEB_RESEARCH_TIMEOUT", "90")),
    )
    response.raise_for_status()
    data = response.json()
    text = data.get("output_text") or _collect_response_text(data)
    parsed = _parse_json_object(text)
    if not isinstance(parsed, dict):
        raise ValueError("web_search_response_not_json")
    return parsed


def _collect_response_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("text"):
                parts.append(str(content["text"]))
    return "\n".join(parts)


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _research_prompt(payload: dict[str, Any], project_name: str) -> str:
    notice = payload.get("notice") or {}
    documents = payload.get("documents") or []
    excerpts = [
        {
            "fileName": item.get("fileName") or item.get("name"),
            "text": clip(str(item.get("documentText") or item.get("text") or ""), 1400),
        }
        for item in documents[:4]
    ]
    prompt_payload = {
        "projectName": project_name,
        "notice": {
            "title": notice.get("title"),
            "agency": notice.get("agency"),
            "budget": notice.get("budget"),
            "industry": notice.get("industry"),
            "method": notice.get("method"),
            "closeAt": notice.get("closeAt"),
            "keywords": notice.get("keywords"),
        },
        "documentExcerpts": excerpts,
        "finInsightStrengthsToValidate": [
            "Krayon",
            "InsightStudio",
            "InsightPage",
            "보유 인증",
            "유사 수행실적",
            "데이터·AI 기술력",
        ],
    }
    return (
        "너는 공공입찰 제안서용 시장·경쟁 리서처이자 팩트체커다. "
        "웹검색으로만 확인 가능한 사실을 조사하고, 출처 링크가 없는 수치·시장점유율·수주사실은 verified로 표시하지 마라. "
        "가능하면 2023~2025년 자료를 우선 사용한다. 회사 내부 인증·실적은 RAG 미연동 상태이므로 추정하지 말고 evidenceNeeded에 적어라. "
        "JSON 객체만 반환한다. 스키마는 다음과 같다: "
        "{executiveSummary:string, competitors:[{name,expectedRole,rationale,likelyPartners:string[],sources:[{title,url,publisher,publishedAt}]}], "
        "precedents:[{projectName,buyer,winner,year,contractAmount,relevance,sources}], "
        "marketStats:[{metric,value,period,interpretation,verification:'verified'|'unverified',sources}], "
        "trends:[{title,detail,implication,sources}], "
        "swot:[{type:'S'|'W'|'O'|'T',title,detail}], "
        "advantages:[{evaluationItem,finInsightEdge,evidenceNeeded,competitorComparison,priority:'high'|'medium'|'low'}], "
        "factChecks:[{claim,status:'verified'|'unverified'|'conflict',note,sources}], warnings:string[]}.\n\n"
        + json.dumps(prompt_payload, ensure_ascii=False)
    )


def _normalize_research(result: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    normalized = {**base}
    normalized["executiveSummary"] = clip(_pick_text(result, "executiveSummary", "executive_summary", "summary") or base["executiveSummary"], 600)
    normalized["competitors"] = _normalize_competitors(_pick_list(result, "competitors", "competition", "경쟁사")) or base["competitors"]
    normalized["precedents"] = _normalize_precedents(_pick_list(result, "precedents", "similarCases", "similar_cases", "수주사례"))
    normalized["marketStats"] = _normalize_market_stats(_pick_list(result, "marketStats", "market_stats", "market", "시장규모")) or base["marketStats"]
    normalized["trends"] = _normalize_trends(_pick_list(result, "trends", "techTrends", "tech_trends", "기술트렌드")) or base["trends"]
    normalized["swot"] = _normalize_swot(_pick_list(result, "swot", "SWOT")) or base["swot"]
    normalized["advantages"] = _normalize_advantages(_pick_list(result, "advantages", "competitiveAdvantages", "competitive_advantages", "경쟁우위")) or base["advantages"]
    normalized["factChecks"] = _normalize_fact_checks(_pick_list(result, "factChecks", "fact_checks", "facts", "팩트체크")) or base["factChecks"]
    normalized["warnings"] = [str(item) for item in _pick_list(result, "warnings", "notes")[:8] if str(item).strip()]
    normalized["status"] = "verified" if _all_number_claims_sourced(normalized) else "needs_verification"
    return normalized


def _normalize_competitors(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        name = _pick_text(item, "name", "company", "competitor", "업체명", "경쟁사")
        rationale = _pick_text(item, "rationale", "reason", "detail", "근거", "설명")
        role = _pick_text(item, "expectedRole", "expected_role", "role", "역할")
        if not any([name, rationale, role]):
            continue
        rows.append(
            {
                "name": clip(name or f"경쟁 후보 {index}", 80),
                "expectedRole": clip(role or "역할 확인 필요", 120),
                "rationale": clip(rationale or "웹검색 결과의 상세 근거 확인 필요", 260),
                "likelyPartners": _string_list(item.get("likelyPartners") or item.get("likely_partners") or item.get("partners") or item.get("컨소시엄")),
                "sources": _normalize_sources(item.get("sources") or item.get("source") or item.get("출처")),
            }
        )
    return rows[:8]


def _normalize_precedents(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        project = _pick_text(item, "projectName", "project_name", "name", "project", "사업명")
        buyer = _pick_text(item, "buyer", "agency", "client", "수요기관", "발주처")
        winner = _pick_text(item, "winner", "contractor", "company", "수주사")
        if not any([project, buyer, winner]):
            continue
        rows.append(
            {
                "projectName": clip(project or f"유사 선행사례 {index}", 120),
                "buyer": clip(buyer or "발주기관 확인 필요", 80),
                "winner": clip(winner or "수주사 확인 필요", 80),
                "year": clip(_pick_text(item, "year", "period", "date", "연도") or "연도 확인 필요", 40),
                "contractAmount": clip(_pick_text(item, "contractAmount", "contract_amount", "amount", "금액"), 60),
                "relevance": clip(_pick_text(item, "relevance", "detail", "similarity", "관련성") or "유사성 확인 필요", 220),
                "sources": _normalize_sources(item.get("sources") or item.get("source") or item.get("출처")),
            }
        )
    return rows[:8]


def _normalize_market_stats(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metric = _pick_text(item, "metric", "name", "title", "지표")
        value = _pick_text(item, "value", "figure", "number", "수치")
        interpretation = _pick_text(item, "interpretation", "detail", "meaning", "해석")
        if not any([metric, value, interpretation]):
            continue
        sources = _normalize_sources(item.get("sources") or item.get("source") or item.get("출처"))
        verification = _pick_text(item, "verification", "status", "검증")
        rows.append(
            {
                "metric": clip(metric or "시장 지표", 90),
                "value": clip(value or "수치 확인 필요", 80),
                "period": clip(_pick_text(item, "period", "year", "date", "기간") or "기간 확인 필요", 60),
                "interpretation": clip(interpretation or "해석 확인 필요", 260),
                "verification": "verified" if verification == "verified" and sources else "unverified",
                "sources": sources,
            }
        )
    return rows[:8]


def _normalize_trends(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        title = _pick_text(item, "title", "name", "trend", "트렌드")
        detail = _pick_text(item, "detail", "description", "summary", "설명")
        implication = _pick_text(item, "implication", "proposalImplication", "proposal_implication", "시사점")
        if not any([title, detail, implication]):
            continue
        rows.append(
            {
                "title": clip(title or f"기술 트렌드 {index}", 90),
                "detail": clip(detail or "상세 동향 확인 필요", 260),
                "implication": clip(implication or "제안 반영 포인트 확인 필요", 220),
                "sources": _normalize_sources(item.get("sources") or item.get("source") or item.get("출처")),
            }
        )
    return rows[:8]


def _normalize_swot(items: list[Any]) -> list[dict[str, str]]:
    allowed = {"S", "W", "O", "T"}
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        swot_type = str(item.get("type") or "").upper()
        if swot_type in allowed:
            rows.append(
                {
                    "type": swot_type,
                    "title": clip(str(item.get("title") or ""), 80),
                    "detail": clip(str(item.get("detail") or ""), 260),
                }
            )
    return rows[:12]


def _normalize_advantages(items: list[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        evaluation = _pick_text(item, "evaluationItem", "evaluation_item", "item", "평가항목")
        edge = _pick_text(item, "finInsightEdge", "fininsight_edge", "edge", "advantage", "우위")
        if not any([evaluation, edge]):
            continue
        rows.append(
            {
                "evaluationItem": clip(evaluation or f"평가항목 {index}", 100),
                "finInsightEdge": clip(edge or "핀인사이트 우위 근거 확인 필요", 260),
                "evidenceNeeded": clip(_pick_text(item, "evidenceNeeded", "evidence_needed", "evidence", "필요증빙") or "사내 증빙 확인 필요", 160),
                "competitorComparison": clip(_pick_text(item, "competitorComparison", "competitor_comparison", "comparison", "경쟁비교") or "경쟁사 비교 근거 확인 필요", 220),
                "priority": _normalize_priority(_pick_text(item, "priority", "우선순위")),
            }
        )
    return rows[:8]


def _normalize_fact_checks(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        claim = _pick_text(item, "claim", "statement", "fact", "주장")
        note = _pick_text(item, "note", "detail", "result", "메모")
        sources = _normalize_sources(item.get("sources") or item.get("source") or item.get("출처"))
        status = _pick_text(item, "status", "verification", "검증")
        if not any([claim, note]):
            continue
        rows.append(
            {
                "claim": clip(claim or f"팩트체크 항목 {index}", 180),
                "status": "verified" if status == "verified" and sources else ("conflict" if status == "conflict" else "unverified"),
                "note": clip(note or "검증 메모 확인 필요", 260),
                "sources": sources,
            }
        )
    return rows[:16]


def _normalize_sources(value: Any) -> list[dict[str, str]]:
    sources = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows: list[dict[str, str]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = _pick_text(source, "url", "link", "href")
        title = _pick_text(source, "title", "name", "publisher", "출처")
        if not url:
            continue
        rows.append(
            {
                "title": clip(title or url, 80),
                "url": url,
                "publisher": clip(_pick_text(source, "publisher", "site", "기관"), 60),
                "publishedAt": clip(_pick_text(source, "publishedAt", "published_at", "date", "일자"), 40),
            }
        )
    return rows[:4]


def _all_number_claims_sourced(payload: dict[str, Any]) -> bool:
    for item in payload.get("marketStats", []):
        if item.get("verification") != "verified" or not item.get("sources"):
            return False
    for item in payload.get("factChecks", []):
        if item.get("status") != "verified":
            return False
    return bool(payload.get("factChecks"))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pick_list(data: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def _pick_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clip(str(item), 60) for item in value if str(item).strip()][:6]
    if isinstance(value, str) and value.strip():
        return [clip(part.strip(), 60) for part in re.split(r"[,/·]", value) if part.strip()][:6]
    return []


def _normalize_priority(value: str) -> str:
    return value if value in {"high", "medium", "low"} else "medium"


def _fallback_payload(payload: dict[str, Any], warning: str) -> dict[str, Any]:
    notice = payload.get("notice") or {}
    proposal_sheets = payload.get("proposalSheets") or {}
    project_name = (
        notice.get("title")
        or proposal_sheets.get("noticeInfo", {}).get("summary", {}).get("projectName")
        or payload.get("summary", {}).get("title")
        or "선택 공고"
    )
    warnings = ["웹검색 AI 검증 전 fallback 데이터입니다.", "출처 없는 수치·시장점유율·수주사실은 제안서 사용 금지입니다."]
    if warning:
        warnings.append(warning)
    return {
        "id": notice.get("number") or payload.get("bidNtceNo") or payload.get("id") or "market-research",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "projectName": project_name,
        "sourceMode": "fallback",
        "status": "needs_verification",
        "executiveSummary": "시장·경쟁 리서치가 아직 검증되지 않았습니다. 웹검색 AI가 생성한 출처 링크가 붙은 항목만 제안서에 반영해야 합니다.",
        "competitors": [
            {
                "name": "동종 공공 SI·데이터 분석 전문사",
                "expectedRole": "주관 또는 데이터/AI 분석 부문 참여 후보",
                "rationale": "공공 데이터·AI·시스템 구축 실적 보유사가 경쟁 후보가 될 수 있습니다.",
                "likelyPartners": ["공공 SI", "클라우드/인프라", "데이터 컨설팅"],
                "sources": [],
            }
        ],
        "precedents": [],
        "marketStats": [
            {
                "metric": "시장 규모·성장률",
                "value": "출처 확인 전",
                "period": "2023~2025 자료 우선",
                "interpretation": "공식 통계와 조달 수주 이력을 교차 확인해야 합니다.",
                "verification": "unverified",
                "sources": [],
            }
        ],
        "trends": [
            {
                "title": "웹검색 AI 리서치 필요",
                "detail": "정책·제도 흐름, 유사 발주 동향, 데이터/AI 기술 트렌드를 검색 기반으로 확인해야 합니다.",
                "implication": "출처 링크가 붙은 항목만 제안서 본문에 반영합니다.",
                "sources": [],
            }
        ],
        "swot": [
            {
                "type": "S",
                "title": "솔루션 기반 제안 구조",
                "detail": "Krayon·InsightStudio·InsightPage를 요구사항 대응 기능으로 연결할 수 있습니다.",
            },
            {
                "type": "W",
                "title": "사내 증빙 미연동",
                "detail": "인증·실적·기술력은 RAG 또는 사내 자료 확인 전 확정하지 않습니다.",
            },
        ],
        "advantages": [
            {
                "evaluationItem": "기술 이해도 및 구현 방안",
                "finInsightEdge": "Krayon·InsightStudio·InsightPage를 요구사항별 산출물과 연결해 제안할 수 있습니다.",
                "evidenceNeeded": "솔루션 기능 명세, 구축 사례, 인증·보안 자료",
                "competitorComparison": "경쟁사 대비 우위 판단은 유사 실적과 평가항목 배점 확인 후 확정합니다.",
                "priority": "high",
            }
        ],
        "factChecks": [
            {
                "claim": "출처 없는 수치·시장점유율·수주사실은 제안서 사용 금지",
                "status": "unverified",
                "note": "웹검색 AI 검증 전",
                "sources": [],
            }
        ],
        "researchPrompt": "경쟁사/컨소시엄, 유사 선행사례, 시장 규모·성장률, 기술 트렌드, SWOT, 핀인사이트 경쟁우위를 출처 링크와 함께 조사한다.",
        "warnings": warnings,
    }
