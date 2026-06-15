from __future__ import annotations

import json
import re
from typing import Any

from .config import ANALYSIS_VERSION
from .llm_analyzer import chat_json, clip
from .text_extractor import clean_text


DETAIL_LABELS = [
    "공고종류",
    "수요기관",
    "사업(과제)명",
    "담당자 연락처",
    "입찰공고번호",
    "공고명",
    "입찰 참가 자격",
    "공동수급협정서 제출 및 구성방식",
    "입찰방식",
    "서류일자(=제출일자=입찰일자)",
    "세부품명",
    "낙찰방법세부기준",
    "계약방법",
    "낙찰방법",
    "계약구분",
    "사업금액",
    "납품기한(사업수행기간)",
    "제안 발표",
    "비고",
]


def generate_proposal_sheets(payload: dict[str, Any]) -> dict[str, Any]:
    documents = payload.get("documents") or []
    source_documents = [
        {
            "fileName": document.get("fileName", ""),
            "docType": document.get("docType", ""),
            "documentText": clean_text(document.get("documentText", "")),
        }
        for document in documents
        if clean_text(document.get("documentText", ""))
    ]
    bid_no = payload.get("bidNtceNo", "")
    bid_ord = payload.get("bidNtceOrd", "000")
    notice_id = f"{bid_no}-{bid_ord}" if bid_no else ""
    source_file = (payload.get("source") or {}).get("fileName", "")

    fallback = rule_proposal_sheets(source_documents, notice_id, source_file, payload.get("analyzedAt", ""))
    result = llm_proposal_sheets(source_documents, fallback)
    result["id"] = notice_id or result.get("id", "")
    result["sourceFile"] = source_file or result.get("sourceFile", "")
    result["generatedAt"] = payload.get("analyzedAt") or result.get("generatedAt", "")
    result["match"] = {
        "noticeId": notice_id,
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_ord,
        "noticeNumber": notice_id,
        "projectName": result["noticeInfo"]["summary"].get("projectName", ""),
        "keywords": [
            value
            for value in [
                result["noticeInfo"]["summary"].get("projectName", ""),
                result["noticeInfo"]["summary"].get("agency", ""),
                notice_id,
            ]
            if value
        ],
    }
    result["analysisVersion"] = ANALYSIS_VERSION
    return normalize_proposal_sheets(result, fallback)


