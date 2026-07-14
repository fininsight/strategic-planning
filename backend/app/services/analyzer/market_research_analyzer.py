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
    research_queries = _build_research_queries(payload, project_name)
    base["researchQueries"] = research_queries
    base["companyEvidence"] = company_evidence.get("results", [])
    base["warnings"].extend(company_evidence.get("warnings", []))
    base = _enrich_fallback_with_strategy_draft(base, payload, company_evidence)

    if not api_key():
        base["warnings"].append("OPENAI_API_KEY 또는 LLM_API_KEY가 없어 웹검색 AI 리서치를 실행하지 않았습니다.")
        base = _enforce_source_policy(base)
        base["researchQuality"] = _research_quality(base)
        return base

    web_evidence = _collect_web_evidence(payload, project_name, research_queries)
    base["webEvidence"] = web_evidence.get("groups", [])
    base["warnings"].extend(web_evidence.get("warnings", []))

    prompt = _research_prompt(payload, project_name, company_evidence, research_queries, web_evidence)
    try:
        result = _responses_analysis_json(prompt)
    except Exception as exc:
        base["sourceMode"] = "fallback"
        base["status"] = "failed"
        base["warnings"].append(f"웹검색 AI 리서치 실패: {exc}")
        base = _enforce_source_policy(base)
        base["researchQuality"] = _research_quality(base)
        return base

    normalized = _normalize_research(result, base)
    normalized = _fill_short_sections(normalized, base)
    normalized = _enforce_source_policy(normalized)
    normalized["researchQuality"] = _research_quality(normalized)
    normalized["sourceMode"] = "web_ai"
    normalized["researchPrompt"] = prompt
    normalized["researchQueries"] = research_queries
    normalized["webEvidence"] = web_evidence.get("groups", [])
    normalized["companyEvidence"] = company_evidence.get("results", [])
    normalized["warnings"].extend(web_evidence.get("warnings", []))
    normalized["warnings"].extend(company_evidence.get("warnings", []))
    if company_evidence.get("results"):
        normalized["warnings"].append("핀인사이트 강점은 내부 회사자료에서 확인된 내용만 제안서용 문장으로 반영합니다.")
    else:
        normalized["warnings"].append("회사 인증·실적은 확인된 내부 회사자료가 없어 사내 증빙으로 재확인해야 합니다.")
    if normalized["researchQuality"]["sourcedFacts"] < 4:
        normalized["warnings"].append("웹 출처가 충분하지 않아 시장수치·수주사실은 제안서에 사용하지 마세요. 검색 쿼리와 출처를 보강해야 합니다.")
    return normalized


def _responses_web_search_json(prompt: str) -> dict[str, Any]:
    return _responses_json(prompt, purpose="web_search", use_web=True)


def _responses_analysis_json(prompt: str) -> dict[str, Any]:
    return _responses_json(prompt, purpose="analysis", use_web=False)


def _responses_json(prompt: str, *, purpose: str, use_web: bool) -> dict[str, Any]:
    payloads = _response_payloads(prompt, purpose=purpose, use_web=use_web)
    last_error: Exception | None = None
    for body in payloads:
        try:
            response = requests.post(
                os.getenv("LLM_RESPONSES_URL", "https://api.openai.com/v1/responses"),
                headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
                json=body,
                timeout=int(os.getenv("WEB_RESEARCH_TIMEOUT", "120")),
            )
            response.raise_for_status()
            return _parse_response_json(response.json())
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else 0
            if not use_web or status not in {400, 422}:
                raise
        except Exception as exc:
            last_error = exc
            raise
    if last_error:
        raise last_error
    raise ValueError("responses_api_no_payload")


def _response_payloads(prompt: str, *, purpose: str, use_web: bool) -> list[dict[str, Any]]:
    model = _research_model(purpose)
    base: dict[str, Any] = {"model": model, "input": prompt}
    if not use_web:
        return [base]

    tool_type = os.getenv("WEB_SEARCH_TOOL", "web_search")
    tool: dict[str, Any] = {"type": tool_type}
    context_size = os.getenv("WEB_SEARCH_CONTEXT_SIZE", "high")
    if context_size and tool_type == "web_search":
        tool["search_context_size"] = context_size

    primary = {**base, "tools": [tool]}
    if _env_truthy("WEB_SEARCH_TOOL_REQUIRED", True):
        primary["tool_choice"] = "required"

    fallback_tool_type = "web_search_preview" if tool_type != "web_search_preview" else "web_search"
    fallback = {**base, "tools": [{"type": fallback_tool_type}]}
    return [primary, {k: v for k, v in primary.items() if k != "tool_choice"}, fallback]


