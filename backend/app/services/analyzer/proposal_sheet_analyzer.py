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

DETAIL_GROUPS = [
    {
        "category": "사업 개요",
        "labels": ["사업명", "발주처", "예산", "사업 기간", "과업 범위"],
    },
    {
        "category": "평가 방식",
        "labels": ["계약/낙찰 방식", "협상/적격심사 여부", "기술:가격 배점비", "평가 절차"],
    },
    {
        "category": "제출 형식 제한",
        "labels": ["제안서 매수 제한", "규격", "원본/사본/PDF/HWPX 등 형식"],
    },
    {
        "category": "일정·방법",
        "labels": ["마감 일시", "제출 방법·제출처", "질의응답·설명회 일정"],
    },
    {
        "category": "공동수급 의무",
        "labels": ["컨소시엄 구성 의무·제한", "주관사 지분 요건", "의무 하도급 비율"],
    },
]

REQUIREMENT_CODE_RE = re.compile(r"\b((?:ECR|SFR|PER|PPR|IFR|DAR|TER|SER|QUR|COR|PMR|PSR)[-_]?\d{1,4})\b")
REQUIREMENT_CATEGORY_LABELS = {
    "ECR": "장비구성 요구사항",
    "SFR": "기능 요구사항",
    "PER": "성능 요구사항",
    "PPR": "사업수행 요구사항",
    "IFR": "인터페이스 요구사항",
    "DAR": "데이터 요구사항",
    "TER": "테스트 요구사항",
    "SER": "보안 요구사항",
    "QUR": "품질 요구사항",
    "COR": "제약사항",
    "PMR": "프로젝트관리 요구사항",
    "PSR": "프로젝트지원 요구사항",
}

REQUIREMENT_TABLE_MARKERS = [
    "요구사항 총괄표",
    "요구사항총괄표",
    "요구사항 목록",
    "요구사항목록",
    "제안요구사항",
    "제안 요구사항",
    "요구사항 명세",
    "요구사항명세",
    "상세 요구사항",
    "요구사항 상세",
]

REQUIREMENT_TABLE_END_MARKERS = [
    "요구사항 상세",
    "상세 요구사항",
    "제안서 작성",
    "제안서 제출",
    "평가항목",
    "평가기준",
    "별첨",
    "붙임",
]

REQUIREMENT_HEADER_WORDS = {
    "번호",
    "순번",
    "구분",
    "분류",
    "요구사항",
    "요구사항명",
    "요구사항 명",
    "요구사항 명칭",
    "요구사항명칭",
    "요구사항 고유번호",
    "요구사항고유번호",
    "고유번호",
    "코드",
    "ID",
    "아이디",
    "설명",
    "세부내용",
    "세부 내용",
    "비고",
}

SCORING_TABLE_MARKERS = [
    "기술제안서 평가 기준 및 배점",
    "기술제안서 평가기준 및 배점",
    "제안서 평가 기준 및 배점",
    "제안서 평가기준 및 배점",
    "평가 항목 및 평가 기준",
    "평가항목 및 평가기준",
    "평가 항목 및 배점 기준",
    "평가항목 및 배점기준",
    "평가항목 및 배점 한도",
    "평가항목 및 배점한도",
    "평가항목 및 배점",
    "제안서 기술능력평가 평가항목 및 배점 한도",
    "기술능력평가 평가항목 및 배점 한도",
    "기술평가 항목",
    "기술평가항목",
]

SCORING_SECTION_MARKERS = [
    "제안서 평가 방법",
    "제안서 평가방법",
    "평가 방법",
    "평가방법",
    "기술능력 평가",
    "기술평가",
]

SCORING_END_MARKERS = [
    "평가 세부기준",
    "평가세부기준",
    "입찰시 유의사항",
    "입찰 시 유의사항",
    "계약사항",
    "제안서 작성",
    "기타사항",
    "붙임",
]