def llm_proposal_sheets(source_documents: list[dict[str, str]], fallback: dict[str, Any]) -> dict[str, Any]:
    if not source_documents:
        return fallback

    excerpts = []
    remaining = 26000
    for document in source_documents:
        text = document["documentText"]
        if remaining <= 0:
            break
        excerpt = text[: min(len(text), remaining)]
        remaining -= len(excerpt)
        excerpts.append(
            {
                "fileName": document["fileName"],
                "docType": document["docType"],
                "text": excerpt,
            }
        )

    messages = [
        {
            "role": "system",
            "content": (
                "너는 정부/공공기관 사업 공고문 분석 전문가다. 반드시 제공된 첨부파일 원문 텍스트에 근거해서만 "
                "제안 준비용 3개 시트 데이터를 JSON으로 만든다. 기존 요약이나 외부 지식은 사용하지 않는다. "
                "문서에 없는 값은 빈 문자열로 둔다."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 원문 텍스트만 사용해서 SKILL.md의 3개 시트 결과를 웹 JSON으로 추출해줘.\n"
                "반드시 순수 JSON만 반환하고, 스키마는 다음과 같아.\n"
                "{"
                "\"noticeInfo\":{\"details\":[{\"label\":\"\",\"value\":\"\",\"note\":\"\"}],"
                "\"requirements\":[{\"requirement\":\"\",\"detail\":\"\",\"type\":\"필수|선택|배제요건|확인\"}],"
                "\"summary\":{\"projectName\":\"\",\"agency\":\"\",\"noticeNumber\":\"\",\"budget\":\"\",\"period\":\"\",\"deadline\":\"\",\"method\":\"\",\"contractMethod\":\"\"}},"
                "\"checklist\":{\"title\":\"제출 서류 목록\",\"subtitle\":\"\",\"method\":\"\","
                "\"headers\":[\"No\",\"제출서류\",\"서식\",\"담당자\",\"주관기관\",\"마감일\",\"비고\"],"
                "\"organizationHeaders\":[\"주관기관\"],"
                "\"items\":[{\"no\":1,\"document\":\"\",\"form\":\"\",\"owner\":\"GO 또는 담당부서 또는 빈값\","
                "\"organizations\":[{\"name\":\"주관기관\",\"required\":true,\"checked\":false}],"
                "\"deadline\":\"\",\"note\":\"\",\"extra\":\"\"}],\"notes\":[\"\"]},"
                "\"scoring\":{\"title\":\"배점표 분석\",\"totalSummary\":\"\","
                "\"items\":[{\"major\":\"\",\"middle\":\"\",\"minor\":\"\",\"score\":0,\"weight\":0,\"grade\":\"A|B|C\",\"strategy\":\"\",\"detail\":\"\"}],"
                "\"totals\":{\"score\":0,\"weight\":0,\"gradeA\":0,\"gradeB\":0,\"gradeC\":0}}"
                "}\n\n"
                "추출 규칙:\n"
                "- noticeInfo.details는 공고종류, 수요기관, 사업(과제)명, 담당자 연락처, 입찰공고번호, 공고명, 입찰 참가 자격, "
                "공동수급협정서 제출 및 구성방식, 입찰방식, 서류일자(=제출일자=입찰일자), 세부품명, 낙찰방법세부기준, "
                "계약방법, 낙찰방법, 계약구분, 사업금액, 납품기한(사업수행기간), 제안 발표, 비고 순서를 유지한다.\n"
                "- checklist.items는 실제 제출해야 하는 서류만 넣는다. 별지/별첨 서식 자체, 평가 전환 시에만 필요한 조건부 서류는 제외한다.\n"
                "- 대체 가능 서류, 발급처, 제본/파일명/제출방식 유의사항은 note 또는 notes에 넣는다.\n"
                "- scoring.items는 평가항목과 배점이 원문에 있을 때만 구조화한다. 없으면 빈 배열로 둔다.\n"
                "- score 비중 기준: 15점 이상 A, 10점 이상 B, 그 미만 C. 전략은 등급에 맞춰 짧게 쓴다.\n\n"
                + json.dumps({"sourceDocuments": excerpts}, ensure_ascii=False)
            ),
        },
    ]
    try:
        result = chat_json(messages, timeout=90)
        if not isinstance(result, dict):
            return fallback
        if not all(isinstance(result.get(key), dict) for key in ("noticeInfo", "checklist", "scoring")):
            return fallback
        return result
    except Exception:
        return fallback