def _research_model(_: str) -> str:
    return "gpt-5"


def _env_truthy(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_response_json(data: dict[str, Any]) -> dict[str, Any]:
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


def _build_research_queries(payload: dict[str, Any], project_name: str) -> dict[str, Any]:
    notice = payload.get("notice") or {}
    agency = str(notice.get("agency") or notice.get("demandAgency") or "발주기관").strip()
    project_text = _project_text(payload)
    domain = _infer_project_domain(project_text)
    raw_keywords = notice.get("keywords") if isinstance(notice.get("keywords"), list) else []
    keywords = [str(item) for item in raw_keywords if str(item).strip()][:5]
    keyword_text = " ".join(keywords) or domain
    company_name = os.getenv("COMPANY_NAME", "핀인사이트")

    return {
        "coreContext": {
            "projectName": project_name,
            "agency": agency,
            "domain": domain,
            "keywords": keywords,
            "projectType": "공공입찰 제안/정보화 사업",
        },
        "competitors": [
            f'"{project_name}" 수주 기업',
            f'"{domain}" 사업 주요 기업',
            f'"{agency}" "{domain}" 계약',
            f'"{keyword_text}" 공공 SI 수주사',
            f'"{keyword_text}" 컨소시엄 주관사',
        ],
        "precedents": [
            f'"{agency}" "{domain}" 구축 사업',
            f'"{domain}" 유사 공공사업 수주 결과',
            f'"{keyword_text}" 나라장터 입찰 결과',
            f'"{keyword_text}" 제안요청서 수주사',
        ],
        "marketTrends": [
            f'"{domain}" 시장 규모 성장률 2024 2025',
            f'"{domain}" 공공부문 정책 동향',
            f'"{keyword_text}" 기술 트렌드 NIA NIPA ETRI',
            f'"{keyword_text}" 법령 고시 표준',
        ],
        "companyPositioning": [
            f'"{company_name}" "{domain}" 수행실적',
            f'"{company_name}" Krayon InsightStudio InsightPage',
            f'"{company_name}" 인증 솔루션 공공 AI',
        ],
        "factCheck": [
            "KOSIS 통계청 공공 데이터 AI 시장 규모",
            "나라장터 입찰결과 수주사 계약금액",
            "법제처 국가법령정보센터 관련 법령 고시",
            "NIA NIPA ETRI KISTI TTA 기술 동향 보고서",
        ],
        "authorityTiers": {
            "tier1": ["KOSIS", "나라장터", "법제처", "발주기관 공식 공고/보도자료"],
            "tier2": ["NIA", "NIPA", "ETRI", "KISTI", "TTA", "ISO", "IEEE"],
            "tier3": ["산업협회", "기업 공시/보도자료", "주요 언론"],
            "tier4": ["블로그", "마케팅 페이지", "2차 재인용 자료"],
        },
    }


def _collect_web_evidence(payload: dict[str, Any], project_name: str, research_queries: dict[str, Any]) -> dict[str, Any]:
    """Run staged web searches before synthesis.

    The final report should be written from these source-backed findings plus
    company/RFP text, instead of asking one model call to discover everything.
    """
    groups = [
        (
            "competitors",
            "경쟁사·경쟁 컨소시엄",
            research_queries.get("competitors", []),
            "이 사업에 들어올 만한 업체, 예상 컨소시엄, 유사 수주이력, 위협도",
        ),
        (
            "precedents",
            "유사 선행사례",
            research_queries.get("precedents", []),
            "동종·유사 사업의 발주기관, 사업명, 수주사, 계약금액, 연도",
        ),
        (
            "marketTrends",
            "시장 규모·정책·기술 트렌드",
            research_queries.get("marketTrends", []),
            "시장 규모·성장률, AI/GPU 인프라 정책, 기술 동향, 제도 흐름",
        ),
        (
            "factCheck",
            "팩트체크 우선 출처",
            research_queries.get("factCheck", []),
            "수치·통계·법령·고시번호·시장점유율·수주사실 검증용 1차 출처",
        ),
    ]
    limit = max(1, min(len(groups), int(os.getenv("WEB_RESEARCH_GROUP_LIMIT", "4"))))
    output: list[dict[str, Any]] = []
    warnings: list[str] = []

    for category, label, queries, objective in groups[:limit]:
        query_list = [str(item) for item in _list(queries) if str(item).strip()][:5]
        if not query_list:
            continue
        prompt = _web_evidence_prompt(payload, project_name, category, label, objective, query_list)
        try:
            result = _responses_web_search_json(prompt)
        except Exception as exc:
            warnings.append(f"{label} 웹검색 수집 실패: {exc}")
            output.append({"category": category, "label": label, "queries": query_list, "findings": [], "warnings": [str(exc)]})
            continue

        findings = _normalize_web_findings(_pick_list(result, "findings", "results", "evidence", "items"), category)
        group_warnings = [str(item) for item in _pick_list(result, "warnings", "notes") if str(item).strip()][:4]
        if not findings:
            group_warnings.append("출처 URL이 있는 검색 결과를 확보하지 못했습니다.")
        output.append(
            {
                "category": category,
                "label": label,
                "queries": _string_list(result.get("queries") or query_list) or query_list,
                "findings": findings,
                "warnings": group_warnings,
            }
        )
    return {"generatedAt": datetime.now(timezone.utc).isoformat(), "groups": output, "warnings": warnings}


def _web_evidence_prompt(
    payload: dict[str, Any],
    project_name: str,
    category: str,
    label: str,
    objective: str,
    queries: list[str],
) -> str:
    notice = payload.get("notice") or {}
    project_text = clip(_project_text(payload), 1200)
    prompt_payload = {
        "projectName": project_name,
        "category": category,
        "label": label,
        "objective": objective,
        "notice": {
            "title": notice.get("title"),
            "agency": notice.get("agency"),
            "budget": notice.get("budget"),
            "industry": notice.get("industry"),
            "keywords": notice.get("keywords"),
        },
        "projectText": project_text,
        "queries": queries,
    }
    return (
        "너는 제안서 리서치 수집 담당자다. 아래 검색어를 실제 web_search로 각각 확인하고, URL이 있는 사실만 JSON으로 반환한다. "
        "검색 결과가 부족하면 검색어를 2~3개 변형해도 된다. "
        "출처 URL이 없는 내용, 추정 경쟁사명, 추정 수주사실, 임의 수치는 findings에 넣지 않는다. "
        "나라장터/발주기관/정부·공공기관/연구기관/제조사 공식문서/기업 공식 보도자료를 우선한다. "
        "각 finding은 제안서에 재사용 가능한 단일 사실 또는 근거 단위여야 한다. "
        "JSON 객체만 반환한다. 스키마: "
        "{queries:string[], findings:[{claim:string, summary:string, category:string, relevance:string, sources:[{title,url,publisher,publishedAt,authorityTier}]}], warnings:string[]}.\n\n"
        + json.dumps(prompt_payload, ensure_ascii=False)
    )


def _normalize_web_findings(items: list[Any], category: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sources = _normalize_sources(item.get("sources") or item.get("source") or item.get("출처"))
        if not sources:
            continue
        claim = _pick_text(item, "claim", "title", "fact", "주장")
        summary = _pick_text(item, "summary", "detail", "description", "요약")
        if not any([claim, summary]):
            continue
        rows.append(
            {
                "category": _pick_text(item, "category") or category,
                "claim": clip(claim or summary, 180),
                "summary": clip(summary or claim, 360),
                "relevance": clip(_pick_text(item, "relevance", "implication", "시사점"), 220),
                "sources": sources,
            }
        )
    return rows[:12]


def _compact_web_evidence(web_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    limit = max(1, int(os.getenv("WEB_EVIDENCE_FINDINGS_PER_GROUP", "6")))
    compact: list[dict[str, Any]] = []
    for group in _list(web_evidence.get("groups")):
        if not isinstance(group, dict):
            continue
        findings: list[dict[str, Any]] = []
        for item in _list(group.get("findings"))[:limit]:
            if not isinstance(item, dict):
                continue
            sources = _normalize_sources(item.get("sources"))[:2]
            if not sources:
                continue
            findings.append(
                {
                    "claim": clip(str(item.get("claim") or ""), 160),
                    "summary": clip(str(item.get("summary") or ""), 260),
                    "relevance": clip(str(item.get("relevance") or ""), 160),
                    "sources": sources,
                }
            )
        compact.append(
            {
                "category": group.get("category", ""),
                "label": group.get("label", ""),
                "queries": _string_list(group.get("queries"))[:5],
                "findings": findings,
                "warnings": _string_list(group.get("warnings"))[:3],
            }
        )
    return compact


def _compact_company_evidence(company_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list(company_evidence.get("results"))[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "fileName": item.get("fileName", ""),
                "docType": item.get("docType", ""),
                "text": clip(str(item.get("text") or ""), 420),
            }
        )
    return rows


def _research_prompt(
    payload: dict[str, Any],
    project_name: str,
    company_evidence: dict[str, Any],
    research_queries: dict[str, Any],
    web_evidence: dict[str, Any],
) -> str:
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
        "documentExcerpts": excerpts[:2],
        "companyOverview": company_evidence.get("overview", {}),
        "companyEvidence": _compact_company_evidence(company_evidence),
        "companyEvidenceWarnings": company_evidence.get("warnings", []),
        "researchQueries": research_queries,
        "webEvidence": _compact_web_evidence(web_evidence),
        "webEvidenceWarnings": web_evidence.get("warnings", []),
    }
    return (
        "너는 공공입찰 제안서용 시장·경쟁 리서치 분석가다. "
        "이미 webEvidence 수집 단계가 끝났으므로 이 호출에서는 추가 웹검색을 하지 말고, 제공된 webEvidence와 companyEvidence만 분석한다. "
        "외부 사실 섹션(competitors, precedents, marketStats, trends)은 반드시 webEvidence의 sources URL이 있는 항목만 사용한다. 출처가 없으면 빈 배열로 둔다. "
        "SWOT과 advantages는 공고 텍스트와 회사자료를 바탕으로 작성하되, 없는 인증·실적·정량 수치는 만들지 않는다. "
        "advantages의 각 항목에는 반드시 companyEvidence 중 직접 연결되는 근거를 evidenceSources 배열로 붙인다. "
        "evidenceSources는 fileName, docType, text를 포함하고 text는 제안서 근거로 쓸 수 있는 짧은 문장 또는 요약이어야 한다. "
        "연결할 회사자료가 없으면 evidenceSources를 빈 배열로 두고 evidenceNeeded에 필요한 증빙을 쓴다. "
        "핀인사이트 강점은 Krayon, InsightStudio, InsightPage, 확인된 인증·실적·기술력을 이 사업 평가항목에 연결해 구체적으로 쓴다. 약점과 보완 전략도 솔직히 쓴다. "
        "factChecks에는 수치·통계·법령·수주사실만 넣고, VERIFIED는 sources가 있을 때만 허용한다. "
        "researchMemory에는 다음 단계에서 재사용할 검증 수치, 수주사실, 인용, 경쟁우위, 보완점을 짧게 저장한다. "
        "JSON 객체만 반환한다. 필요한 스키마: "
        "{executiveSummary:string, researchQueries:object, competitors:[{name,expectedRole,rationale,likelyPartners:string[],winRecords:string[],strengths:string[],weaknesses:string[],threatLevel:'high'|'medium'|'low',responseStrategy,sources:[{title,url,publisher,publishedAt,authorityTier}]}], "
        "precedents:[{projectName,buyer,winner,year,contractAmount,relevance,outcome,proposalImplication,sources}], "
        "marketStats:[{metric,value,period,interpretation,verification:'verified'|'unverified',sources}], "
        "trends:[{title,detail,implication,sources}], "
        "swot:[{type:'S'|'W'|'O'|'T',title,detail}], "
        "advantages:[{evaluationItem,finInsightEdge,evidenceNeeded,competitorComparison,priority:'high'|'medium'|'low',evidenceSources:[{fileName,docType,text}]}], "
        "factChecks:[{claim,category:'numeric'|'competitor'|'legal'|'tech'|'company'|'other',status:'verified'|'unverified'|'conflict',verdict:'VERIFIED'|'PARTIAL'|'OUTDATED'|'WEAK_SOURCE'|'CONTRADICTED'|'NOT_FOUND',confidence:number,note,issue,suggestedFix,citationText,sources}], "
        "researchMemory:{verifiedNumbers:string[], verifiedWins:string[], usableCitations:string[], finInsightEdges:string[], gaps:string[]}, warnings:string[]}.\n\n"
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
    normalized["researchQueries"] = result.get("researchQueries") if isinstance(result.get("researchQueries"), dict) else base.get("researchQueries", {})
    normalized["researchMemory"] = _normalize_research_memory(result.get("researchMemory") or result.get("research_memory"))
    normalized["warnings"] = [str(item) for item in _pick_list(result, "warnings", "notes")[:8] if str(item).strip()]
    normalized["status"] = "verified" if _all_number_claims_sourced(normalized) else "needs_verification"
    return normalized


def _fill_short_sections(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    minimums = {
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


def _enforce_source_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep external-fact sections strictly source-backed.

    SWOT and advantages may contain strategy derived from the RFP/company evidence.
    Competitive claims, precedents, market numbers, and trend/policy facts must not.
    """
    filtered = {**payload}
    dropped: dict[str, int] = {}
    source_required = ("competitors", "precedents", "trends")
    for key in source_required:
        rows = [item for item in _list(filtered.get(key)) if isinstance(item, dict) and item.get("sources")]
        dropped_count = len(_list(filtered.get(key))) - len(rows)
        if dropped_count > 0:
            dropped[key] = dropped_count
        filtered[key] = rows

    market_rows = [
        item
        for item in _list(filtered.get("marketStats"))
        if isinstance(item, dict) and item.get("verification") == "verified" and item.get("sources")
    ]
    dropped_market = len(_list(filtered.get("marketStats"))) - len(market_rows)
    if dropped_market > 0:
        dropped["marketStats"] = dropped_market
    filtered["marketStats"] = market_rows

    if dropped:
        warnings = [str(item) for item in _list(filtered.get("warnings")) if str(item).strip()]
        warnings.append(
            "출처 없는 외부 사실을 결과 섹션에서 제외했습니다: "
            + ", ".join(f"{key} {count}건" for key, count in dropped.items())
        )
        filtered["warnings"] = warnings[:10]
        memory = filtered.get("researchMemory") if isinstance(filtered.get("researchMemory"), dict) else {}
        gaps = _string_list(memory.get("gaps"))
        gaps.append("경쟁사·선행사례·시장수치·트렌드는 출처 있는 항목만 표시됨")
        filtered["researchMemory"] = {**memory, "gaps": gaps[:8]}
    return filtered


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
                "winRecords": _string_list(item.get("winRecords") or item.get("win_records") or item.get("similarWins") or item.get("수주이력")),
                "strengths": _string_list(item.get("strengths") or item.get("강점")),
                "weaknesses": _string_list(item.get("weaknesses") or item.get("약점")),
                "threatLevel": _normalize_priority(_pick_text(item, "threatLevel", "threat_level", "위협도")),
                "responseStrategy": clip(_pick_text(item, "responseStrategy", "response_strategy", "strategy", "대응전략") or "대응전략 확인 필요", 220),
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
                "outcome": clip(_pick_text(item, "outcome", "result", "성과", "결과"), 180),
                "proposalImplication": clip(_pick_text(item, "proposalImplication", "proposal_implication", "implication", "시사점"), 220),
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


def _normalize_advantages(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
                "evidenceSources": _normalize_company_evidence_sources(
                    item.get("evidenceSources")
                    or item.get("evidence_sources")
                    or item.get("companyEvidence")
                    or item.get("근거")
                ),
            }
        )
    return rows[:8]


def _normalize_company_evidence_sources(value: Any) -> list[dict[str, str]]:
    items = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        file_name = _pick_text(item, "fileName", "file_name", "sourceFile", "source_file", "파일명")
        text = _pick_text(item, "text", "summary", "evidence", "quote", "근거", "내용")
        if not file_name and not text:
            continue
        rows.append(
            {
                "fileName": clip(file_name or "회사자료", 80),
                "docType": clip(_pick_text(item, "docType", "doc_type", "type", "자료유형") or "회사자료", 40),
                "text": clip(text or "근거 내용 확인 필요", 220),
            }
        )
    return rows[:3]


def _normalize_fact_checks(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        claim = _pick_text(item, "claim", "statement", "fact", "주장")
        note = _pick_text(item, "note", "detail", "result", "메모")
        sources = _normalize_sources(item.get("sources") or item.get("source") or item.get("출처"))
        status, verdict = _normalize_fact_status(_pick_text(item, "status", "verification", "verdict", "판정", "검증"))
        if not any([claim, note]):
            continue
        rows.append(
            {
                "claim": clip(claim or f"팩트체크 항목 {index}", 180),
                "category": _normalize_fact_category(_pick_text(item, "category", "type", "영역")),
                "status": "verified" if status == "verified" and sources else ("conflict" if status == "conflict" else "unverified"),
                "verdict": verdict,
                "confidence": _normalize_confidence(item.get("confidence")),
                "note": clip(note or "검증 메모 확인 필요", 260),
                "issue": clip(_pick_text(item, "issue", "problem", "문제"), 220),
                "suggestedFix": clip(_pick_text(item, "suggestedFix", "suggested_fix", "recommendation", "권장수정"), 220),
                "citationText": clip(_pick_text(item, "citationText", "citation_text", "citation", "인용"), 180),
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
                "authorityTier": _normalize_authority_tier(_pick_text(source, "authorityTier", "authority_tier", "tier", "권위")),
            }
        )
    return rows[:4]


def _normalize_research_memory(value: Any) -> dict[str, list[str]]:
    memory = value if isinstance(value, dict) else {}
    return {
        "verifiedNumbers": _string_list(memory.get("verifiedNumbers") or memory.get("verified_numbers")),
        "verifiedWins": _string_list(memory.get("verifiedWins") or memory.get("verified_wins")),
        "usableCitations": _string_list(memory.get("usableCitations") or memory.get("usable_citations")),
        "finInsightEdges": _string_list(memory.get("finInsightEdges") or memory.get("fininsight_edges")),
        "gaps": _string_list(memory.get("gaps") or memory.get("risks") or memory.get("보완점")),
    }


def _research_quality(payload: dict[str, Any]) -> dict[str, int]:
    verified_claims = sum(1 for item in payload.get("factChecks", []) if isinstance(item, dict) and item.get("status") == "verified" and item.get("sources"))
    verified_market_stats = sum(1 for item in payload.get("marketStats", []) if isinstance(item, dict) and item.get("verification") == "verified" and item.get("sources"))
    sourced_competitors = sum(1 for item in payload.get("competitors", []) if isinstance(item, dict) and item.get("sources"))
    sourced_precedents = sum(1 for item in payload.get("precedents", []) if isinstance(item, dict) and item.get("sources"))
    sourced_trends = sum(1 for item in payload.get("trends", []) if isinstance(item, dict) and item.get("sources"))
    return {
        "sourcedFacts": verified_claims + verified_market_stats + sourced_precedents,
        "verifiedClaims": verified_claims,
        "verifiedMarketStats": verified_market_stats,
        "sourcedCompetitors": sourced_competitors,
        "sourcedPrecedents": sourced_precedents,
        "sourcedTrends": sourced_trends,
    }


def _normalize_fact_status(value: str) -> tuple[str, str]:
    raw = value.strip().upper()
    if raw in {"VERIFIED", "검증", "검증완료"}:
        return "verified", "VERIFIED"
    if raw in {"CONTRADICTED", "CONFLICT", "충돌", "사실충돌"}:
        return "conflict", "CONTRADICTED"
    if raw in {"PARTIAL", "OUTDATED", "WEAK_SOURCE", "NOT_FOUND", "UNVERIFIED", "미검증", "출처약함"}:
        return "unverified", raw if raw in {"PARTIAL", "OUTDATED", "WEAK_SOURCE", "NOT_FOUND"} else "NOT_FOUND"
    if raw == "VERIFIED":
        return "verified", "VERIFIED"
    return "unverified", "NOT_FOUND"


def _normalize_fact_category(value: str) -> str:
    allowed = {"numeric", "competitor", "legal", "tech", "company", "other"}
    lowered = value.strip().lower()
    return lowered if lowered in allowed else "other"


def _normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, round(number, 2)))


def _normalize_authority_tier(value: str) -> str:
    lowered = value.strip().lower().replace(" ", "")
    if lowered in {"tier1", "1", "정부", "공공", "official"}:
        return "tier1"
    if lowered in {"tier2", "2", "research", "standard", "연구기관", "표준기관"}:
        return "tier2"
    if lowered in {"tier3", "3", "industry", "company", "media", "협회", "기업", "언론"}:
        return "tier3"
    if lowered in {"tier4", "4", "blog", "marketing", "블로그", "마케팅"}:
        return "tier4"
    return ""


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
        "researchMemory": {
            "verifiedNumbers": [],
            "verifiedWins": [],
            "usableCitations": [],
            "finInsightEdges": [],
            "gaps": ["웹 출처와 회사자료 증빙 확인 전"],
        },
        "researchQuality": {
            "sourcedFacts": 0,
            "verifiedClaims": 0,
            "verifiedMarketStats": 0,
            "sourcedCompetitors": 0,
            "sourcedPrecedents": 0,
        },
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
    company_insight = _company_insight_sentence(company_evidence)
    company_evidence_label = evidence_files or "회사소개서, 솔루션 소개서, 수행실적 증빙"

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
            "detail": f"핀인사이트는 {company_insight} 이를 과업 요구사항, 평가항목, 산출물 구성으로 연결해 실행 중심의 제안 논리를 만들 수 있습니다.",
        },
        {
            "type": "S",
            "title": "증빙 가능한 강점 구성",
            "detail": f"{company_evidence_label}에서 확인 가능한 내용을 중심으로 기술·수행·운영 강점을 정리해 평가위원이 확인할 수 있는 근거형 제안으로 전개할 수 있습니다.",
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
            "detail": "기관별 생성형 AI, 문서 자동화, 지식관리 고도화 수요가 확대되면서 전문 솔루션 기반 제안의 기회가 커지고 있습니다.",
        },
        {
            "type": "O",
            "title": "보안형 내부자료 활용 요구",
            "detail": "공공기관은 내부 문서 유출 없이 AI를 활용해야 하므로, 권한관리·감사로그·민감정보 보호를 포함한 안전한 지식활용 설계가 차별 포인트가 됩니다.",
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
            "finInsightEdge": f"{domain} 요구를 업무 흐름, 데이터 활용, 산출물 자동화 관점으로 재구성하고 {company_insight} 이를 바탕으로 발주기관이 바로 검토할 수 있는 추진전략과 단계별 산출물을 제시할 수 있습니다.",
            "evidenceNeeded": company_evidence_label,
            "competitorComparison": "대형 SI가 범용 구축 경험을 앞세울 때, 핀인사이트는 과업별 AI 활용 시나리오와 산출물 중심 제안으로 차별화해야 합니다.",
            "priority": "high",
            "evidenceSources": _match_company_evidence_sources(company_evidence, f"사업 이해도 추진전략 {domain} {company_insight}"),
        },
        {
            "evaluationItem": "기술 구현 방안",
            "finInsightEdge": "Krayon·InsightStudio·InsightPage를 문서 분석, 업무 데이터 처리, 보고서·페이지 생성 흐름에 맞춰 배치해 요구사항별 구현 방안과 사용자 경험을 구체적으로 제시할 수 있습니다.",
            "evidenceNeeded": "솔루션 기능 명세, 화면 예시, 적용 시나리오",
            "competitorComparison": "범용 개발사 대비 자체 솔루션 기반 데모와 업무 흐름 설명이 가능한 점을 강조합니다.",
            "priority": "high",
            "evidenceSources": _match_company_evidence_sources(company_evidence, "Krayon InsightStudio InsightPage 솔루션 기능 문서 분석 데이터 보고서 페이지"),
        },
        {
            "evaluationItem": "수행 경험 및 안정성",
            "finInsightEdge": "확인된 수행실적과 인력 자료를 바탕으로 유사 업무 수행 가능성, 역할별 투입체계, 착수 후 안정적인 운영 전환 방안을 제안서에 연결할 수 있습니다.",
            "evidenceNeeded": "주요 수행실적, 인력증빙, 역할별 투입계획",
            "competitorComparison": "대형사 대비 규모 열위는 핵심 인력의 역할 명확화와 컨소시엄 보완 전략으로 상쇄해야 합니다.",
            "priority": "high" if has_performance or has_people else "medium",
            "evidenceSources": _match_company_evidence_sources(company_evidence, "주요 수행실적 인력 조직 투입체계 안정성"),
        },
        {
            "evaluationItem": "품질·보안·운영관리",
            "finInsightEdge": "제안 단계부터 근거 확인, 산출물 검토, 보안·품질 체크를 분리해 운영 중에도 추적 가능한 관리 체계를 제시할 수 있습니다.",
            "evidenceNeeded": "품질관리 계획, 보안관리 계획, 산출물 검토 절차",
            "competitorComparison": "경쟁사 대비 제안 준비 단계부터 근거관리와 검토 절차를 체계화하는 점을 차별 요소로 제시합니다.",
            "priority": "medium",
            "evidenceSources": _match_company_evidence_sources(company_evidence, "품질 보안 운영관리 검토 절차 산출물"),
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
            "claim": "핀인사이트 강점은 내부 회사자료에서 확인된 내용만 반영",
            "status": "unverified",
            "note": f"현재 확인 자료: {evidence_files or '회사자료 검색 결과 확인 필요'}",
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


def _match_company_evidence_sources(company_evidence: dict[str, Any], query: str) -> list[dict[str, str]]:
    results = company_evidence.get("results", []) if isinstance(company_evidence.get("results"), list) else []
    if not results:
        return []
    query_tokens = set(_evidence_tokens(query))
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(str(item.get(key) or "") for key in ("fileName", "docType", "text"))
        overlap = len(query_tokens & set(_evidence_tokens(haystack)))
        score = overlap * 2 + float(item.get("score") or 0)
        if score > 0:
            scored.append((score, item))
    if not scored:
        scored = [(float(item.get("score") or 0), item) for item in results if isinstance(item, dict)]
    rows = []
    for _, item in sorted(scored, key=lambda row: row[0], reverse=True)[:2]:
        rows.append(
            {
                "fileName": clip(str(item.get("fileName") or "회사자료"), 80),
                "docType": clip(str(item.get("docType") or "회사자료"), 40),
                "text": clip(str(item.get("text") or "근거 내용 확인 필요"), 220),
            }
        )
    return rows


def _evidence_tokens(text: str) -> list[str]:
    stop_words = {"확인", "필요", "제안", "근거", "경쟁", "평가", "항목", "자료", "수행", "기술"}
    return [
        token.lower()
        for token in re.findall(r"[0-9A-Za-z가-힣]{2,}", text)
        if token.lower() not in stop_words
    ]


def _company_insight_sentence(company_evidence: dict[str, Any]) -> str:
    overview = company_evidence.get("overview", {}) if isinstance(company_evidence.get("overview"), dict) else {}
    doc_types = {str(item) for item in overview.get("docTypes", []) if str(item).strip()}
    results = company_evidence.get("results", []) if isinstance(company_evidence.get("results"), list) else []
    evidence_text = " ".join(str(item.get("text") or "") for item in results[:4] if isinstance(item, dict))

    insights: list[str] = []
    if "보유 기술/솔루션" in doc_types or any(keyword.lower() in evidence_text.lower() for keyword in ("krayon", "insightstudio", "insightpage", "솔루션")):
        insights.append("자체 솔루션을 활용해 문서 분석, 데이터 처리, 산출물 생성 과정을 하나의 업무 흐름으로 제안할 수 있습니다.")
    if "주요 수행실적" in doc_types or any(keyword in evidence_text for keyword in ("수행", "실적", "구축", "운영")):
        insights.append("유사 사업 수행 경험을 근거로 착수, 구축, 운영 전환 단계의 리스크를 줄이는 실행 계획을 제시할 수 있습니다.")
    if "인력/조직" in doc_types or any(keyword in evidence_text for keyword in ("인력", "조직", "전담", "PM", "전문가")):
        insights.append("역할별 투입체계와 전문 인력을 앞세워 발주기관 대응 속도와 수행 안정성을 강조할 수 있습니다.")
    if "인증/자격" in doc_types or any(keyword in evidence_text for keyword in ("인증", "자격", "보안", "품질")):
        insights.append("보안·품질 관련 증빙을 활용해 공공사업 평가에서 요구되는 신뢰성과 관리 역량을 보강할 수 있습니다.")
    if not insights:
        insights.append("보유 솔루션과 수행 역량을 요구사항별 고객 가치로 정리하되, 실적·인증·정량 수치는 확인 가능한 증빙을 보강해야 합니다.")
    return " ".join(insights[:2])


def _infer_project_domain(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered for keyword in ("rag", "llm", "생성형", "인공지능", "ai", "에이전트")):
        return "생성형 AI·지식활용 플랫폼"
    if any(keyword in lowered for keyword in ("빅데이터", "데이터", "분석", "통계")):
        return "데이터 분석·플랫폼"
    if any(keyword in lowered for keyword in ("클라우드", "서버", "gpu", "인프라")):
        return "AI 인프라·클라우드"
    if any(keyword in lowered for keyword in ("홈페이지", "포털", "웹", "콘텐츠")):
        return "웹서비스·콘텐츠 플랫폼"
    return "공공 정보화"
