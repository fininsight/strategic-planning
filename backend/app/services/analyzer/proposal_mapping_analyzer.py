from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

REQUIREMENT_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9가-힣])"
    r"((?:ECR|SFR|PER|IFR|DAR|TER|SER|QUR|COR|PMR|PSR|REQ|FUN|SEC|DBA|UIX|SYS|TST|MNT)[-_]?\d{1,4})"
    r"(?![A-Za-z0-9가-힣])",
    re.IGNORECASE,
)

PROPOSAL_ITEM_RE = re.compile(
    r"^(Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴ|Ⅵ|Ⅶ|Ⅷ|Ⅸ|Ⅹ)\.\s*([^-–—]+?)(?:\s*[-–—]\s*(.*))?$"
)

RFP_DOCUMENT_KEYWORDS = [
    "제안요청서",
    "제안 요청서",
    "제안요청",
    "제안 요청",
    "과업내용서",
    "과업 내용서",
    "과업지시서",
    "요구사항",
    "RFP",
]

LOW_VALUE_DOCUMENT_KEYWORDS = [
    "전자입찰특별유의서",
    "입찰유의서",
    "계약일반조건",
    "계약특수조건",
    "합의각서",
    "공동수급",
    "보안서약",
    "청렴",
    "법령",
    "고시",
]

QUALITATIVE_KEYWORDS = [
    "기능",
    "시스템",
    "서비스",
    "화면",
    "데이터",
    "연계",
    "보안",
    "성능",
    "품질",
    "운영",
    "교육",
    "성과",
    "관리",
    "과업",
    "구축",
    "개발",
]

QUANTITATIVE_KEYWORDS = [
    "정량",
    "실적",
    "신용",
    "재무",
    "경영상태",
    "인력",
    "자격",
    "면허",
    "등록",
    "중소기업",
    "직접생산",
    "증명",
    "인증",
]


def generate_proposal_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    proposal_sheets = payload.get("proposalSheets") or {}
    requirements, extraction = _extract_requirements(payload, proposal_sheets)
    mapped_requirements = [_map_requirement(requirement) for requirement in requirements]
    scoring_items, scoring_source = _extract_scoring_items(payload, proposal_sheets)
    page_plan = _build_page_plan(scoring_items, mapped_requirements)
    toc = _build_toc(mapped_requirements, page_plan)
    validation = _validate_mapping(requirements, mapped_requirements, extraction["warnings"])

    return {
        "id": f"{payload.get('bidNtceNo', '')}-{payload.get('bidNtceOrd', '000')}",
        "generatedAt": datetime.now().isoformat(),
        "sourceAnalysisAt": payload.get("analyzedAt", ""),
        "projectName": proposal_sheets.get("noticeInfo", {}).get("summary", {}).get("projectName", ""),
        "sourceFile": extraction["primarySourceFile"] or proposal_sheets.get("sourceFile") or (payload.get("source") or {}).get("fileName", ""),
        "requirementSourceFiles": extraction["sourceFiles"],
        "extractionWarnings": extraction["warnings"],
        "documentTypes": _detect_document_types(proposal_sheets),
        "requirementTraceability": mapped_requirements,
        "scoringPagePlan": page_plan,
        "scoringSource": scoring_source,
        "tableOfContents": toc,
        "validation": validation,
    }