def rule_proposal_sheets(
    source_documents: list[dict[str, str]],
    notice_id: str,
    source_file: str,
    generated_at: str,
) -> dict[str, Any]:
    text = "\n\n".join(f"[{item['fileName']}]\n{item['documentText']}" for item in source_documents)
    title = find_value(text, [r"입찰건명[:：]\s*(.+?)(?:\s+[나-하]\.\s|$)", r"공고명[:：]\s*(.+?)(?:\n|$)"])
    agency = find_value(text, [r"수요기관[:：]\s*(.+?)(?:\n|$)", r"발주기관[:：]\s*(.+?)(?:\n|$)"])
    budget = find_value(text, [r"사업예산[:：]\s*(.+?)(?:\s+[바-하]\.\s|$)", r"사업금액[:：]\s*(.+?)(?:\n|$)"])
    deadline = find_datetime(
        text,
        [
            "입찰서제출 마감일시",
            "제안서제출 마감일시",
            "제안서 제출 마감일시",
            "제출 마감일시",
            "마감일시",
            "제출기한",
        ],
    )
    method = find_value(text, [r"입찰방법[:：]\s*(.+?)(?:\s+[라-하]\.\s|$)", r"계약방법[:：]\s*(.+?)(?:\n|$)"])
    period = find_value(text, [r"사업기간[:：]\s*(.+?)(?:\s+[마-하]\.\s|$)", r"납품기한[:：]\s*(.+?)(?:\n|$)"])
    qualification = numbered_section(text, "입찰참가자격", "낙찰자 결정방법") or section(
        text,
        r"(?:입찰참가자격|입찰 참가 자격)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|낙찰자|제출 서류|제출서류|$)",
    )
    submit_section = numbered_section(text, "입찰 참가 제출 서류", "입찰보증금") or section(
        text,
        r"(?:제출 서류|제출서류|구비서류|입찰 참가 제출 서류)[-\s:：]*(.+?)(?:입찰보증금|입찰의 무효|$)",
    )
    score_section = extract_score_section(text)

    details = [
        {"label": label, "value": "", "note": ""}
        for label in DETAIL_LABELS
    ]
    set_detail(details, "공고종류", "용역 공고" if "용역" in text else "")
    set_detail(details, "수요기관", agency)
    set_detail(details, "사업(과제)명", title)
    set_detail(details, "입찰공고번호", notice_id)
    set_detail(details, "공고명", title)
    set_detail(details, "입찰 참가 자격", clip(qualification, 900))
    set_detail(details, "공동수급협정서 제출 및 구성방식", infer_joint_contract(text))
    set_detail(details, "입찰방식", method)
    set_detail(details, "서류일자(=제출일자=입찰일자)", deadline, "마감 확인" if deadline else "")
    set_detail(details, "낙찰방법세부기준", clip(score_section, 500))
    set_detail(details, "계약방법", method)
    set_detail(details, "낙찰방법", method)
    set_detail(details, "사업금액", budget)
    set_detail(details, "납품기한(사업수행기간)", period)
    set_detail(details, "제안 발표", find_presentation_info(text))
    set_detail(details, "비고", "첨부파일 원문 텍스트 기반 자동 추출")

    checklist = parse_submission_documents(submit_section, deadline) or parse_submission_documents(text, deadline)
    score_items = parse_score_items(score_section or text)
    return {
        "id": notice_id,
        "sourceFile": source_file,
        "generatedAt": generated_at,
        "match": {
            "noticeId": notice_id,
            "bidNtceNo": notice_id.split("-")[0] if "-" in notice_id else "",
            "bidNtceOrd": notice_id.split("-")[1] if "-" in notice_id else "",
            "noticeNumber": notice_id,
            "projectName": title,
            "keywords": [title, agency, notice_id],
        },
        "noticeInfo": {
            "details": details,
            "requirements": parse_requirements(qualification),
            "summary": {
                "projectName": title,
                "agency": agency,
                "noticeNumber": notice_id,
                "budget": budget,
                "period": period,
                "deadline": deadline,
                "method": method,
                "contractMethod": method,
            },
        },
        "checklist": {
            "title": "제출 서류 목록",
            "subtitle": f"사업(과제)명: {title}",
            "method": f"제출방법: {method}",
            "headers": ["No", "제출서류", "서식", "담당자", "주관기관", "마감일", "비고"],
            "organizationHeaders": ["주관기관"],
            "items": checklist,
            "notes": ["첨부파일 원문 텍스트 기반 자동 추출 결과입니다. 최종 제출 전 원문 검증이 필요합니다."],
        },
        "scoring": {
            "title": "배점표 분석",
            "totalSummary": f"평가항목 {len(score_items)}개 추출" if score_items else "명시적인 배점표 확인 필요",
            "items": score_items,
            "totals": score_totals(score_items),
        },
    }


