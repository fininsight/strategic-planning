from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from app.services.knowledge.company_knowledge import retrieve_company_evidence

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
    company_evidence = retrieve_company_evidence(payload)
    base["companyEvidence"] = company_evidence.get("results", [])
    base["warnings"].extend(company_evidence.get("warnings", []))
    base = _enrich_fallback_with_strategy_draft(base, payload, company_evidence)

    if not api_key():
        base["warnings"].append("OPENAI_API_KEY 또는 LLM_API_KEY가 없어 웹검색 AI 리서치를 실행하지 않았습니다.")
        return base

    prompt = _research_prompt(payload, project_name, company_evidence)
    try:
        result = _responses_web_search_json(prompt)
    except Exception as exc:
        base["sourceMode"] = "fallback"
        base["status"] = "failed"
        base["warnings"].append(f"웹검색 AI 리서치 실패: {exc}")
        return base

    normalized = _normalize_research(result, base)
    normalized = _fill_short_sections(normalized, base)
    normalized["sourceMode"] = "web_ai"
    normalized["researchPrompt"] = prompt
    normalized["companyEvidence"] = company_evidence.get("results", [])
    normalized["warnings"].extend(company_evidence.get("warnings", []))
    if company_evidence.get("results"):
        normalized["warnings"].append("핀인사이트 강점은 회사자료 RAG 검색결과에 근거하되, 외부 수치·수주사실은 웹 출처가 있는 항목만 사용합니다.")
    else:
        normalized["warnings"].append("회사 인증·실적은 RAG 검색 결과가 없어 사내 증빙으로 재확인해야 합니다.")
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