def generate_proposal_sheets(payload: dict[str, Any], use_llm: bool = True) -> dict[str, Any]:
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
    result = llm_proposal_sheets(source_documents, fallback) if use_llm else fallback
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

    excerpts = build_llm_source_excerpts(source_documents)
    all_text = "\n\n".join(f"[{item['fileName']}]\n{item['documentText']}" for item in source_documents)
    rule_requirements = parse_requirements(all_text, "")
    rule_scoring = parse_score_items(all_text)
    rule_checklist = parse_submission_documents(all_text, fallback["noticeInfo"]["summary"].get("deadline", ""))

    messages = [
        {
            "role": "system",
            "content": (
                "너는 정부/공공기관 RFP·공고문을 제안서 작성 관점으로 정밀 분석하는 전문가다. "
                "반드시 제공된 첨부파일 원문 텍스트에 근거해서만 JSON을 만든다. 외부 지식, 추측, 임의 보완은 금지다. "
                "특히 요구사항 코드는 원문 문자를 절대 수정하지 않는 전사(transcription) 업무로 처리한다."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 원문 텍스트만 사용해서 proposal-analyzer 핵심정보 요약 결과를 웹 JSON으로 추출해줘.\n"
                "반드시 순수 JSON만 반환하고, 스키마는 다음과 같아.\n"
                "{"
                "\"noticeInfo\":{\"details\":[{\"label\":\"\",\"value\":\"\",\"note\":\"\"}],"
                "\"detailGroups\":[{\"category\":\"사업 개요|평가 방식|제출 형식 제한|일정·방법|공동수급 의무\","
                "\"items\":[{\"label\":\"\",\"value\":\"\",\"note\":\"\"}]}],"
                "\"requirements\":[{\"code\":\"원문 코드 그대로 또는 빈값\",\"requirement\":\"요구사항명 원문 그대로\","
                "\"name\":\"요구사항명 원문 그대로\",\"detail\":\"\",\"type\":\"필수|선택|배제요건|확인\","
                "\"category\":\"ECR|SFR|PER|PPR|IFR|DAR|TER|SER|QUR|COR|PMR|PSR 또는 원문 분류\",\"source\":\"\"}],"
                "\"risks\":[{\"title\":\"\",\"detail\":\"\",\"severity\":\"주의|높음|확인\"}],"
                "\"clarifications\":[{\"question\":\"\",\"reason\":\"\"}],"
                "\"summary\":{\"projectName\":\"\",\"agency\":\"\",\"noticeNumber\":\"\",\"budget\":\"\",\"period\":\"\",\"deadline\":\"\",\"method\":\"\",\"contractMethod\":\"\"}},"
                "\"checklist\":{\"title\":\"제출 서류 목록\",\"subtitle\":\"\",\"method\":\"\","
                "\"headers\":[\"No\",\"제출서류\",\"서식\",\"담당자\",\"주관기관\",\"마감일\",\"비고\"],"
                "\"organizationHeaders\":[\"주관기관(대표사)\"],"
                "\"items\":[{\"no\":1,\"document\":\"\",\"form\":\"\",\"owner\":\"GO 또는 담당부서 또는 빈값\","
                "\"organizations\":[{\"name\":\"주관기관(대표사)\",\"required\":true,\"checked\":false}],"
                "\"deadline\":\"\",\"note\":\"\",\"extra\":\"\"}],\"notes\":[\"\"]},"
                "\"scoring\":{\"title\":\"배점표 분석\",\"totalSummary\":\"\","
                "\"items\":[{\"major\":\"\",\"middle\":\"\",\"minor\":\"\",\"score\":0,\"weight\":0,\"grade\":\"A|B|C\",\"strategy\":\"\",\"detail\":\"\"}],"
                "\"totals\":{\"score\":0,\"weight\":0,\"gradeA\":0,\"gradeB\":0,\"gradeC\":0}}"
                "}\n\n"
                "추출 규칙:\n"
                "[최우선 원칙]\n"
                "- 추측·창작 금지. 공고문에 없는 내용은 빈 문자열 또는 공고문상 불명확으로 둔다.\n"
                "- 요구사항 표/목록은 빠짐없이 추출한다. 일부만 샘플링하지 않는다.\n"
                "- '요구사항 총괄표', '요구사항총괄표', '요구사항 목록', '제안요구사항' 표가 있으면 이를 requirements의 1차 원천으로 삼는다.\n"
                "- 총괄표의 한 행에 있는 코드와 요구사항명은 반드시 같은 requirements 항목으로 묶는다. 표 셀이 줄바꿈되어 있어도 앞뒤 셀을 보고 같은 행 맥락을 복원한다.\n"
                "- 원문에 있는 요구사항 코드를 임의로 정규화하지 않는다. 예: SFR-001을 SFR001로 바꾸지 말고, PER_01을 PER-001로 바꾸지 않는다.\n"
                "- 요구사항명도 원문 셀/행의 명칭을 그대로 옮긴다. 영문↔국문 변환, 축약, 의역, 임의 띄어쓰기 변경을 하지 않는다.\n"
                "- requirements[].code에는 ECR/SFR/PER/PPR/IFR/DAR/TER/SER/QUR/COR/PMR/PSR 등 원문 요구사항 코드를 그대로 넣는다. 예시 코드군 밖의 코드라도 요구사항 총괄표/상세에 있으면 누락하지 않는다. 코드가 진짜 없을 때만 빈 문자열로 둔다.\n"
                "- requirements[].requirement와 requirements[].name에는 요구사항명 원문을 동일하게 넣는다.\n"
                "- requirements[].detail에는 요구사항 설명, 세부내용, 산출물, 구현 기능을 제안자가 이해할 수 있게 요약하되 원문 근거를 벗어나지 않는다.\n"
                "- noticeInfo.details는 공고종류, 수요기관, 사업(과제)명, 담당자 연락처, 입찰공고번호, 공고명, 입찰 참가 자격, "
                "공동수급협정서 제출 및 구성방식, 입찰방식, 서류일자(=제출일자=입찰일자), 세부품명, 낙찰방법세부기준, "
                "계약방법, 낙찰방법, 계약구분, 사업금액, 납품기한(사업수행기간), 제안 발표, 비고 순서를 유지한다.\n"
                "- detailGroups는 사업 개요/평가 방식/제출 형식 제한/일정·방법/공동수급 의무로 나누고, 각 하위 label은 "
                "사업명, 발주처, 예산, 사업 기간, 과업 범위, 계약/낙찰 방식, 협상/적격심사 여부, 기술:가격 배점비, 평가 절차, "
                "제안서 매수 제한, 규격, 원본/사본/PDF/HWPX 등 형식, 마감 일시, 제출 방법·제출처, 질의응답·설명회 일정, "
                "컨소시엄 구성 의무·제한, 주관사 지분 요건, 의무 하도급 비율을 포함한다. 문서에 없으면 value를 빈 문자열로 둔다.\n"
                "- 공고정보의 사업명/발주처/예산/마감/계약방법은 공고문·입찰공고 파일을 우선 원천으로 삼고, 과업범위/제출형식/평가방식/요구사항/배점표는 제안요청서·과업지시서 파일을 우선 원천으로 삼는다. 목차, 예시표, 다른 사업명처럼 보이는 값은 사용하지 않는다.\n"
                "- requirements는 RFP/공고문에 명시된 모든 제안요구사항을 추출한다. ECR/SFR/PER/PPR/IFR/DAR/TER/SER/QUR/COR/PMR/PSR "
                "등 코드와 요구사항명은 원문 표기 그대로 옮긴다. 기능 요구사항은 무엇을 구현하라는 것인지, "
                "관리/보안/품질/제약 요구사항은 제안서에 무엇을 약속·증빙해야 하는지 detail에 구체적으로 적는다.\n"
                "- risks는 놓치기 쉬운 독소조항·특이 요건만, clarifications는 발주처 질의가 필요한 모호한 지점만 넣는다.\n"
                "- checklist는 제안서 작성 실무에서 가장 먼저 확인할 제출서류 통합 체크리스트다. 제출서류 파악을 우선한다.\n"
                "- checklist.items는 공고문에 명시된 실제 제출 서류만 넣는다. 정량 별지서식의 내용물(인력투입표, 수행실적, 재무제표, 신용평가, 청렴/보안서약, 하도급, 보험, 자격증명), 정성 기술제안서 본문, 입찰참가자격 증빙을 빠짐없이 확인한다.\n"
                "- 별지서식/별첨서식 제목 자체가 아니라 실제 제출해야 하는 서류명을 document에 넣는다. 단, 별지 번호가 문서 양식이면 form에 넣는다.\n"
                "- 제안서 내에 포함되는 작성 항목과 계약 후 제출 서식은 독립 제출서류로 만들지 않는다. '대면평가 시', '대면평가일 경우', '요청 시', '계약 체결 후'처럼 조건부/예외 서류는 제외하거나 note에 조건부로 명시한다.\n"
                "- 제출 부수·형식(원본/사본/PDF/HWP/HWPX/USB/온라인 제출), 제출처, 마감 시각, 파일명 규칙, 제출 순서가 있으면 note 또는 notes에 반드시 남긴다.\n"
                "- owner는 정부24/나라장터/세무서/보험사/신용평가기관 등 외부 발급 서류면 GO, 직접 작성 서류면 전략기획/제안작성/사업관리 등 담당부서명 또는 빈값으로 둔다.\n"
                "- organizations는 통합 시트의 기관 열이다. 주관기관(대표사)은 항상 포함한다. 공동수급/컨소시엄이 있으면 참여기관1(참여), 참여기관2(참여) 같은 placeholder 열을 추가한다. 수요기관 제출/확인이 필요하면 수요기관(수요)을 추가한다. 기관명은 추측하지 않는다.\n"
                "- organizations[].required가 true이면 사용자가 수기로 체크할 대상이며 checked는 기본 false다. 해당 없는 기관은 required=false, checked=false로 둔다.\n"
                "- 대체 가능 서류, 발급처, 제본/파일명/제출방식 유의사항은 note 또는 notes에 넣는다.\n"
                "- scoring.items는 평가항목과 배점이 원문에 있을 때만 구조화한다. 없으면 빈 배열로 둔다.\n"
                "- scoring.items는 '기술제안서 평가 기준 및 배점', '평가항목 및 배점', '기술능력평가 평가항목 및 배점' 표가 있으면 이를 1차 원천으로 삼는다.\n"
                "- 배점표가 있으면 총괄비율 90:10만 반환하지 말고 세부 평가항목을 모두 반환한다. 예: 정량평가/유사분야 수행실적/5점, 전략 및 방법론/사업이해도/5점 등.\n"
                "- scoring.items[].major에는 최상위 평가 대분류를 넣는다. 예: 기술능력평가, 가격평가. 기술 90 / 가격 10 같은 총괄 배점이 있으면 이 최상위 분류를 반드시 반영한다.\n"
                "- scoring.items[].middle에는 원문 평가항목 대분류/중분류를 넣는다. 예: 정량평가, 전략 및 방법론, 사업수행, 수행기반, 프로젝트 관리, 프로젝트 지원.\n"
                "- scoring.items[].minor에는 원문 세부평가항목명을 넣고, score/weight에는 원문 배점을 숫자로 넣는다.\n"
                "- scoring.items[].detail에는 평가기준 원문을 짧게 요약하되 원문 근거를 벗어나지 않는다.\n"
                "- 기술평가 세부항목과 가격평가가 함께 있으면 둘 다 포함한다. 다만 점수 산정 예시표의 A/B/C 업체 점수는 평가항목으로 넣지 않는다.\n"
                "- score 비중 기준: 15점 이상 A, 10점 이상 B, 그 미만 C. 전략은 등급에 맞춰 짧게 쓴다.\n\n"
                + json.dumps(
                    {
                        "sourceDocuments": excerpts,
                        "ruleDetectedRequirementCodes": rule_requirements,
                        "ruleDetectedChecklistItems": rule_checklist,
                        "ruleDetectedScoringItems": rule_scoring,
                    },
                    ensure_ascii=False,
                )
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


def build_llm_source_excerpts(source_documents: list[dict[str, str]]) -> list[dict[str, str]]:
    excerpts = []
    remaining = 62000
    for document in sorted(source_documents, key=document_priority):
        if remaining <= 0:
            break
        text = document["documentText"]
        focused = "\n\n".join(
            dedupe_preserve_order(
                [
                    collect_requirement_table_sections(text),
                    collect_scoring_table_sections(text),
                    collect_submission_sections(text),
                    clip(text, 6000),
                    collect_requirement_windows(text),
                    collect_keyword_windows(
                        text,
                        [
                            "요구사항 총괄표",
                            "요구사항총괄표",
                            "요구사항 목록",
                            "요구사항목록",
                            "제안요구사항",
                            "요구사항 명세",
                            "사업 개요",
                            "사업개요",
                            "과업 범위",
                            "과업범위",
                            "평가 방식",
                            "평가기준",
                            "배점",
                            "기술제안서 평가 기준 및 배점",
                            "기술제안서 평가기준 및 배점",
                            "평가항목 및 배점",
                            "제안서 평가방법",
                            "제안서 작성",
                            "제안서 제출",
                            "제출 서류",
                            "제출서류",
                            "구비서류",
                            "정량제안서",
                            "정성제안서",
                            "기술제안서",
                            "원본",
                            "사본",
                            "USB",
                            "PDF",
                            "HWPX",
                            "공동수급",
                            "하도급",
                            "질의",
                            "설명회",
                        ],
                    ),
                ]
            )
        )
        excerpt = focused[: min(len(focused), remaining, 18000)]
        remaining -= len(excerpt)
        excerpts.append(
            {
                "fileName": document["fileName"],
                "docType": document["docType"],
                "text": excerpt,
            }
        )
    return excerpts


def document_priority(document: dict[str, str]) -> tuple[int, str]:
    text = f"{document.get('fileName', '')} {document.get('docType', '')}".lower()
    if "제안요청" in text or "rfp" in text:
        return (0, text)
    if "과업" in text:
        return (1, text)
    if "공고" in text:
        return (2, text)
    return (3, text)


def collect_requirement_windows(text: str) -> str:
    lines = text.splitlines()
    matches = []
    for index, line in enumerate(lines):
        if REQUIREMENT_CODE_RE.search(line):
            start = max(0, index - 8)
            end = min(len(lines), index + 14)
            matches.append(clean_text("\n".join(lines[start:end])))
    return "\n\n".join(dedupe_preserve_order(matches))[:26000]


def collect_requirement_table_sections(text: str) -> str:
    folded = fold_requirement_text(text)
    snippets = []
    for marker in REQUIREMENT_TABLE_MARKERS:
        marker_position = folded.find(fold_requirement_text(marker))
        if marker_position < 0:
            continue
        end_candidates = []
        for end_marker in REQUIREMENT_TABLE_END_MARKERS:
            end_position = folded.find(fold_requirement_text(end_marker), marker_position + len(marker))
            if end_position > marker_position:
                end_candidates.append(end_position)
        end = min(end_candidates) if end_candidates else min(len(text), marker_position + 18000)
        snippets.append(clean_text(text[marker_position:end]))
    return "\n\n".join(dedupe_preserve_order(snippets))[:36000]


def collect_submission_sections(text: str) -> str:
    markers = [
        "입찰 참가 제출 서류",
        "입찰참가 제출서류",
        "제출 서류",
        "제출서류",
        "구비서류",
        "제안서 제출",
        "제안서 제출방법",
        "제안서 제출 방법",
        "제안서 작성 및 제출",
        "정량제안서",
        "정성제안서",
    ]
    end_markers = [
        "입찰보증금",
        "입찰의 무효",
        "제안서 평가",
        "평가방법",
        "협상",
        "계약",
        "기타사항",
    ]
    snippets = []
    for marker in markers:
        for match in re.finditer(loose_text_pattern(marker), text):
            start = max(0, match.start() - 900)
            window_start = match.start()
            end_candidates = []
            for end_marker in end_markers:
                end_match = re.search(loose_text_pattern(end_marker), text[window_start + len(marker):])
                if end_match:
                    end_candidates.append(window_start + len(marker) + end_match.start())
            end = min(end_candidates) if end_candidates else min(len(text), match.end() + 6000)
            snippets.append(clean_text(text[start:end]))
    return "\n\n".join(dedupe_preserve_order(snippets))[:30000]


def collect_scoring_table_sections(text: str) -> str:
    candidates: list[tuple[int, int, str]] = []
    markers = SCORING_TABLE_MARKERS + SCORING_SECTION_MARKERS
    for marker in markers:
        start_positions = [match.start() for match in re.finditer(loose_text_pattern(marker), text)]
        for marker_position in start_positions:
            window = text[marker_position:marker_position + 8000]
            if not any(token in fold_requirement_text(window) for token in ("배점", "평가항목", "기술능력평가", "가격평가", "정량평가")):
                continue
            end_candidates = []
            for end_marker in SCORING_END_MARKERS:
                end_match = re.search(loose_text_pattern(end_marker), text[marker_position + len(marker):])
                if end_match:
                    end_candidates.append(marker_position + len(marker) + end_match.start())
            end = min(end_candidates) if end_candidates else min(len(text), marker_position + 16000)
            snippet = clean_text(text[marker_position:end])
            folded_snippet = fold_requirement_text(snippet)
            score = 0
            if "평가구분평가항목세부평가항목평가기준배점" in folded_snippet:
                score += 220
            if "별표3" in folded_snippet and ("평가항목및평가기준" in folded_snippet or "평가항목및배점기준" in folded_snippet):
                score += 120
            if "세부평가항목" in folded_snippet or "새부평가항목" in folded_snippet:
                score += 80
            if marker in SCORING_TABLE_MARKERS:
                score += 120
            if "배점한도" in folded_snippet:
                score += 40
            if re.search(r"(?:^|\n|[^\d])계\s*100(?:\.0)?(?:\n|$|[^\d])", snippet):
                score += 100
            if re.search(r"(?:^|\n)계\s*\n\s*9?0(?:\.0)?(?:\n|$)", snippet):
                score += 40
            if "기술능력평가" in snippet and "입찰가격평가" in snippet:
                score += 10
            score += min(20, len(snippet) // 1000)
            candidates.append((score, marker_position, snippet))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2][:42000]


def collect_keyword_windows(text: str, keywords: list[str]) -> str:
    snippets = []
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword), text, re.IGNORECASE):
            start = max(0, match.start() - 900)
            end = min(len(text), match.end() + 2600)
            snippets.append(clean_text(text[start:end]))
            if len(snippets) >= 18:
                return "\n\n".join(dedupe_preserve_order(snippets))[:22000]
    return "\n\n".join(dedupe_preserve_order(snippets))[:22000]


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = clean_text(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def rule_proposal_sheets(
    source_documents: list[dict[str, str]],
    notice_id: str,
    source_file: str,
    generated_at: str,
) -> dict[str, Any]:
    text = "\n\n".join(f"[{item['fileName']}]\n{item['documentText']}" for item in source_documents)
    notice_text = prioritized_document_text(source_documents, ["공고", "입찰공고", "공고서", "공고문"])
    rfp_text = prioritized_document_text(source_documents, ["제안요청", "제안 요청", "과업", "규격", "시방"])
    title_patterns = [
        r"입찰건명[:：]\s*(.+?)(?:\s+[나-하]\.\s|$)",
        r"공고명[:：]\s*(.+?)(?:\n|$)",
        r"사\s*업\s*명\s*[:：]?\s*(.+?)(?:\n(?:기\s*관\s*명|기관명|수요기관|발주기관|20\d{2}|담당|목\s*차)|$)",
        r"계약건명\s*[:：]?\s*(.+?)(?:\n|계약기간|$)",
    ]
    agency_patterns = [
        r"수요기관[:：]\s*(.+?)(?:\n|$)",
        r"발주기관[:：]\s*(.+?)(?:\n|$)",
        r"기\s*관\s*명\s*[:：]?\s*(.+?)(?:\n(?:20\d{2}|담당|부서명|목\s*차)|$)",
        r"주관기관\s*\(\s*발주기관\s*\)\s*[:：]?\s*(.+?)(?:\n|20\d{2}|$)",
    ]
    budget_patterns = [
        r"사업예산\s*[:：]?\s*(.+?)(?:\n(?:사업기간|계약방법|평가항목|[0-9]+\.\s)|$)",
        r"사업금액[:：]\s*(.+?)(?:\n|$)",
        r"소요예산\s*(.+?)(?:\n|긴급입찰|$)",
    ]
    title = find_value(notice_text, title_patterns) or find_value(text, title_patterns)
    agency = find_value(notice_text, agency_patterns) or find_value(text, agency_patterns)
    budget = find_value(notice_text, budget_patterns) or find_value(text, budget_patterns)
    deadline = find_datetime(
        notice_text,
        [
            "입찰서제출 마감일시",
            "제안서제출 마감일시",
            "제안서 제출 마감일시",
            "제출 마감일시",
            "마감일시",
            "제출기한",
        ],
    ) or find_datetime(text, ["입찰서제출 마감일시", "제안서제출 마감일시", "제출 마감일시", "마감일시", "제출기한"])
    method_patterns = [
        r"입찰방법[:：]\s*(.+?)(?:\s+[라-하]\.\s|$)",
        r"계약방법\s*[:：]?\s*(.+?)(?:\n(?:평가항목|[0-9]+\.\s)|$)",
    ]
    period_patterns = [
        r"사업기간\s*[:：]?\s*(.+?)(?:\n(?:\*|계약방법|평가항목|[0-9]+\.\s)|$)",
        r"납품기한[:：]\s*(.+?)(?:\n|$)",
        r"계약기간\s*(.+?)(?:\n|계약부서|$)",
    ]
    method = find_value(notice_text, method_patterns) or find_value(text, method_patterns)
    period = find_value(notice_text, period_patterns) or find_value(text, period_patterns)
    qualification = numbered_section(notice_text, "입찰참가자격", "낙찰자 결정방법") or section(
        notice_text,
        r"(?:입찰참가자격|입찰 참가 자격)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|낙찰자|제출 서류|제출서류|$)",
    )
    submit_section = numbered_section(notice_text, "입찰 참가 제출 서류", "입찰보증금") or section(
        notice_text,
        r"(?:제출 서류|제출서류|구비서류|입찰 참가 제출 서류)[-\s:：]*(.+?)(?:입찰보증금|입찰의 무효|$)",
    )
    score_section = collect_scoring_table_sections(rfp_text) or extract_score_section(rfp_text) or extract_score_section(text)
    detail_groups = build_detail_groups(
        text=f"{notice_text}\n\n{rfp_text}",
        title=title,
        agency=agency,
        budget=budget,
        period=period,
        deadline=deadline,
        method=method,
        score_section=score_section,
    )

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
            "detailGroups": detail_groups,
            "requirements": parse_requirements(text, qualification),
            "risks": parse_risks(text),
            "clarifications": parse_clarifications(text),
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
            "headers": ["No", "제출서류", "서식", "담당자", "주관기관(대표사)", "마감일", "비고"],
            "organizationHeaders": ["주관기관(대표사)"],
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


def prioritized_document_text(source_documents: list[dict[str, str]], preferred_name_tokens: list[str]) -> str:
    preferred = []
    rest = []
    for document in source_documents:
        file_name = document.get("fileName", "")
        doc_type = document.get("docType", "")
        chunk = f"[{file_name}]\n{document.get('documentText', '')}"
        if any(token in file_name or token in doc_type for token in preferred_name_tokens):
            preferred.append(chunk)
        else:
            rest.append(chunk)
    return "\n\n".join(preferred + rest)


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
            "code": clean_text(str(item.get("code", ""))),
            "requirement": clean_text(str(item.get("requirement", ""))),
            "name": clean_text(str(item.get("name", item.get("requirement", "")))),
            "detail": clean_text(str(item.get("detail", ""))),
            "type": clean_text(str(item.get("type", "확인"))),
            "category": clean_text(str(item.get("category", ""))),
            "source": clean_text(str(item.get("source", ""))),
        }
        for item in notice_info.get("requirements", [])
        if isinstance(item, dict)
    ] or fallback["noticeInfo"]["requirements"]
    for item in requirements:
        if not item["requirement"]:
            item["requirement"] = item["name"] or item["code"] or "요구사항 원문 확인"
        if not item["name"]:
            item["name"] = item["requirement"]
    requirements = merge_requirement_fallbacks(requirements, fallback["noticeInfo"]["requirements"])

    detail_groups = normalize_detail_groups(notice_info.get("detailGroups"), fallback["noticeInfo"].get("detailGroups", []))
    risks = normalize_key_value_list(notice_info.get("risks"), ["title", "detail", "severity"]) or fallback["noticeInfo"].get("risks", [])
    clarifications = normalize_key_value_list(notice_info.get("clarifications"), ["question", "reason"]) or fallback["noticeInfo"].get("clarifications", [])

    items = normalize_checklist(checklist.get("items", []), fallback["checklist"]["items"])
    organization_headers = normalize_organization_headers(checklist.get("organizationHeaders"), items, fallback["checklist"]["organizationHeaders"])
    score_items = normalize_scores(scoring.get("items", []), fallback["scoring"]["items"])
    fallback_score_items = fallback["scoring"]["items"]
    if fallback_score_items and len(fallback_score_items) >= len(score_items):
        score_items = fallback_score_items
    summary = notice_info.get("summary") if isinstance(notice_info.get("summary"), dict) else {}
    normalized = {
        **fallback,
        **result,
        "noticeInfo": {
            "details": normalized_details,
            "detailGroups": detail_groups,
            "requirements": requirements,
            "risks": risks,
            "clarifications": clarifications,
            "summary": {
                **fallback["noticeInfo"]["summary"],
                **{key: normalize_summary_value(key, clean_text(str(value))) for key, value in summary.items() if value is not None},
            },
        },
        "checklist": {
            **fallback["checklist"],
            **checklist,
            "organizationHeaders": organization_headers,
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
            organizations = [{"name": "주관기관(대표사)", "required": True, "checked": False}]
        normalized.append(
            {
                "no": int(item.get("no") or index),
                "document": document,
                "form": clean_text(str(item.get("form", ""))),
                "owner": clean_text(str(item.get("owner", ""))),
                "organizations": [
                    {
                        "name": normalize_organization_name(clean_text(str(org.get("name", "주관기관(대표사)")))) if isinstance(org, dict) else "주관기관(대표사)",
                        "required": bool(org.get("required", True)) if isinstance(org, dict) else True,
                        "checked": False,
                    }
                    for org in organizations
                ],
                "deadline": normalize_date_text(clean_text(str(item.get("deadline", "")))),
                "note": clean_text(str(item.get("note", ""))),
                "extra": clean_text(str(item.get("extra", ""))),
            }
        )
    return normalized or fallback_items


def normalize_organization_headers(headers: Any, items: list[dict[str, Any]], fallback_headers: list[str]) -> list[str]:
    normalized = []
    if isinstance(headers, list):
        normalized = [normalize_organization_name(clean_text(str(header))) for header in headers if clean_text(str(header))]
    for item in items:
        for org in item.get("organizations", []):
            name = clean_text(str(org.get("name", ""))) if isinstance(org, dict) else ""
            if name and name not in normalized:
                normalized.append(name)
    if not normalized:
        normalized = fallback_headers or ["주관기관(대표사)"]
    if not any("주관" in header for header in normalized):
        normalized.insert(0, "주관기관(대표사)")
    return normalized


def normalize_organization_name(name: str) -> str:
    if name in {"주관기관", "대표사", "주관사"}:
        return "주관기관(대표사)"
    return name or "주관기관(대표사)"


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


def normalize_detail_groups(groups: Any, fallback_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        return fallback_groups
    groups_by_category = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        category = clean_text(str(group.get("category", "")))
        items = group.get("items")
        if not category or not isinstance(items, list):
            continue
        groups_by_category[category] = [
            {
                "label": clean_text(str(item.get("label", ""))),
                "value": clean_text(str(item.get("value", ""))),
                "note": clean_text(str(item.get("note", ""))),
            }
            for item in items
            if isinstance(item, dict) and clean_text(str(item.get("label", "")))
        ]

    normalized = []
    for template in DETAIL_GROUPS:
        category = template["category"]
        items_by_label = {item["label"]: item for item in groups_by_category.get(category, [])}
        fallback_items = next((group.get("items", []) for group in fallback_groups if group.get("category") == category), [])
        fallback_by_label = {item.get("label"): item for item in fallback_items if isinstance(item, dict)}
        normalized.append(
            {
                "category": category,
                "items": [
                    items_by_label.get(label)
                    or fallback_by_label.get(label)
                    or {"label": label, "value": "", "note": ""}
                    for label in template["labels"]
                ],
            }
        )
    return normalized


def normalize_key_value_list(items: Any, keys: list[str]) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {key: clean_text(str(item.get(key, ""))) for key in keys}
        if any(row.values()):
            normalized.append(row)
    return normalized[:20]


def merge_requirement_fallbacks(requirements: list[dict[str, str]], fallback_requirements: list[dict[str, str]]) -> list[dict[str, str]]:
    if not fallback_requirements:
        return requirements
    by_code = {item.get("code", ""): item for item in requirements if item.get("code")}
    merged = list(requirements)
    for fallback_item in fallback_requirements:
        code = clean_text(str(fallback_item.get("code", "")))
        if not code or code in by_code:
            continue
        merged.append(
            {
                "code": code,
                "requirement": clean_text(str(fallback_item.get("requirement", ""))),
                "name": clean_text(str(fallback_item.get("name", fallback_item.get("requirement", "")))),
                "detail": clean_text(str(fallback_item.get("detail", ""))),
                "type": clean_text(str(fallback_item.get("type", "필수"))),
                "category": clean_text(str(fallback_item.get("category", ""))),
                "source": clean_text(str(fallback_item.get("source", "rule-fallback"))),
            }
        )
    return merged


def find_value(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            return clip(clean_bound_value(value), 500)
    return ""


def build_detail_groups(
    *,
    text: str,
    title: str,
    agency: str,
    budget: str,
    period: str,
    deadline: str,
    method: str,
    score_section: str,
) -> list[dict[str, Any]]:
    values = {
        "사업명": title,
        "발주처": agency,
        "예산": budget,
        "사업 기간": period,
        "과업 범위": find_scope(text),
        "계약/낙찰 방식": method,
        "협상/적격심사 여부": infer_evaluation_type(text, method),
        "기술:가격 배점비": find_tech_price_ratio(text),
        "평가 절차": clip(score_section, 700),
        "제안서 매수 제한": find_submission_limit(text),
        "규격": find_submission_format(text),
        "원본/사본/PDF/HWPX 등 형식": find_copy_file_format(text),
        "마감 일시": deadline,
        "제출 방법·제출처": find_submission_method(text),
        "질의응답·설명회 일정": find_qna_or_briefing(text),
        "컨소시엄 구성 의무·제한": infer_joint_contract(text),
        "주관사 지분 요건": find_lead_share_requirement(text),
        "의무 하도급 비율": find_subcontract_requirement(text),
    }
    return [
        {
            "category": group["category"],
            "items": [{"label": label, "value": values.get(label, ""), "note": ""} for label in group["labels"]],
        }
        for group in DETAIL_GROUPS
    ]


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
    value = re.sub(r"\s+,", ",", value)
    value = re.sub(r"(?<=\d)\s+(?=[,\d])", "", value)
    value = re.sub(r"\s*[□○◦▪]\s*$", "", value)
    value = re.sub(r"\s+", " ", value)
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


def find_scope(text: str) -> str:
    patterns = [
        r"4\.\s*사업\s*내용\s*(.+?)(?:\n\s*II\.|\n\s*III\.|\n\s*IV\.|$)",
        r"1\.\s*사업개요\s*(.+?)(?:\n\s*2\.\s*배경|2\.\s*배경|$)",
        r"(?:과업\s*범위|과업\s*내용|사업\s*내용|사업개요|추진\s*목적)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|평가|제출|입찰|$)",
        r"(?:사업\s*내용|사업내용)\s*(.+?)(?:\n\s*[IVX]+\.\s|\n\s*\d+\.\s|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.DOTALL):
            candidate = clean_text(match.group(1))
            if candidate and ("○" in candidate or "□" in candidate):
                return clip(candidate, 900)
    return ""


def infer_evaluation_type(text: str, method: str) -> str:
    haystack = f"{method} {text}"
    labels = []
    if "협상에 의한 계약" in haystack or "협상" in haystack:
        labels.append("협상에 의한 계약")
    if "적격심사" in haystack:
        labels.append("적격심사")
    if "종합평가" in haystack:
        labels.append("종합평가")
    return ", ".join(dict.fromkeys(labels))


def find_tech_price_ratio(text: str) -> str:
    patterns = [
        r"기술(?:능력)?평가\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?\s*\+\s*(?:입찰)?가격평가\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?",
        r"기술(?:능력)?평가\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*[:/대,\s]+(?:입찰)?가격평가\s*(\d+(?:\.\d+)?)\s*(?:점|%)",
        r"기술(?:능력)?평가\s*(\d+(?:\.\d+)?)\s*%\s*/\s*(?:입찰)?가격평가\s*(\d+(?:\.\d+)?)\s*%",
        r"기술\s*[:：]\s*가격\s*=\s*(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)}:{match.group(2)}"
    return ""


def find_submission_limit(text: str) -> str:
    return find_value(
        text,
        [
            r"(?:제안서|정성제안서|정량제안서).{0,40}(?:분량|매수|쪽수|페이지|page).{0,120}",
            r"(?:\d+\s*(?:쪽|페이지|page|매)\s*(?:이내|내외).{0,120})",
        ],
    )


def find_submission_format(text: str) -> str:
    return find_value(
        text,
        [
            r"(?:작성\s*규격|제안서\s*규격|용지|글자|폰트|여백|A4).{0,220}",
            r"(?:제안서\s*작성방법|작성\s*방법)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|제출|평가|$)",
        ],
    )


def find_copy_file_format(text: str) -> str:
    source = collect_submission_sections(text) or text
    return find_value(
        source,
        [
            r"(?:제안서|정량제안서|정성제안서|기술제안서|발표자료|USB|전자파일|파일).{0,100}(?:원본|사본|PDF|HWPX|HWP|USB|전자파일).{0,180}",
            r"(?:원본|사본|PDF|HWPX|HWP|USB|전자파일).{0,100}(?:제안서|정량제안서|정성제안서|기술제안서|발표자료|USB|전자파일|파일).{0,180}",
            r"(?:제출\s*부수|제출\s*형식)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|평가|입찰|$)",
        ],
    )


def find_submission_method(text: str) -> str:
    return find_value(
        text,
        [
            r"(?:제출방법|제출\s*방법|제출장소|제출처)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|질의|평가|입찰|$)",
            r"(?:나라장터|e-발주시스템|방문제출|우편제출|온라인제출).{0,220}",
        ],
    )


def find_qna_or_briefing(text: str) -> str:
    return find_value(
        text,
        [
            r"(?:질의응답|질의\s*및\s*답변|제안요청\s*설명회|사업설명회|현장설명회)[-\s:：]*(.+?)(?:\n\s*\d+\.\s|제출|평가|입찰|$)",
            r"(?:설명회|질의).{0,220}",
        ],
    )


def find_lead_share_requirement(text: str) -> str:
    return find_value(text, [r"(?:대표사|주관사|공동수급체\s*대표).{0,120}(?:지분|분담|출자).{0,120}"])


def find_subcontract_requirement(text: str) -> str:
    return find_value(text, [r"하도급.{0,80}(?:비율|의무\s*하도급|의무\s*비율).{0,120}"])


def parse_requirements(text: str, qualification_text: str = "") -> list[dict[str, str]]:
    coded = parse_coded_requirements(text)
    if coded:
        return coded

    chunks = re.split(r"\s+[가-하]\.\s+|\s+\d+\)\s+", trim_qualification(qualification_text))
    rows = []
    for chunk in chunks:
        chunk = clip(chunk, 500)
        if not chunk:
            continue
        rows.append(
            {
                "code": "",
                "requirement": chunk[:40],
                "name": chunk[:40],
                "detail": chunk,
                "type": "필수" if "하여야" in chunk or "필" in chunk else "확인",
                "category": "입찰 참가 자격",
                "source": "",
            }
        )
    return rows[:12] or [
        {
            "code": "",
            "requirement": "공고문 확인",
            "name": "공고문 확인",
            "detail": "입찰 참가 요건 원문 확인 필요",
            "type": "확인",
            "category": "입찰 참가 자격",
            "source": "",
        }
    ]


def parse_coded_requirements(text: str) -> list[dict[str, str]]:
    lines = [clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    rows = []
    seen = set()
    for index, line in enumerate(lines):
        match = REQUIREMENT_CODE_RE.search(line)
        if not match:
            continue
        code = match.group(1)
        if code in seen:
            continue
        seen.add(code)
        before_context = [
            item
            for item in lines[max(0, index - 8):index]
            if is_requirement_context_line(item)
        ]
        after_context = []
        tail = clean_text(line[match.end():].strip(" \t|:：-"))
        if tail:
            after_context.append(tail)
        for next_index in range(index + 1, min(len(lines), index + 8)):
            next_line = lines[next_index]
            if REQUIREMENT_CODE_RE.search(next_line):
                break
            if after_context and is_requirement_section_boundary(next_line):
                break
            if starts_next_requirement_row(lines, next_index):
                break
            if is_requirement_context_line(next_line):
                after_context.append(next_line)
            if sum(len(item) for item in after_context) > 900:
                break
        row_context = before_context + [clean_text(REQUIREMENT_CODE_RE.sub(" ", line))] + after_context
        name = extract_requirement_name(row_context, code=code, code_index=len(before_context)) or code
        detail = extract_requirement_detail(after_context or row_context, name)
        prefix = code[:3]
        rows.append(
            {
                "code": code,
                "requirement": name,
                "name": name,
                "detail": detail or name,
                "type": "필수",
                "category": REQUIREMENT_CATEGORY_LABELS.get(prefix, prefix),
                "source": "",
            }
        )
    return rows


def extract_requirement_name(context: list[str], code: str = "", code_index: int = 0) -> str:
    if not context:
        return ""
    candidates: list[tuple[int, str]] = []
    for offset, line in enumerate(context):
        for cell in split_requirement_cells(line):
            if not is_requirement_name_candidate(cell, code):
                continue
            distance = abs(offset - code_index)
            score = distance
            if offset < code_index:
                score -= 1
            if any(keyword in cell for keyword in ("기능", "관리", "조회", "연계", "보안", "성능", "품질", "데이터", "화면", "지원", "운영")):
                score -= 1
            candidates.append((score, cell))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (item[0], len(item[1])))
    return clip(candidates[0][1], 140)


def extract_requirement_detail(context: list[str], name: str) -> str:
    cleaned = []
    for line in context:
        if not is_requirement_context_line(line):
            continue
        if clean_requirement_cell(line) == name:
            continue
        cleaned.append(line)
    detail = clean_text(" ".join(cleaned))
    if name and detail.startswith(name):
        detail = clean_text(detail[len(name):])
    return clip(detail or name, 900)


def split_requirement_cells(line: str) -> list[str]:
    cells = re.split(r"\s{2,}|\t+|[|│┃]\s*|ㆍ|·", line)
    return [clean_requirement_cell(cell) for cell in cells if clean_requirement_cell(cell)]


def clean_requirement_cell(value: str) -> str:
    value = clean_text(value)
    value = REQUIREMENT_CODE_RE.sub(" ", value)
    value = re.sub(r"^\d+[.)]?\s*", "", value)
    value = re.sub(r"^(?:요구사항명|요구사항\s*명칭|명칭|항목|세부내용|내용)\s*[:：]?\s*", "", value)
    return clean_text(value.strip(" -–—:：[]()"))


def is_requirement_context_line(line: str) -> bool:
    value = clean_requirement_cell(line)
    if not value:
        return False
    if value in REQUIREMENT_HEADER_WORDS:
        return False
    if len(value) > 350 and re.fullmatch(r"[A-Za-z0-9+/=]{120,}", value):
        return False
    return True


def is_requirement_name_candidate(value: str, code: str) -> bool:
    value = clean_requirement_cell(value)
    if not value or value == code:
        return False
    if value in REQUIREMENT_HEADER_WORDS:
        return False
    if REQUIREMENT_CODE_RE.fullmatch(value):
        return False
    if len(value) > 120:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return False
    if value.endswith(("요구사항", "고유번호")) and len(value) <= 12:
        return False
    return True


def starts_next_requirement_row(lines: list[str], index: int) -> bool:
    value = clean_requirement_cell(lines[index])
    if not value:
        return False
    lookahead = lines[index + 1:index + 3]
    if not any(REQUIREMENT_CODE_RE.search(line) for line in lookahead):
        return False
    if len(value) > 90:
        return False
    if re.search(r"(한다|해야|하여야|가능|제공|구축|관리|지원|수행|포함|작성|제출|검토|확인)", value):
        return False
    return True


def is_requirement_section_boundary(line: str) -> bool:
    folded = fold_requirement_text(line)
    if not folded:
        return False
    return any(folded == fold_requirement_text(marker) or folded.startswith(fold_requirement_text(marker)) for marker in REQUIREMENT_TABLE_END_MARKERS)


def fold_requirement_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def loose_text_pattern(text: str) -> str:
    return r"\s*".join(re.escape(char) for char in text if not char.isspace())


def parse_risks(text: str) -> list[dict[str, str]]:
    risk_keywords = [
        ("실적·인증 요건", r"(?:최근\s*\d+년|실적|인증|직접생산|중소기업|소프트웨어사업자).{0,180}"),
        ("일정 리스크", r"(?:긴급|제안서\s*제출\s*마감|착수일|완료일|납품기한).{0,160}"),
        ("공동수급·하도급", r"(?:공동수급|공동계약|하도급|분담이행|공동이행).{0,180}"),
        ("감점·실격 조건", r"(?:감점|실격|무효|탈락|배제).{0,180}"),
    ]
    risks = []
    for title, pattern in risk_keywords:
        match = re.search(pattern, text)
        if match:
            risks.append({"title": title, "detail": clip(match.group(0), 260), "severity": "확인"})
    return risks[:8]


def parse_clarifications(text: str) -> list[dict[str, str]]:
    questions = []
    if not find_tech_price_ratio(text):
        questions.append({"question": "기술평가와 가격평가의 정확한 배점비를 확인해야 합니다.", "reason": "공고문상 자동 추출 결과 배점비가 명확하지 않습니다."})
    if not find_submission_limit(text):
        questions.append({"question": "제안서 매수 제한과 별도 제출본별 제한을 확인해야 합니다.", "reason": "제안서 분량 제한이 공고문상 불명확합니다."})
    if "공동수급" in text and not find_lead_share_requirement(text):
        questions.append({"question": "공동수급 시 대표사 지분 또는 참여비율 제한이 있는지 확인해야 합니다.", "reason": "공동수급 언급은 있으나 지분 요건은 자동 추출되지 않았습니다."})
    return questions


def parse_submission_documents(text: str, deadline: str) -> list[dict[str, Any]]:
    text = clean_text(text)
    candidates = [
        ("입찰참가신청서", "별지 1", ""),
        ("입찰참가 등록증", "", "나라장터 경쟁입찰 참가자격 등록 여부 확인"),
        ("조달청 경쟁입찰 참가 등록증", "", "조달청 나라장터 출력. 컴퓨터관련서비스업(1468) 또는 디지털콘텐츠개발서비스업(1469) 확인"),
        ("4대보험완납증명서", "", ""),
        ("이행(입찰)보증보험증권", "", "입찰금액의 100분의 5 이상"),
        ("입찰보증보험증권", "", "입찰보증금 또는 보증보험 관련 제출 여부 확인"),
        ("보증보험증권", "", "입찰보증금 또는 계약이행 관련 제출 여부 확인"),
        ("기업신용평가 등급확인서", "", ""),
        ("신용평가등급확인서", "", ""),
        ("신용평가서", "", ""),
        ("인감증명서", "", "법인인 경우 법인인감증명서 및 법인등기부등본 각 1부"),
        ("법인인감증명서", "", ""),
        ("법인등기부등본", "", "개인사업자는 사업자등록증 등 대체 가능 여부 확인"),
        ("법인 등기사항증명서", "", "개인사업자는 사업자등록증 등 대체 가능 여부 확인"),
        ("사용인감계", "", "인감도장 입찰참가 신청 시 지참"),
        ("사업자등록증 사본", "", ""),
        ("사업자등록증", "", ""),
        ("국세・지방세 완납증명서", "", "각 1부"),
        ("국세 완납증명서", "", ""),
        ("지방세 완납증명서", "", ""),
        ("확약서", "별지 2", ""),
        ("청렴계약서", "별지 3", ""),
        ("청렴계약 이행서약서", "", ""),
        ("보안서약서", "별지 4", ""),
        ("개인정보보호 서약서", "", ""),
        ("최근 결산기준 재무상태 및 재무제표", "", ""),
        ("재무제표", "", "최근 결산 기준 등 기간 확인"),
        ("재무상태표", "", ""),
        ("손익계산서", "", ""),
        ("수행실적증명서", "", "유사분야 수행실적 증빙"),
        ("실적증명서", "", "수행실적 증빙"),
        ("용역이행 실적증명서", "", ""),
        ("인력투입계획서", "", ""),
        ("투입인력 이력사항", "", ""),
        ("참여인력 이력사항", "", ""),
        ("기술자격증", "", "인력 자격 증빙"),
        ("자격증 사본", "", "인력 자격 증빙"),
        ("소프트웨어사업자 신고확인서", "", ""),
        ("직접생산확인증명서", "", ""),
        ("중소기업확인서", "", ""),
        ("하도급 계획서", "", "하도급 예정 시 제출 여부 확인"),
        ("하도급 적정성 판단 자기평가표", "", ""),
        ("대표자 위임장, 재직증명서, 신분증", "별지 5", "대리인의 경우에 한함"),
        ("위임장", "", "대리인 제출 시 필요"),
        ("재직증명서", "", "대리인 또는 투입인력 증빙"),
        ("신분증", "", "대리인 제출 시 필요"),
        ("개인정보 수집 이용 동의서", "별지 6", ""),
        ("정량제안서", "", "2부. 제안요청서 P.16~22 참고, 정량평가 자가진단서 첨부"),
        ("정량평가 자가진단서", "", ""),
        ("정성제안서", "", "10부. 원본 1부, 사본 9부는 제안사명 및 로고 미표기"),
        ("기술제안서", "", "원본/사본/PDF/HWPX 등 제출 형식 확인"),
        ("제안서", "", "정성/정량 구분, 원본/사본/PDF/HWPX 등 제출 형식 확인"),
        ("제안요약서", "", ""),
        ("발표자료", "", "제안 발표용 자료 제출 여부 확인"),
        ("제안서 발표자료", "", ""),
        ("제안서(발표용 PPT)가 포함된 USB", "", "각 1개. 원본 1개, 사본 1개"),
        ("USB", "", "전자파일 제출 매체, 원본/사본 구분 확인"),
    ]
    items = []
    seen_documents = set()
    for name, form, default_note in candidates:
        if name in seen_documents:
            continue
        if name in text and not is_excluded_submission_document_context(text, name):
            seen_documents.add(name)
            note = extract_doc_note(text, name, default_note)
            items.append(
                {
                    "no": len(items) + 1,
                    "document": name,
                    "form": form,
                    "owner": "GO" if is_external_document(name) else "",
                    "organizations": [{"name": "주관기관(대표사)", "required": True, "checked": False}],
                    "deadline": normalize_date_text(deadline),
                    "note": note,
                    "extra": "",
                }
            )
    return filter_submission_documents(items)


def filter_submission_documents(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {item.get("document", "") for item in items}
    suppressed = set()
    if {"정성제안서", "기술제안서", "정량제안서"} & names:
        suppressed.add("제안서")
    if "수행실적증명서" in names:
        suppressed.add("실적증명서")
    if "입찰보증보험증권" in names:
        suppressed.add("보증보험증권")
    filtered = [item for item in items if item.get("document") not in suppressed]
    for index, item in enumerate(filtered, 1):
        item["no"] = index
    return filtered


def is_excluded_submission_document_context(text: str, name: str) -> bool:
    position = text.find(name)
    if position < 0:
        return False
    context = text[max(0, position - 80):position + len(name) + 120]
    if any(token in context for token in ["대면평가 시", "대면평가일 경우", "계약 체결 후", "계약체결 후", "요청 시", "필요 시"]):
        return True
    if "별지서식" in context and not any(token in context for token in ["제출", "첨부", "포함"]):
        return True
    return False


def parse_score_items(text: str) -> list[dict[str, Any]]:
    text = clean_text(text)
    compact_items = parse_compact_score_table(text)
    if compact_items:
        return compact_items

    generic_items = parse_generic_score_table(text)
    if generic_items:
        return generic_items

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


def parse_compact_score_table(text: str) -> list[dict[str, Any]]:
    section = collect_scoring_table_sections(text) or text
    folded_section = fold_requirement_text(section)
    compact_header = "평가구분평가항목세부평가항목평가기준배점"
    if compact_header not in folded_section and "별표3" not in folded_section:
        return []

    specs = [
        ("기술능력평가", "정량평가", "경영 상태"),
        ("기술능력평가", "정량평가", "납품 및 설치 실적"),
        ("기술능력평가", "전략 및 방법론", "사업이해도"),
        ("기술능력평가", "전략 및 방법론", "추진전략"),
        ("기술능력평가", "전략 및 방법론", "적용기술"),
        ("기술능력평가", "전략 및 방법론", "구축방법론"),
        ("기술능력평가", "기술 및 기능", "시스템 장비 구성 요구사항"),
        ("기술능력평가", "기술 및 기능", "기능 요구사항"),
        ("기술능력평가", "기술 및 기능", "보안 요구사항"),
        ("기술능력평가", "기술 및 기능", "제약 사항"),
        ("기술능력평가", "성능 및 품질", "테스트 요구사항"),
        ("기술능력평가", "성능 및 품질", "품질요구사항"),
        ("기술능력평가", "성능 및 품질", "구축 방안 및 절차"),
        ("기술능력평가", "프로젝트 관리", "일정계획"),
        ("기술능력평가", "프로젝트 관리", "관리 방법론"),
        ("기술능력평가", "프로젝트 지원", "하자보수 계획"),
        ("기술능력평가", "프로젝트 지원", "교육훈련 및 기술지원"),
        ("기술능력평가", "프로젝트 지원", "비상대책"),
    ]
    label_patterns = [(major, middle, minor, loose_text_pattern(minor)) for major, middle, minor in specs]
    matches = []
    for major, middle, minor, pattern in label_patterns:
        match = re.search(pattern, section)
        if match:
            matches.append((match.start(), match.end(), major, middle, minor))
    if len(matches) < 6:
        return []
    matches.sort(key=lambda item: item[0])

    boundary_patterns = [
        loose_text_pattern(label)
        for label in [
            "정성평가",
            "전략 및 방법론",
            "기술 및기능",
            "기술 및 기능",
            "성능및품질",
            "성능 및 품질",
            "프로젝트 관리",
            "프로젝트 지원",
            "[별표 4]",
        ]
    ]

    items = []
    for index, (start, end, major, middle, minor) in enumerate(matches):
        next_start = matches[index + 1][0] if index + 1 < len(matches) else len(section)
        total_boundary = re.search(r"계\s*100(?:\.0)?", section[end:])
        if total_boundary:
            absolute = end + total_boundary.start()
            if end < absolute < next_start:
                next_start = absolute
        for pattern in boundary_patterns:
            boundary = re.search(pattern, section[end:])
            if boundary:
                absolute = end + boundary.start()
                if end < absolute < next_start:
                    next_start = absolute
        raw_detail = section[end:next_start]
        score_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-\s*\d+\s*-\s*)?(?:평가구분평가항목세부평가항목평가기준배점)?\s*$",
            fold_requirement_text(raw_detail),
        )
        if not score_match:
            continue
        score = float(score_match.group(1))
        if not 0 < score <= 100:
            continue
        raw_score = re.search(r"(\d+(?:\.\d+)?)", raw_detail)
        detail = clean_text(raw_detail[: raw_score.start()]) if raw_score else clean_text(raw_detail)
        if detail.startswith(minor):
            detail = clean_text(detail[len(minor):])
        grade = grade_for_score(score)
        items.append(
            {
                "major": major,
                "middle": middle,
                "minor": minor,
                "score": score,
                "weight": score,
                "grade": grade,
                "strategy": strategy_by_grade(grade),
                "detail": clip(detail, 420),
            }
        )

    items = dedupe_score_items(items)
    total = sum(float(item.get("score") or 0) for item in items)
    return items if len(items) >= 6 and 60 <= total <= 110 else []


def parse_generic_score_table(text: str) -> list[dict[str, Any]]:
    section = collect_scoring_table_sections(text)
    if not section:
        section = extract_score_section(text)
    if not section:
        return []

    lines = [clean_text(line) for line in section.splitlines()]
    lines = [line for line in lines if line and not is_score_noise_line(line)]
    items: list[dict[str, Any]] = []
    current_major = ""
    current_major_score = 0.0
    index = 0
    while index < len(lines):
        major = read_score_major(lines, index)
        if major:
            current_major, current_major_score, next_index = major
            index = next_index
            continue

        if is_plain_score(lines[index]) or is_score_section_boundary_line(lines[index]):
            index += 1
            continue

        label_parts = []
        cursor = index
        while cursor < len(lines):
            candidate = lines[cursor]
            if is_plain_score(candidate) or read_score_major(lines, cursor):
                break
            if is_score_detail_sentence(candidate) and label_parts:
                break
            if not is_score_item_label(candidate) and label_parts:
                break
            if is_score_item_label(candidate) or not label_parts:
                label_parts.append(clean_score_label(candidate))
                cursor += 1
                continue
            break

        minor = clean_score_label(" ".join(label_parts))
        if not is_score_item_label(minor):
            index += 1
            continue

        detail_lines = []
        score = 0.0
        while cursor < len(lines):
            candidate = lines[cursor]
            if read_score_major(lines, cursor) and detail_lines:
                break
            if is_plain_score(candidate):
                score = float(candidate)
                cursor += 1
                break
            detail_lines.append(candidate)
            cursor += 1

        if score and minor not in {"계", "합계", "총계", "배점", "한도"}:
            technical_group = current_major or infer_score_major(section, index)
            major = "기술능력평가" if technical_group != "가격평가" else "가격평가"
            middle = technical_group if major == "기술능력평가" else ""
            grade = grade_for_score(score)
            detail = clean_text(" ".join(detail_lines))
            items.append(
                {
                    "major": major or "평가항목",
                    "middle": middle,
                    "minor": minor,
                    "score": score,
                    "weight": score,
                    "grade": grade,
                    "strategy": strategy_by_grade(grade),
                    "detail": clip(detail, 420),
                }
            )
        index = max(cursor, index + 1)

    items = dedupe_score_items(items)
    total = sum(float(item.get("score") or 0) for item in items)
    if items and 60 <= total <= 110:
        if total < 95 and re.search(r"(?:입찰)?가격평가\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?", text):
            price_score = float(re.search(r"(?:입찰)?가격평가\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:점|%)\s*\)?", text).group(1))
            if not any("가격" in item["major"] or "가격" in item["minor"] for item in items):
                grade = grade_for_score(price_score)
                items.append(
                    {
                        "major": "가격평가",
                        "middle": "",
                        "minor": "입찰가격평가",
                        "score": price_score,
                        "weight": price_score,
                        "grade": grade,
                        "strategy": strategy_by_grade(grade),
                        "detail": "입찰가격 평가점수",
                    }
                )
        return items[:60]
    return []


def read_score_major(lines: list[str], index: int) -> tuple[str, float, int] | None:
    line = lines[index]
    inline_match = re.match(r"^(.{2,40}?)\s*\(\s*(\d+(?:\.\d+)?)\s*\)\s*$", line)
    if inline_match and not is_score_detail_sentence(inline_match.group(1)):
        return clean_score_label(inline_match.group(1)), float(inline_match.group(2)), index + 1

    label_parts = []
    cursor = index
    while cursor < min(len(lines), index + 5):
        candidate = lines[cursor]
        paren_match = re.fullmatch(r"\(\s*(\d+(?:\.\d+)?)\s*\)", candidate)
        if paren_match and label_parts:
            label = clean_score_label(" ".join(label_parts))
            if is_score_major_label(label):
                return label, float(paren_match.group(1)), cursor + 1
            return None
        if is_plain_score(candidate) or is_score_detail_sentence(candidate):
            return None
        if not is_score_major_part(candidate):
            return None
        label_parts.append(clean_score_label(candidate))
        cursor += 1
    return None


def is_score_major_label(label: str) -> bool:
    return any(token in label for token in ["정량평가", "정성평가", "전략", "방법론", "사업수행", "수행기반", "프로젝트", "관리", "지원", "가격평가"])


def is_score_major_part(line: str) -> bool:
    label = clean_score_label(line)
    if not label or len(label) > 18:
        return False
    if is_plain_score(label) or re.fullmatch(r"\(\s*\d+(?:\.\d+)?\s*\)", label):
        return False
    if is_score_detail_sentence(label):
        return False
    if is_score_item_label(label):
        return True
    return bool(re.fullmatch(r"[가-힣A-Za-z·ㆍ/ ]{1,18}", label))


def is_score_noise_line(line: str) -> bool:
    normalized = clean_text(line)
    if normalized in {"평가", "항목", "새부평가항목", "세부평가항목", "평가기준", "배점", "한도", "비고"}:
        return True
    folded = fold_requirement_text(normalized)
    if any(folded == fold_requirement_text(marker) for marker in SCORING_TABLE_MARKERS):
        return True
    if re.fullmatch(r"[A-Z]\b|제안기업|원점수 합계|원점수 합계 순위|차등점수제 적용", normalized):
        return True
    return False


def is_score_section_boundary_line(line: str) -> bool:
    return any(marker in line for marker in ["평가 세부기준", "입찰시 유의사항", "입찰 시 유의사항", "계약사항"])


def is_plain_score(line: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", line.strip())) and 0 < float(line) <= 100


def is_score_item_label(line: str) -> bool:
    label = clean_score_label(line)
    if not label or len(label) > 45:
        return False
    if re.fullmatch(r"\(\s*\d+(?:\.\d+)?\s*\)", label):
        return False
    if is_plain_score(label):
        return False
    if any(token in label for token in ["평가", "관리", "전략", "실적", "상태", "요구사항", "지원", "훈련", "인계", "하자", "구축", "성능", "안정화", "정책", "조직", "안전", "방법론", "체계", "이해도", "인수", "이슈", "재난", "제약"]):
        return True
    return False


def is_score_detail_sentence(line: str) -> bool:
    return len(line) > 26 or any(token in line for token in ["평가한다", "제시", "구체적", "적절"])


def clean_score_label(line: str) -> str:
    line = clean_text(line)
    line = re.sub(r"^\d+[.)]?\s*", "", line)
    line = re.sub(r"\b프로\s+젝트\b", "프로젝트", line)
    return line.strip(" -–—:：[]")


def infer_score_major(section: str, index: int) -> str:
    return "기술능력평가" if "기술" in section else "평가항목"


def dedupe_score_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for item in items:
        key = (item.get("major", ""), item.get("minor", ""), float(item.get("score") or 0))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


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