def _extract_requirements(payload: dict[str, Any], proposal_sheets: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    documents = _candidate_requirement_documents(payload.get("documents") or [])
    requirements_by_code: dict[str, dict[str, str]] = {}
    source_files: list[str] = []

    for document in documents:
        file_name = str(document.get("fileName") or "")
        if file_name and file_name not in source_files:
            source_files.append(file_name)
        text = str(document.get("documentText") or "")
        composition_requirements = _extract_proposal_composition_requirements(text, file_name)
        if composition_requirements:
            return composition_requirements, {
                "primarySourceFile": file_name,
                "sourceFiles": [file_name],
                "warnings": [],
            }

        for requirement in _extract_requirements_from_text(text, file_name):
            code = requirement["code"]
            if code in requirements_by_code:
                existing = requirements_by_code[code]
                if len(requirement["detail"]) > len(existing["detail"]):
                    existing["detail"] = requirement["detail"]
                continue
            requirements_by_code[code] = requirement

    if requirements_by_code:
        return list(requirements_by_code.values()), {
            "primarySourceFile": source_files[0] if source_files else "",
            "sourceFiles": source_files,
            "warnings": [],
        }

    sheet_requirements = proposal_sheets.get("noticeInfo", {}).get("requirements") or []
    fallback: list[dict[str, str]] = []
    for index, item in enumerate(sheet_requirements, start=1):
        if not isinstance(item, dict):
            continue
        name = _clean(str(item.get("requirement") or "원문 요구사항 확인 필요"))
        detail = _clean(str(item.get("detail") or "원문 확인 필요"))
        fallback.append(
            {
                "code": _clean(str(item.get("code") or "")) or f"코드 미확인-{index:03d}",
                "name": name,
                "detail": detail,
                "source": "proposalSheets.noticeInfo.requirements",
            }
        )

    if fallback:
        return fallback, {
            "primarySourceFile": source_files[0] if source_files else proposal_sheets.get("sourceFile", ""),
            "sourceFiles": source_files or ["proposalSheets.noticeInfo.requirements"],
            "warnings": ["RFP 원문에서 요구사항 코드를 찾지 못해 기존 분석 요약을 보조 자료로 사용했습니다."],
        }

    return [], {
        "primarySourceFile": source_files[0] if source_files else "",
        "sourceFiles": source_files,
        "warnings": ["제안요청서 원문에서 요구사항 코드를 추출하지 못했습니다. 제안요청서 파일 및 텍스트 추출 상태를 확인해야 합니다."],
    }


def _candidate_requirement_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rfp_scored = []
    code_scored = []
    for index, document in enumerate(documents):
        name = str(document.get("fileName") or "")
        text = str(document.get("documentText") or "")
        score = _document_requirement_score(name, text)
        if score >= 100:
            rfp_scored.append((score, index, document))
        elif score > 0:
            code_scored.append((score, index, document))
    if rfp_scored:
        return [document for _, _, document in sorted(rfp_scored, key=lambda item: (-item[0], item[1]))]
    if code_scored:
        return [document for _, _, document in sorted(code_scored, key=lambda item: (-item[0], item[1]))]

    fallback = []
    for document in documents:
        name = str(document.get("fileName") or "")
        if any(keyword in name for keyword in LOW_VALUE_DOCUMENT_KEYWORDS):
            continue
        fallback.append(document)
    return fallback or documents


def _document_requirement_score(file_name: str, text: str) -> int:
    score = 0
    normalized_name = _fold_text(file_name)
    normalized_text = _fold_text(text)
    if any(_fold_text(keyword) in normalized_name for keyword in RFP_DOCUMENT_KEYWORDS):
        score += 100
    if "제안요구사항" in normalized_text or "요구사항 상세" in normalized_text or "요구사항 명세" in normalized_text:
        score += 50
    if REQUIREMENT_CODE_RE.search(text):
        score += 20
    if any(_fold_text(keyword) in normalized_name for keyword in LOW_VALUE_DOCUMENT_KEYWORDS):
        score -= 100
    return score


def _extract_requirements_from_text(text: str, source: str) -> list[dict[str, str]]:
    lines = [_clean(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    requirements: list[dict[str, str]] = []

    for index, line in enumerate(lines):
        match = REQUIREMENT_CODE_RE.search(line)
        if not match:
            continue

        code = match.group(1)
        tail = _clean(line[match.end():])
        context_lines = [tail] if tail else []
        for next_line in lines[index + 1:index + 7]:
            if REQUIREMENT_CODE_RE.search(next_line):
                break
            if _looks_like_noise(next_line):
                continue
            context_lines.append(next_line)
            if sum(len(item) for item in context_lines) > 700:
                break

        name = _requirement_name_from_context(code, context_lines)
        detail = _requirement_detail_from_context(context_lines, name)
        requirements.append(
            {
                "code": code,
                "name": name,
                "detail": detail,
                "source": source,
            }
        )
    return requirements


def _extract_proposal_composition_requirements(text: str, source: str) -> list[dict[str, str]]:
    composition = _slice_proposal_composition(text)
    if not composition:
        return []

    requirements: list[dict[str, str]] = []
    for proposal_type, label, section_text in [
        ("quantitative", "정량제안서", _slice_between(composition, ["나. 정량 제안서", "나.정량 제안서"], ["다. 정성 제안서", "다.정성 제안서"])),
        ("qualitative", "정성제안서", _slice_between(composition, ["다. 정성 제안서", "다.정성 제안서"], ["【붙임1】", "라. 정량평가", "6. 제안서 제출"])),
    ]:
        if not section_text:
            continue
        requirements.extend(_proposal_items_from_section(section_text, source, proposal_type, label))
    return requirements


def _slice_proposal_composition(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text or "")
    start_match = re.search(r"5\.\s*제안서\s*구성", normalized)
    if not start_match:
        return ""
    end_match = re.search(r"\n\s*6\.\s*제안서\s*제출", normalized[start_match.start():])
    if end_match:
        return normalized[start_match.start(): start_match.start() + end_match.start()]
    return normalized[start_match.start():]


def _slice_between(text: str, start_markers: list[str], end_markers: list[str]) -> str:
    folded = _fold_text(text)
    start_positions = [folded.find(_fold_text(marker)) for marker in start_markers]
    start_positions = [position for position in start_positions if position >= 0]
    if not start_positions:
        return ""
    start = min(start_positions)

    end_candidates = []
    for marker in end_markers:
        position = folded.find(_fold_text(marker), start + 1)
        if position >= 0:
            end_candidates.append(position)
    end = min(end_candidates) if end_candidates else len(text)
    return text[start:end]


def _proposal_items_from_section(section_text: str, source: str, proposal_type: str, label: str) -> list[dict[str, str]]:
    lines = [_clean(line) for line in section_text.splitlines()]
    lines = [line for line in lines if line and not _looks_like_noise(line)]
    items: list[dict[str, str]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        match = PROPOSAL_ITEM_RE.match(line)
        if match:
            if current:
                items.append(_proposal_item_to_requirement(current, source, proposal_type, label))
            roman, title, inline_detail = match.groups()
            current = {
                "roman": roman,
                "title": _clean(title),
                "details": [_clean(inline_detail or "")] if inline_detail else [],
            }
            continue

        if current and _is_proposal_detail_line(line):
            current["details"].append(_clean(line.lstrip("-*※ ")))

    if current:
        items.append(_proposal_item_to_requirement(current, source, proposal_type, label))
    return items


def _proposal_item_to_requirement(
    item: dict[str, Any],
    source: str,
    proposal_type: str,
    label: str,
) -> dict[str, str]:
    roman = item["roman"]
    title = item["title"]
    details = " ".join(detail for detail in item.get("details", []) if detail)
    code = f"{label} {roman}"
    section = f"{label} {roman}. {title}"
    return {
        "code": code,
        "name": title,
        "detail": details or "제안요청서의 해당 작성 항목 기준으로 작성",
        "source": source,
        "proposalType": proposal_type,
        "targetSection": section,
        "note": "제안요청서 '5. 제안서 구성'에서 추출",
    }


def _is_proposal_detail_line(line: str) -> bool:
    if line.startswith(("-", "*", "※")):
        return True
    if any(keyword in line for keyword in ["작성", "기술", "첨부", "제출", "기재", "수행", "평가"]):
        return True
    return False


def _requirement_name_from_context(code: str, context_lines: list[str]) -> str:
    for line in context_lines:
        line = _clean(REQUIREMENT_CODE_RE.sub("", line))
        if not line or _looks_like_noise(line):
            continue
        parts = re.split(r"\s{2,}|[|│ㆍ·]\s*", line)
        for part in parts:
            part = _clean(part)
            if part and len(part) <= 80 and not part.startswith(("세부", "내용", "설명")):
                return part
        return line[:80]
    return code


def _requirement_detail_from_context(context_lines: list[str], name: str) -> str:
    detail = _clean(" ".join(context_lines))
    if detail.startswith(name):
        detail = _clean(detail[len(name):])
    return detail[:900] or "원문 세부 요구내용 확인 필요"


def _looks_like_noise(line: str) -> bool:
    if len(line) > 300 and re.fullmatch(r"[A-Za-z0-9+/=]{120,}", line):
        return True
    return line in {"{이미지파일}", "{이미지파일목록}", "[]>"}


def _map_requirement(requirement: dict[str, str]) -> dict[str, Any]:
    code = requirement["code"]
    target = requirement.get("targetSection") or _target_for_requirement(code, requirement["name"], requirement["detail"])
    proposal_type = requirement.get("proposalType") or _proposal_type_for_requirement(code, requirement["name"], requirement["detail"])
    status = "mapped" if target else "ambiguous"
    return {
        **requirement,
        "proposalType": proposal_type,
        "targetSection": target or "확인 필요",
        "status": status,
        "note": requirement.get("note") or ("" if status == "mapped" else "요구사항 성격이 불명확하여 수동 확인 필요"),
    }


def _extract_scoring_items(payload: dict[str, Any], proposal_sheets: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    for document in _candidate_requirement_documents(payload.get("documents") or []):
        file_name = str(document.get("fileName") or "")
        text = str(document.get("documentText") or "")
        items = _extract_score_items_from_text(text)
        if items:
            return items, f"제안요청서 원문 배점표: {file_name}"

    sheet_items = proposal_sheets.get("scoring", {}).get("items") or []
    if sheet_items:
        return sheet_items, "proposalSheets.scoring"
    return [], "배점표 확인 필요"


def _extract_score_items_from_text(text: str) -> list[dict[str, Any]]:
    section = _slice_score_table(text)
    if not section:
        return []

    compact = re.sub(r"\s+", "", section)
    specs = [
        ("기술능력평가", "정량평가", "경영상태", 5),
        ("기술능력평가", "정량평가", "유사용역 수행실적", 5),
        ("기술능력평가", "정량평가", "참여인력 경력", 5),
        ("기술능력평가", "정성평가", "사업 이해도", 5),
        ("기술능력평가", "정성평가", "교육과정 설계", 10),
        ("기술능력평가", "정성평가", "강사진 및 교육 운영 역량", 10),
        ("기술능력평가", "정성평가", "기업 연계 계획", 10),
        ("기술능력평가", "정성평가", "성과관리 및 평가체계", 5),
        ("기술능력평가", "정성평가", "사업관리 역량", 5),
    ]

    items: list[dict[str, Any]] = []
    for index, (major, middle, minor, score) in enumerate(specs):
        compact_minor = re.sub(r"\s+", "", minor)
        if compact_minor not in compact:
            continue
        detail = _score_detail(section, minor, specs[index + 1][2] if index + 1 < len(specs) else "")
        items.append(
            {
                "major": major,
                "middle": middle,
                "minor": minor,
                "score": float(score),
                "weight": float(score),
                "grade": "B" if score >= 10 else "C",
                "strategy": "원문 평가항목 기준으로 제안서 분량과 핵심 메시지를 배분",
                "detail": detail,
                "source": "제안서 기술능력평가 평가항목 및 배점 한도",
            }
        )
    return items


def _slice_score_table(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text or "")
    folded = _fold_text(normalized)
    markers = [
        "제안서 기술능력평가 평가항목 및 배점 한도",
        "기술능력평가 평가항목 및 배점 한도",
        "평가항목 및 배점 한도",
    ]
    starts = [folded.find(_fold_text(marker)) for marker in markers]
    starts = [start for start in starts if start >= 0]
    if not starts:
        return ""
    start = min(starts)
    end_markers = ["평가점수 산정 방법", "5. 제안서 구성", "제안서 구성", "4. 제안서 작성"]
    ends = []
    for marker in end_markers:
        position = folded.find(_fold_text(marker), start + 1)
        if position >= 0:
            ends.append(position)
    end = min(ends) if ends else min(len(normalized), start + 5000)
    return normalized[start:end]


def _score_detail(section: str, current_label: str, next_label: str) -> str:
    current_pattern = _loose_label_pattern(current_label)
    next_pattern = _loose_label_pattern(next_label) if next_label else r"합\s*계|가격|※"
    match = re.search(rf"({current_pattern}.+?)(?:{next_pattern}|$)", section, re.DOTALL)
    if not match:
        return ""
    detail = _clean(match.group(1))
    detail = re.sub(r"\b(?:10|9|8|7\.5|7|5|4\.5|4|3\.75|3\.5)\b", " ", detail)
    return _clean(detail)[:300]


def _loose_label_pattern(label: str) -> str:
    return r"\s*".join(re.escape(char) for char in label)


def _proposal_type_for_requirement(code: str, name: str, detail: str) -> str:
    text = f"{code} {name} {detail}"
    upper_code = code.upper()
    if upper_code.startswith(("ECR",)) or any(keyword in text for keyword in QUANTITATIVE_KEYWORDS):
        return "quantitative"
    return "qualitative"


def _target_for_requirement(code: str, name: str, detail: str) -> str:
    text = f"{code} {name} {detail}".lower()
    upper_code = code.upper()

    if upper_code.startswith(("SFR", "IFR", "DAR", "TER", "SER", "QUR", "COR", "PMR", "PSR")):
        return "정성제안서 Ⅲ. 요구사항별 이행 방안"
    if upper_code.startswith(("ECR",)) or (
        upper_code.startswith(("REQ",)) and any(keyword in f"{name} {detail}" for keyword in QUANTITATIVE_KEYWORDS)
    ):
        return "정량제안서 Ⅱ. 입찰 참가자격 및 증빙"
    if "실적" in text or "수행" in text:
        return "정량제안서 Ⅲ. 수행실적 및 유사사업 경험"
    if "인력" in text or "조직" in text:
        return "정성제안서 Ⅴ. 수행조직 및 투입인력"
    if "보안" in text:
        return "정성제안서 Ⅵ. 품질·보안·위험관리"
    if "교육" in text or "운영" in text:
        return "정성제안서 Ⅳ. 운영 및 확산 계획"
    if "성과" in text or "품질" in text or "위험" in text:
        return "정성제안서 Ⅵ. 품질·보안·위험관리"
    if any(keyword in f"{name} {detail}" for keyword in QUANTITATIVE_KEYWORDS):
        return "정량제안서 Ⅱ. 입찰 참가자격 및 증빙"
    if any(keyword in f"{name} {detail}" for keyword in QUALITATIVE_KEYWORDS):
        return "정성제안서 Ⅲ. 요구사항별 이행 방안"
    return "정성제안서 Ⅰ. 사업 이해 및 추진 방향"


def _build_page_plan(scoring_items: list[dict[str, Any]], mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    qualitative_sections = _section_codes(mappings, "qualitative")
    quantitative_sections = _section_codes(mappings, "quantitative")
    items: list[dict[str, Any]] = []

    valid_scores = [
        item for item in scoring_items
        if isinstance(item, dict) and float(item.get("score") or 0) > 0
    ]
    if valid_scores:
        total_score = sum(float(item.get("score") or 0) for item in valid_scores) or 1
        total_pages = _recommended_total_pages(valid_scores)
        for item in valid_scores:
            score = float(item.get("score") or 0)
            pages = max(1, round(total_pages * score / total_score))
            label = _clean(str(item.get("minor") or item.get("middle") or item.get("major") or "평가항목"))
            target = _section_for_score(label, mappings)
            items.append(
                {
                    "scoreItem": label,
                    "score": score,
                    "targetSection": target,
                    "proposalType": "quantitative" if "정량" in target else "qualitative",
                    "recommendedPages": pages,
                    "mappedRequirementCodes": qualitative_sections.get(target, []) + quantitative_sections.get(target, []),
                    "source": item.get("source") or "배점표",
                    "detail": _clean(str(item.get("detail") or "")),
                }
            )
        return items

    base_sections = _ordered_sections(mappings)
    for section in base_sections:
        is_quant = section.startswith("정량")
        items.append(
            {
                "scoreItem": "배점표 확인 필요",
                "score": 0,
                "targetSection": section,
                "proposalType": "quantitative" if is_quant else "qualitative",
                "recommendedPages": 2 if is_quant else 4,
                "mappedRequirementCodes": quantitative_sections.get(section, []) + qualitative_sections.get(section, []),
                "source": "목차 기반 추정",
                "detail": "",
            }
        )
    return items


def _section_for_score(label: str, mappings: list[dict[str, Any]]) -> str:
    alias_targets = {
        "사업 이해도": "제안개요",
        "교육과정 설계": "사업 추진 계획 및 방안",
        "강사진 및 교육 운영 역량": "사업 관리",
        "기업 연계 계획": "사업 추진 계획 및 방안",
        "성과관리 및 평가체계": "사업 관리",
        "사업관리 역량": "사업 관리",
    }
    for score_label, section_keyword in alias_targets.items():
        if score_label in label:
            matched = _find_section_by_keyword(mappings, section_keyword, "qualitative")
            if matched:
                return matched

    for mapping in mappings:
        section = str(mapping.get("targetSection") or "")
        name = str(mapping.get("name") or "")
        if name and name in label:
            return section
        if label and label in section:
            return section
    if any(keyword in label for keyword in ["정량", "경영상태", "실적", "인력"]):
        return "정량제안서 Ⅲ. 수행실적 및 유사사업 경험" if "실적" in label else "정량제안서 Ⅱ. 입찰 참가자격 및 증빙"
    if "사업" in label and "관리" not in label:
        return "정성제안서 Ⅰ. 사업 이해 및 추진 방향"
    if "관리" in label or "품질" in label or "보안" in label:
        return "정성제안서 Ⅵ. 품질·보안·위험관리"
    if "운영" in label or "교육" in label:
        return "정성제안서 Ⅳ. 운영 및 확산 계획"
    return "정성제안서 Ⅲ. 요구사항별 이행 방안"


def _find_section_by_keyword(mappings: list[dict[str, Any]], keyword: str, proposal_type: str | None = None) -> str:
    for mapping in mappings:
        if proposal_type and mapping.get("proposalType") != proposal_type:
            continue
        section = str(mapping.get("targetSection") or "")
        name = str(mapping.get("name") or "")
        if keyword in section or keyword in name:
            return section
    return ""


def _recommended_total_pages(scoring_items: list[dict[str, Any]]) -> int:
    if any("매수" in str(item.get("detail", "")) for item in scoring_items):
        return 40
    return 50


def _build_toc(mappings: list[dict[str, Any]], page_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    page_by_section: dict[str, int] = {}
    for item in page_plan:
        section = str(item.get("targetSection") or "")
        if not section:
            continue
        page_by_section[section] = page_by_section.get(section, 0) + int(item.get("recommendedPages") or 0)
    use_scoring_pages = bool(page_plan)
    codes_by_section = _section_codes(mappings)
    sections = []
    for proposal_type, title, default_sections in [
        (
            "quantitative",
            "정량제안서",
            [
                "정량제안서 Ⅰ. 제안사 일반현황",
                "정량제안서 Ⅱ. 입찰 참가자격 및 증빙",
                "정량제안서 Ⅲ. 수행실적 및 유사사업 경험",
                "정량제안서 Ⅳ. 투입인력 및 인증·가점 증빙",
            ],
        ),
        (
            "qualitative",
            "정성제안서",
            [
                "정성제안서 Ⅰ. 사업 이해 및 추진 방향",
                "정성제안서 Ⅱ. 제안 전략 및 차별화 방향",
                "정성제안서 Ⅲ. 요구사항별 이행 방안",
                "정성제안서 Ⅳ. 운영 및 확산 계획",
                "정성제안서 Ⅴ. 수행조직 및 투입인력",
                "정성제안서 Ⅵ. 품질·보안·위험관리",
            ],
        ),
    ]:
        actual_sections = [
            section
            for section in _ordered_sections(mappings)
            if section.startswith(title)
        ]
        toc_sections = actual_sections or default_sections
        children = []
        for section in toc_sections:
            codes = codes_by_section.get(section, [])
            children.append(
                {
                    "title": section.replace(f"{title} ", ""),
                    "section": section,
                    "requirementCodes": codes,
                    "recommendedPages": page_by_section.get(
                        section,
                        0 if use_scoring_pages else (1 if proposal_type == "quantitative" else 3),
                    ),
                }
            )
        sections.append({"proposalType": proposal_type, "title": title, "children": children})
    return sections


def _validate_mapping(
    requirements: list[dict[str, str]],
    mappings: list[dict[str, Any]],
    extraction_warnings: list[str],
) -> dict[str, Any]:
    all_codes = [item["code"] for item in requirements]
    mapped_codes = [item["code"] for item in mappings if item.get("targetSection") and item.get("status") == "mapped"]
    unmapped = [code for code in all_codes if code not in mapped_codes]
    ambiguous = [item["code"] for item in mappings if item.get("status") != "mapped"]
    is_complete = bool(all_codes) and not unmapped and not ambiguous and not extraction_warnings
    return {
        "totalRequirements": len(all_codes),
        "mappedRequirements": len(mapped_codes),
        "unmappedRequirements": unmapped,
        "ambiguousRequirements": ambiguous,
        "isComplete": is_complete,
        "message": _validation_message(all_codes, unmapped, ambiguous, extraction_warnings),
    }


def _detect_document_types(proposal_sheets: dict[str, Any]) -> list[dict[str, Any]]:
    items = proposal_sheets.get("checklist", {}).get("items") or []
    names = " ".join(str(item.get("document", "")) for item in items if isinstance(item, dict))
    return [
        {"type": "quantitative", "label": "정량제안서", "detected": "정량" in names},
        {"type": "qualitative", "label": "정성제안서", "detected": "정성" in names or "기술제안" in names},
    ]


def _section_codes(mappings: list[dict[str, Any]], proposal_type: str | None = None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for mapping in mappings:
        if proposal_type and mapping.get("proposalType") != proposal_type:
            continue
        result.setdefault(mapping.get("targetSection", ""), []).append(mapping.get("code", ""))
    return result


def _ordered_sections(mappings: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for mapping in mappings:
        section = mapping.get("targetSection", "")
        if section and section not in seen:
            seen.append(section)
    return seen


def _validation_message(
    all_codes: list[str],
    unmapped: list[str],
    ambiguous: list[str],
    extraction_warnings: list[str],
) -> str:
    if extraction_warnings:
        return extraction_warnings[0]
    if not all_codes:
        return "제안요구사항 코드가 추출되지 않아 누락 0 검증을 완료할 수 없습니다."
    if unmapped:
        return "목차에 매핑되지 않은 요구사항이 있습니다."
    if ambiguous:
        return "매핑이 애매한 요구사항이 있어 확인이 필요합니다."
    return "모든 요구사항이 원문 코드 기준으로 목차에 1:1 매핑되었습니다."


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" -:：\t\r\n")


def _fold_text(value: str) -> str:
    return unicodedata.normalize("NFC", value or "").upper()