def _research_prompt(payload: dict[str, Any], project_name: str, company_evidence: dict[str, Any]) -> str:
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
        "companyOverview": company_evidence.get("overview", {}),
        "companyEvidence": company_evidence.get("results", []),
        "companyEvidenceWarnings": company_evidence.get("warnings", []),
    }
    return (
        "너는 공공입찰 제안서용 시장·경쟁 리서처이자 팩트체커다. "
        "중요: 이 결과는 제안 전략 초안이므로 빈칸을 만들지 말고 충분히 작성한다. "
        "다만 사실 검증 원칙은 분리한다. 경쟁사 후보, 예상 컨소시엄, 기술 트렌드, SWOT, 평가항목별 전략은 LLM이 사업내용을 바탕으로 합리적 가설/초안으로 작성해도 된다. "
        "반대로 시장 규모·성장률 같은 수치, 법령·고시번호, 시장점유율, 특정 사업 수주사실, 계약금액은 반드시 web_search 출처 링크가 있을 때만 verified로 둔다. "
        "출처 없는 수치·점유율·수주사실은 factChecks에서 unverified로 표시하고 제안서 사용 금지라고 쓴다. "
        "1단계 competitive-researcher 역할로 경쟁사·예상 컨소시엄, 유사 선행사례, 시장 규모·성장률, 기술 트렌드, SWOT을 작성한다. "
        "2단계 proposal-fact-checker 역할로 수치·통계·법령·고시번호·시장점유율·수주사실만 web_search로 교차검증한다. "
        "3단계로 핀인사이트 경쟁우위를 도출한다. companyEvidence와 companyOverview는 핀인사이트 내부자료 RAG 결과이므로 강점·실적·인력·솔루션 근거로 적극 활용한다. "
        "회사자료에 있는 내용은 '회사자료 근거'로 보고 우위 문장에 반영하되, 회사자료에도 없는 인증명·실적명·정량 수치는 새로 만들지 않는다. "
        "가능하면 2023~2025년 자료를 우선 사용한다. "
        "핀인사이트 기본 강점 후보는 Krayon, InsightStudio, InsightPage, 보유 인증, 유사 수행실적, 데이터·AI 기술력이다. "
        "후속 전략 도출·제안서 작성에서 재사용할 수 있도록 검증된 핵심 수치, 출처, 경쟁우위, 보완 필요점을 JSON에 일관되게 남겨라. "
        "분량 지침: competitors 4~6개, precedents 3~6개, marketStats 3~5개, trends 4~6개, swot는 S/W/O/T 각각 2개 이상, advantages 4~6개, factChecks 6~10개를 목표로 한다. "
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


def _fill_short_sections(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    minimums = {
        "competitors": 4,
        "trends": 4,
        "swot": 8,
        "advantages": 4,
        "factChecks": 4,
    }
    for key, minimum in minimums.items():
        current = payload.get(key) if isinstance(payload.get(key), list) else []
        if len(current) >= minimum:
            continue
        payload[key] = _append_unique_rows(current, fallback.get(key, []), key)[: max(minimum, len(current))]
    return payload


def _append_unique_rows(current: list[Any], fallback: Any, key: str) -> list[Any]:
    rows = list(current)
    if not isinstance(fallback, list):
        return rows
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in rows if isinstance(item, dict)}
    for item in fallback:
        if not isinstance(item, dict):
            continue
        marker_key = {
            "competitors": "name",
            "trends": "title",
            "swot": "title",
            "advantages": "evaluationItem",
            "factChecks": "claim",
        }.get(key)
        marker = str(item.get(marker_key) or json.dumps(item, ensure_ascii=False, sort_keys=True))
        if marker in seen:
            continue
        rows.append(item)
        seen.add(marker)
    return rows


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


def _enrich_fallback_with_strategy_draft(base: dict[str, Any], payload: dict[str, Any], company_evidence: dict[str, Any]) -> dict[str, Any]:
    project_name = base.get("projectName") or "선택 공고"
    project_text = _project_text(payload)
    domain = _infer_project_domain(project_text)
    company_docs = company_evidence.get("overview", {}).get("documents", [])
    doc_types = company_evidence.get("overview", {}).get("docTypes", [])
    has_performance = "주요 수행실적" in doc_types
    has_people = "인력/조직" in doc_types
    has_company_profile = "회사소개서" in doc_types or bool(company_docs)
    evidence_files = ", ".join(str(item.get("fileName", "")) for item in company_docs[:4] if isinstance(item, dict) and item.get("fileName"))

    base["executiveSummary"] = (
        f"{project_name}은 {domain} 역량, 공공사업 수행관리, 보안·품질 관리, 데이터/AI 활용 역량을 함께 평가받을 가능성이 큽니다. "
        "아래 경쟁·트렌드·SWOT은 제안 전략 초안이며, 수치·수주사실·법령명은 팩트체크 로그에서 출처가 확인된 항목만 제안서에 사용해야 합니다."
    )
    base["competitors"] = [
        {
            "name": "대형 공공 SI 사업자",
            "expectedRole": "주관사 또는 인프라·시스템통합 총괄",
            "rationale": f"{domain} 과업은 요구사항 관리, 보안, 구축·운영 안정성이 중요해 공공 SI 경험이 많은 업체가 참여할 가능성이 높습니다.",
            "likelyPartners": ["클라우드/인프라", "보안", "데이터 분석"],
            "sources": [],
        },
        {
            "name": "AI·데이터 플랫폼 전문기업",
            "expectedRole": "AI/RAG·데이터 처리·분석 기능 구축",
            "rationale": "RAG, 문서분석, 검색, 자동화 요구가 포함된 사업은 AI 플랫폼 구현 경험을 가진 전문사가 경쟁 후보가 됩니다.",
            "likelyPartners": ["공공 SI", "LLM/API", "검색엔진"],
            "sources": [],
        },
        {
            "name": "클라우드·인프라 구축사",
            "expectedRole": "GPU/서버/클라우드 환경 설계 및 운영",
            "rationale": "성능·확장성·운영 안정성이 평가되는 경우 인프라 전문사가 컨소시엄 파트너로 들어올 수 있습니다.",
            "likelyPartners": ["AI 플랫폼", "보안", "운영관리"],
            "sources": [],
        },
        {
            "name": "보안·품질관리 전문기업",
            "expectedRole": "보안성 검토, 취약점 조치, 품질관리 지원",
            "rationale": "공공 정보화 사업은 보안 요구사항과 품질 산출물 관리가 중요해 보안·품질 전문 역량이 차별 요소가 됩니다.",
            "likelyPartners": ["주관 SI", "PMO", "인증/점검"],
            "sources": [],
        },
    ]
    base["trends"] = [
        {
            "title": "기관 특화 RAG와 하이브리드 검색",
            "detail": "공공기관 내부 문서와 외부 최신 자료를 결합해 응답 근거를 제시하는 RAG 구조가 제안의 핵심 설계 포인트가 됩니다.",
            "implication": "문서 수집·정제·청킹·검색·근거표시·재색인 운영 절차를 과업 요구사항과 연결해 제시합니다.",
            "sources": [],
        },
        {
            "title": "LLM 기반 업무 자동화와 에이전트 협업",
            "detail": "단순 질의응답을 넘어 보고서 작성, 행정 자동화, 다단계 검토를 수행하는 AI 에이전트형 서비스 요구가 커지고 있습니다.",
            "implication": "워크플로우, 승인, 로그, 재시도, 품질검증을 포함한 운영 가능한 자동화 구조를 제안합니다.",
            "sources": [],
        },
        {
            "title": "보안·접근통제 중심의 생성형 AI 도입",
            "detail": "공공 데이터와 내부자료를 다루는 AI 시스템은 권한, 감사로그, 비식별화, 외부 API 호출 통제 설계가 중요합니다.",
            "implication": "권한 기반 검색, 민감정보 마스킹, 외부 호출 정책, 감사로그를 기술 우위 항목으로 정리합니다.",
            "sources": [],
        },
        {
            "title": "사용자 주도형 노코드·로우코드 AI 활용",
            "detail": "현업 사용자가 직접 AI 서비스나 템플릿을 만들고 개선하는 방향으로 플랫폼 요구가 확장되고 있습니다.",
            "implication": "Krayon·InsightStudio·InsightPage를 사용자 경험, 산출물 생성, 지식 활용 흐름과 연결합니다.",
            "sources": [],
        },
    ]
    base["swot"] = [
        {
            "type": "S",
            "title": "AI·데이터 제안 구조화 역량",
            "detail": "핀인사이트 보유 솔루션과 회사자료 RAG를 과업 요구사항, 평가항목, 산출물로 연결해 제안 논리를 빠르게 구성할 수 있습니다.",
        },
        {
            "type": "S",
            "title": "내부자료 기반 증빙 활용",
            "detail": f"회사자료 RAG에서 확인된 자료({evidence_files or '회사소개서·실적·인력 자료'})를 근거로 강점 문장을 제안서에 일관되게 반영할 수 있습니다.",
        },
        {
            "type": "W",
            "title": "외부 공인 수치 검증 필요",
            "detail": "시장 규모, 점유율, 특정 수주사실은 내부자료가 아니라 웹 출처가 필요하므로 별도 팩트체크가 필요합니다.",
        },
        {
            "type": "W",
            "title": "대형 SI 대비 레퍼런스 인지도 보완",
            "detail": "경쟁사가 대형 공공 SI인 경우 조직 규모와 유사 대형사업 인지도에서 열위로 평가될 수 있어 실적 증빙과 협력체계를 명확히 해야 합니다.",
        },
        {
            "type": "O",
            "title": "공공 AI 전환 수요 확대",
            "detail": "기관별 생성형 AI, 문서 자동화, RAG 기반 지식관리 수요가 확대되면서 전문 솔루션 기반 제안의 기회가 커지고 있습니다.",
        },
        {
            "type": "O",
            "title": "보안형 내부자료 활용 요구",
            "detail": "공공기관은 내부 문서 유출 없이 AI를 활용해야 하므로, 폐쇄형·권한형 RAG 설계가 차별 포인트가 됩니다.",
        },
        {
            "type": "T",
            "title": "대형사 컨소시엄 경쟁",
            "detail": "공공 SI, 클라우드, 보안사가 결합한 컨소시엄이 가격·인력·레퍼런스 측면에서 강하게 경쟁할 수 있습니다.",
        },
        {
            "type": "T",
            "title": "팩트 오류 리스크",
            "detail": "제안서에 검증되지 않은 시장 수치나 수주사실이 들어가면 신뢰도와 평가 안정성이 떨어질 수 있습니다.",
        },
    ]
    base["advantages"] = [
        {
            "evaluationItem": "사업 이해도 및 추진전략",
            "finInsightEdge": f"{domain} 요구를 AI·데이터·문서 자동화 관점으로 구조화하고, 공고 첨부파일 분석 결과와 회사자료 RAG 근거를 함께 사용해 전략을 구체화할 수 있습니다.",
            "evidenceNeeded": evidence_files or "회사소개서, 솔루션 소개서, 수행실적 증빙",
            "competitorComparison": "대형 SI가 범용 구축 경험을 앞세울 때, 핀인사이트는 과업별 AI 활용 시나리오와 산출물 중심 제안으로 차별화해야 합니다.",
            "priority": "high",
        },
        {
            "evaluationItem": "기술 구현 방안",
            "finInsightEdge": "Krayon·InsightStudio·InsightPage를 RAG 검색, 분석, 보고서/페이지 생성 흐름과 연결해 요구사항별 구현 방안을 제시할 수 있습니다.",
            "evidenceNeeded": "솔루션 기능 명세, 화면 예시, 적용 시나리오",
            "competitorComparison": "범용 개발사 대비 자체 솔루션 기반 데모와 업무 흐름 설명이 가능한 점을 강조합니다.",
            "priority": "high",
        },
        {
            "evaluationItem": "수행 경험 및 안정성",
            "finInsightEdge": "회사자료 RAG에 포함된 수행실적과 인력 자료를 바탕으로 유사 업무 수행 가능성과 투입체계를 제안서에 연결할 수 있습니다.",
            "evidenceNeeded": "주요 수행실적, 인력증빙, 역할별 투입계획",
            "competitorComparison": "대형사 대비 규모 열위는 핵심 인력의 역할 명확화와 컨소시엄 보완 전략으로 상쇄해야 합니다.",
            "priority": "high" if has_performance or has_people else "medium",
        },
        {
            "evaluationItem": "품질·보안·운영관리",
            "finInsightEdge": "출처 기반 리서치, 내부자료 RAG, 팩트체크 로그를 분리해 제안서 작성 단계부터 검증 가능한 산출물 관리 체계를 만들 수 있습니다.",
            "evidenceNeeded": "품질관리 계획, 보안관리 계획, 산출물 검토 절차",
            "competitorComparison": "경쟁사 대비 제안 준비 단계의 근거관리·팩트체크 프로세스를 차별 요소로 제시합니다.",
            "priority": "medium",
        },
    ]
    if has_company_profile:
        base["warnings"] = [warning for warning in base["warnings"] if "사내 증빙 미연동" not in warning]
    base["factChecks"] = [
        {
            "claim": "경쟁사 후보와 SWOT 중 정성적 전략 초안은 LLM 가설이며 수치 사실이 아니다",
            "status": "unverified",
            "note": "제안 전략 초안으로 사용 가능하나, 특정 업체 수주사실·점유율·금액으로 표현하려면 별도 출처가 필요합니다.",
            "sources": [],
        },
        {
            "claim": "시장 규모·성장률·점유율·계약금액은 출처 링크가 있어야 제안서에 사용 가능",
            "status": "unverified",
            "note": "웹검색으로 검증된 marketStats와 factChecks의 verified 항목만 본문 수치로 채택합니다.",
            "sources": [],
        },
        {
            "claim": "핀인사이트 강점은 회사자료 RAG 근거와 연결",
            "status": "unverified",
            "note": f"현재 RAG 자료: {evidence_files or '회사자료 검색 결과 확인 필요'}",
            "sources": [],
        },
        {
            "claim": "회사자료에 없는 인증명·실적명·정량 수치는 임의 생성 금지",
            "status": "unverified",
            "note": "없는 내용은 필요 증빙으로 남기고 사람 검토 후 확정합니다.",
            "sources": [],
        },
    ]
    return base


def _project_text(payload: dict[str, Any]) -> str:
    notice = payload.get("notice") or {}
    proposal_sheets = payload.get("proposalSheets") or {}
    documents = payload.get("documents") or []
    parts = [
        str(notice.get("title") or ""),
        str(notice.get("industry") or ""),
        str(proposal_sheets.get("noticeInfo", {}).get("summary", {}).get("projectName") or ""),
        str(payload.get("summary", {}).get("summary") or ""),
    ]
    parts.extend(str(item.get("documentText") or "")[:1600] for item in documents[:3] if isinstance(item, dict))
    return " ".join(parts)


def _infer_project_domain(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("rag", "llm", "생성형", "인공지능", "ai", "에이전트")):
        return "생성형 AI·RAG 플랫폼"
    if any(keyword in lowered for keyword in ("빅데이터", "데이터", "분석", "통계")):
        return "데이터 분석·플랫폼"
    if any(keyword in lowered for keyword in ("클라우드", "서버", "gpu", "인프라")):
        return "AI 인프라·클라우드"
    if any(keyword in lowered for keyword in ("홈페이지", "포털", "웹", "콘텐츠")):
        return "웹서비스·콘텐츠 플랫폼"
    return "공공 정보화"