def normalize_proposal_sheets(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    result = result or fallback
    notice_info = result.get("noticeInfo") if isinstance(result.get("noticeInfo"), dict) else fallback["noticeInfo"]
    checklist = result.get("checklist") if isinstance(result.get("checklist"), dict) else fallback["checklist"]
    scoring = result.get("scoring") if isinstance(result.get("scoring"), dict) else fallback["scoring"]

    details = notice_info.get("details") if isinstance(notice_info.get("details"), list) else fallback["noticeInfo"]["details"]
    details_by_label = {
        str(item.get("label", "")): {
            "label": str(item.get("label", "")),
            "value": clean_text(str(item.get("value", ""))),
            "note": clean_text(str(item.get("note", ""))),
        }
        for item in details
        if isinstance(item, dict)
    }
    normalized_details = [
        details_by_label.get(label, {"label": label, "value": "", "note": ""})
        for label in DETAIL_LABELS
    ]
    for item in normalized_details:
        item["value"] = normalize_detail_value(item["label"], item["value"])

    requirements = [
        {
            "requirement": clean_text(str(item.get("requirement", ""))),
            "detail": clean_text(str(item.get("detail", ""))),
            "type": clean_text(str(item.get("type", "확인"))),
        }
        for item in notice_info.get("requirements", [])
        if isinstance(item, dict)
    ] or fallback["noticeInfo"]["requirements"]

    items = normalize_checklist(checklist.get("items", []), fallback["checklist"]["items"])
    score_items = normalize_scores(scoring.get("items", []), fallback["scoring"]["items"])
    fallback_score_items = fallback["scoring"]["items"]
    if len(fallback_score_items) > len(score_items):
        score_items = fallback_score_items
    summary = notice_info.get("summary") if isinstance(notice_info.get("summary"), dict) else {}
    normalized = {
        **fallback,
        **result,
        "noticeInfo": {
            "details": normalized_details,
            "requirements": requirements,
            "summary": {
                **fallback["noticeInfo"]["summary"],
                **{key: normalize_summary_value(key, clean_text(str(value))) for key, value in summary.items() if value is not None},
            },
        },
        "checklist": {
            **fallback["checklist"],
            **checklist,
            "items": items,
            "notes": [clean_text(str(item)) for item in checklist.get("notes", []) if str(item).strip()]
            or fallback["checklist"]["notes"],
        },
        "scoring": {
            **fallback["scoring"],
            **scoring,
            "items": score_items,
            "totals": score_totals(score_items),
        },
    }
    return normalized


def normalize_checklist(items: Any, fallback_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return fallback_items
    normalized = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        document = clean_text(str(item.get("document", "")))
        if not document:
            continue
        organizations = item.get("organizations")
        if not isinstance(organizations, list) or not organizations:
            organizations = [{"name": "주관기관", "required": True, "checked": False}]
        normalized.append(
            {
                "no": int(item.get("no") or index),
                "document": document,
                "form": clean_text(str(item.get("form", ""))),
                "owner": clean_text(str(item.get("owner", ""))),
                "organizations": [
                    {
                        "name": clean_text(str(org.get("name", "주관기관"))) if isinstance(org, dict) else "주관기관",
                        "required": bool(org.get("required", True)) if isinstance(org, dict) else True,
                        "checked": bool(org.get("checked", False)) if isinstance(org, dict) else False,
                    }
                    for org in organizations
                ],
                "deadline": normalize_date_text(clean_text(str(item.get("deadline", "")))),
                "note": clean_text(str(item.get("note", ""))),
                "extra": clean_text(str(item.get("extra", ""))),
            }
        )
    return normalized or fallback_items


def normalize_scores(items: Any, fallback_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return fallback_items
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        minor = clean_text(str(item.get("minor", "")))
        if not minor:
            continue
        score = float(item.get("score") or 0)
        grade = clean_text(str(item.get("grade", ""))) or grade_for_score(score)
        normalized.append(
            {
                "major": clean_text(str(item.get("major", ""))),
                "middle": clean_text(str(item.get("middle", ""))),
                "minor": minor,
                "score": score,
                "weight": float(item.get("weight") or score),
                "grade": grade,
                "strategy": clean_text(str(item.get("strategy", ""))) or strategy_by_grade(grade),
                "detail": clean_text(str(item.get("detail", ""))),
            }
        )
    return normalized or fallback_items


def find_value(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return clip(clean_bound_value(match.group(1)), 500)
    return ""


def section(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def numbered_section(text: str, start_title: str, end_title: str) -> str:
    pattern = rf"(?:^|\n|\s)\d+\.\s*{re.escape(start_title)}[-\s–—]*?(.+?)(?:\n?-?\d+\.\s*{re.escape(end_title)}|$)"
    match = re.search(pattern, text, re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def extract_score_section(text: str) -> str:
    candidates = [
        numbered_section(text, "낙찰자 결정방법 및 협상", "입찰무효"),
        numbered_section(text, "협상대상자 선정 및 협상기준", "입찰무효"),
        numbered_section(text, "제안서 평가", "입찰참가"),
        numbered_section(text, "평가기준", "제출"),
        section(text, r"(?:평가항목|평가기준|배점표|배점)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|계약|제출|$)"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate

    keyword_match = re.search(r"(?:협상순서|기술능력평가\s*\d+(?:\.\d+)?\s*%|기술평가|가격평가|입찰가격평가|배점)", text)
    if not keyword_match:
        return ""
    start = max(0, keyword_match.start() - 900)
    end = min(len(text), keyword_match.end() + 1800)
    return clean_text(text[start:end])


def clean_bound_value(value: str) -> str:
    value = clean_text(value)
    value = re.split(r"\s+[가-하]\.\s+(?=[가-힣A-Za-z(])", value, maxsplit=1)[0]
    value = re.split(r"\s+\d+\.\s+(?=[가-힣A-Za-z(])", value, maxsplit=1)[0]
    return clean_text(value)


def find_datetime(text: str, labels: list[str]) -> str:
    datetime_pattern = r"\d{4}[.\-]\s*\d{1,2}[.\-]\s*\d{1,2}\.?\s*(?:\([^)]+\))?\s*,?\s*\d{1,2}:\d{2}"
    date_pattern = r"\d{4}[.\-]\s*\d{1,2}[.\-]\s*\d{1,2}\.?\s*(?:\([^)]+\))?"
    for label in labels:
        label_pattern = re.escape(label).replace(r"\ ", r"\s*")
        window_match = re.search(rf"{label_pattern}[:：]?\s*(.{{0,180}})", text, re.DOTALL)
        if not window_match:
            continue
        window = window_match.group(1)
        match = re.search(datetime_pattern, window) or re.search(date_pattern, window)
        if match:
            return clean_text(match.group(0))
    return ""


def normalize_detail_value(label: str, value: str) -> str:
    if "일자" in label or "마감" in label:
        return normalize_date_text(value)
    if label == "입찰 참가 자격":
        return trim_qualification(value)
    return clean_bound_value(value)


def normalize_summary_value(key: str, value: str) -> str:
    if key in {"deadline"}:
        return normalize_date_text(value)
    return clean_bound_value(value)


def normalize_date_text(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    match = re.search(r"\d{4}[.\-]\s*\d{1,2}[.\-]\s*\d{1,2}\.?\s*(?:\([^)]+\))?\s*,?\s*\d{1,2}:\d{2}", value)
    if match:
        return clean_text(match.group(0))
    match = re.search(r"\d{4}[.\-]\s*\d{1,2}[.\-]\s*\d{1,2}\.?\s*(?:\([^)]+\))?", value)
    return clean_text(match.group(0)) if match else clean_bound_value(value)


def trim_qualification(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"^-{5,}\s*", "", value)
    value = re.sub(r"※\s*제\s*안\s*서.*$", "", value)
    return clip(value, 900)


def find_presentation_info(text: str) -> str:
    match = re.search(r"(발표방법[:：]\s*.+?)(?:\s*-\s*발표순서|\s*-\s*참고사항|$)", text, re.DOTALL)
    if match:
        return clip(clean_bound_value(match.group(1)), 300)
    match = re.search(r"(제안서평가 일시 및 장소[:：]\s*.+?)(?:\s*-\s*사업금액|$)", text, re.DOTALL)
    return clip(clean_bound_value(match.group(1)), 300) if match else ""


def set_detail(details: list[dict[str, str]], label: str, value: str, note: str = ""):
    for item in details:
        if item["label"] == label:
            item["value"] = value
            item["note"] = note
            return


def infer_joint_contract(text: str) -> str:
    if "공동계약 가능" in text or "공동수급체" in text:
        return "공동계약 가능 또는 공동수급 관련 조건 있음"
    if "공동수급 불허" in text or "공동계약 불가" in text:
        return "공동수급 불허"
    return ""


def parse_requirements(text: str) -> list[dict[str, str]]:
    chunks = re.split(r"\s+[가-하]\.\s+|\s+\d+\)\s+", trim_qualification(text))
    rows = []
    for chunk in chunks:
        chunk = clip(chunk, 500)
        if not chunk:
            continue
        rows.append({"requirement": chunk[:40], "detail": chunk, "type": "필수" if "하여야" in chunk or "필" in chunk else "확인"})
    return rows[:12] or [{"requirement": "공고문 확인", "detail": "입찰 참가 요건 원문 확인 필요", "type": "확인"}]


def parse_submission_documents(text: str, deadline: str) -> list[dict[str, Any]]:
    text = clean_text(text)
    candidates = [
        ("입찰참가신청서", "별지 1", ""),
        ("조달청 경쟁입찰 참가 등록증", "", "조달청 나라장터 출력. 컴퓨터관련서비스업(1468) 또는 디지털콘텐츠개발서비스업(1469) 확인"),
        ("4대보험완납증명서", "", ""),
        ("이행(입찰)보증보험증권", "", "입찰금액의 100분의 5 이상"),
        ("기업신용평가 등급확인서", "", ""),
        ("인감증명서", "", "법인인 경우 법인인감증명서 및 법인등기부등본 각 1부"),
        ("사용인감계", "", "인감도장 입찰참가 신청 시 지참"),
        ("사업자등록증 사본", "", ""),
        ("국세・지방세 완납증명서", "", "각 1부"),
        ("확약서", "별지 2", ""),
        ("청렴계약서", "별지 3", ""),
        ("보안서약서", "별지 4", ""),
        ("최근 결산기준 재무상태 및 재무제표", "", ""),
        ("대표자 위임장, 재직증명서, 신분증", "별지 5", "대리인의 경우에 한함"),
        ("개인정보 수집 이용 동의서", "별지 6", ""),
        ("정량제안서", "", "2부. 제안요청서 P.16~22 참고, 정량평가 자가진단서 첨부"),
        ("정성제안서", "", "10부. 원본 1부, 사본 9부는 제안사명 및 로고 미표기"),
        ("제안서(발표용 PPT)가 포함된 USB", "", "각 1개. 원본 1개, 사본 1개"),
    ]
    items = []
    for name, form, default_note in candidates:
        if name in text:
            note = extract_doc_note(text, name, default_note)
            items.append(
                {
                    "no": len(items) + 1,
                    "document": name,
                    "form": form,
                    "owner": "GO" if is_external_document(name) else "",
                    "organizations": [{"name": "주관기관", "required": True, "checked": False}],
                    "deadline": normalize_date_text(deadline),
                    "note": note,
                    "extra": "",
                }
            )
    return items


def parse_score_items(text: str) -> list[dict[str, Any]]:
    text = clean_text(text)
    detailed_items = parse_detailed_score_items(text)
    if detailed_items:
        return detailed_items

    items = []
    paired = re.search(
        r"(기술(?:능력)?평가)\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?.*?"
        r"(?:입찰)?(가격평가)\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?",
        text,
    )
    if paired:
        detail = score_context(text)
        for label, score_text in [(paired.group(1), paired.group(2)), (paired.group(3), paired.group(4))]:
            score = float(score_text)
            grade = grade_for_score(score)
            items.append(
                {
                    "major": "평가항목",
                    "middle": "협상 적격자 평가",
                    "minor": label,
                    "score": score,
                    "weight": score,
                    "grade": grade,
                    "strategy": strategy_by_grade(grade),
                    "detail": detail,
                }
            )
        return items

    slash_pair = re.search(
        r"(기술(?:능력)?평가)\s*(\d+(?:\.\d+)?)\s*%\s*/\s*(?:입찰)?(가격평가)\s*(\d+(?:\.\d+)?)\s*%",
        text,
    )
    if slash_pair:
        detail = score_context(text)
        for label, score_text in [(slash_pair.group(1), slash_pair.group(2)), (slash_pair.group(3), slash_pair.group(4))]:
            score = float(score_text)
            grade = grade_for_score(score)
            items.append(
                {
                    "major": "평가항목",
                    "middle": "협상 적격자 평가",
                    "minor": label,
                    "score": score,
                    "weight": score,
                    "grade": grade,
                    "strategy": strategy_by_grade(grade),
                    "detail": detail,
                }
            )
        return items

    for label, score_text in re.findall(r"([가-힣A-Za-z0-9·ㆍ/\s]{2,40}?)[(:：\s]+(\d+(?:\.\d+)?)\s*(?:점|%)", text):
        label = clean_text(label).strip("()")
        if not label or label in {"총점"} or "마감" in label or label.endswith("한도의"):
            continue
        score = float(score_text)
        grade = grade_for_score(score)
        items.append(
            {
                "major": "평가항목",
                "middle": "",
                "minor": clip(label, 80),
                "score": score,
                "weight": score,
                "grade": grade,
                "strategy": strategy_by_grade(grade),
                "detail": f"{clip(label, 120)} {score:g}점",
            }
        )
    return items[:30]


def parse_detailed_score_items(text: str) -> list[dict[str, Any]]:
    text = clean_text(text)
    if "제안서 기술능력평가 평가항목 및 배점 한도" not in text:
        return []

    section_match = re.search(
        r"제안서 기술능력평가 평가항목 및 배점 한도(.+?)(?:합\s*계\s*100점|※\s*평가점수 산정 방법)",
        text,
        re.DOTALL,
    )
    score_text = section_match.group(1) if section_match else text
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
        ("가격평가", "가격", "금액", 40),
    ]

    items = []
    normalized_score_text = re.sub(r"\s+", "", score_text)
    for index, (major, middle, minor, score) in enumerate(specs):
        compact_minor = re.sub(r"\s+", "", minor)
        if compact_minor not in normalized_score_text and not (minor == "금액" and "가격(40)" in normalized_score_text):
            continue
        detail = extract_score_detail(score_text, minor, specs[index + 1][2] if index + 1 < len(specs) else "")
        grade = grade_for_score(float(score))
        items.append(
            {
                "major": major,
                "middle": middle,
                "minor": minor,
                "score": float(score),
                "weight": float(score),
                "grade": grade,
                "strategy": strategy_by_grade(grade),
                "detail": detail,
            }
        )
    return items


def extract_score_detail(text: str, current_label: str, next_label: str) -> str:
    current_pattern = label_pattern(current_label)
    if current_label == "금액":
        current_pattern = r"가격\s*\(40\)\s*금\s*액"
    next_pattern = label_pattern(next_label) if next_label else r"합\s*계|※"
    match = re.search(rf"({current_pattern}.+?)(?:{next_pattern}|$)", text, re.DOTALL)
    if not match:
        return ""
    detail = re.sub(r"\s+", " ", match.group(1))
    detail = re.sub(r"\b(?:5|4\.5|4|3\.75|3\.5|10|9|8|7\.5|7)\b(?:\s+|$)", " ", detail)
    detail = re.sub(r"\s+(?:정량|정성)\s*평\s*가\s*\(\d+(?:\.\d+)?\)\s*$", "", detail)
    detail = re.sub(r"\s+가격\s*\(\d+(?:\.\d+)?\)\s*$", "", detail)
    detail = detail.replace("평가체 계", "평가체계")
    return clip(detail, 260)


def label_pattern(label: str) -> str:
    parts = []
    for char in label:
        if char.isspace():
            parts.append(r"\s*")
        else:
            parts.append(re.escape(char) + r"\s*")
    return "".join(parts)


def extract_doc_note(text: str, name: str, default_note: str) -> str:
    if name == "인감증명서":
        return default_note
    start = text.find(name)
    if start < 0:
        return default_note
    fragment = text[start + len(name): start + len(name) + 120]
    fragment = re.sub(r"^(?:각?\s*)?\d+\s*부", "", fragment)
    fragment = re.sub(r"^각?\s*1\s*개", "", fragment)
    fragment = re.split(r"\d{1,2}[가-힣A-Za-z]", fragment, maxsplit=1)[0]
    fragment = clean_text(fragment)
    if not fragment or len(fragment) < 6 or re.fullmatch(r"별지\s*\d*", fragment):
        return default_note
    if default_note and len(fragment) < len(default_note):
        return default_note
    return fragment or default_note


def is_external_document(name: str) -> bool:
    return any(key in name for key in ["증명서", "등록증", "완납", "보험증권", "사업자등록증", "재무제표", "확인서"])


def score_context(text: str) -> str:
    text = clean_text(re.sub(r"-{5,}", " ", text))
    match = re.search(
        r"협상순서는.+?기술(?:능력)?평가\s*\d+(?:\.\d+)?%?.+?(?:입찰)?가격평가\s*\d+(?:\.\d+)?%?.+?진행하며",
        text,
    )
    if match:
        return clip(match.group(0), 260)
    match = re.search(r"제안서 평가는.+?기술(?:능력)?평가\(?\d+(?:\.\d+)?(?:점|%)\)?.+?(?:입찰)?가격평가\(?\d+(?:\.\d+)?(?:점|%)\)?.+?함", text)
    if match:
        return clip(match.group(0), 260)
    match = re.search(r"배점은\s*기술(?:능력)?평가\(?\d+(?:\.\d+)?(?:점|%)\)?.+?(?:입찰)?가격평가\(?\d+(?:\.\d+)?(?:점|%)\)?.+?함", text)
    if match:
        return clip(match.group(0), 260)
    return clip(text, 260)


def grade_for_score(score: float) -> str:
    if score >= 15:
        return "A"
    if score >= 10:
        return "B"
    return "C"


def strategy_by_grade(grade: str) -> str:
    if grade == "A":
        return "Win Theme 핵심 적용. 독자적 방법론과 정량 목표를 전면 배치"
    if grade == "B":
        return "요건 충족과 실적 근거를 연결해 충실하게 작성"
    return "누락 방지 중심으로 증빙과 기본 요건 확인"


def score_totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "score": sum(float(item.get("score") or 0) for item in items),
        "weight": sum(float(item.get("weight") or 0) for item in items),
        "gradeA": sum(1 for item in items if item.get("grade") == "A"),
        "gradeB": sum(1 for item in items if item.get("grade") == "B"),
        "gradeC": sum(1 for item in items if item.get("grade") == "C"),
    }
