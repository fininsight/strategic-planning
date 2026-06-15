from __future__ import annotations

import json
import os
import re

import requests

from .config import ANALYSIS_VERSION
from .text_extractor import clean_text


def clip(text: str, limit: int = 260) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def section(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.DOTALL)
    return clean_text(match.group(1)) if match else ""


def find(pattern: str, text: str, default: str = "공고서 확인") -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return clean_text(match.group(1)) if match else default


def document_kind(file_name: str) -> str:
    name = file_name.lower()
    if "제안요청" in name or "제안 요청" in name or "rfp" in name:
        return "제안요청서"
    if "과업" in name:
        return "과업지시서"
    if "공고" in name:
        return "입찰공고문"
    if "규격" in name or "시방" in name:
        return "규격서"
    return "첨부서류"


def api_key() -> str:
    return os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def chat_json(messages: list[dict], timeout: int = 45) -> dict:
    key = api_key()
    if not key:
        return {}

    response = requests.post(
        os.getenv("LLM_BASE_URL", "https://api.openai.com/v1/chat/completions"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


def rule_document_analysis(text: str, file_name: str) -> dict:
    doc_type = document_kind(file_name)
    qualification = section(r"입찰참가자격[-\s:：]+(.+?)(?:낙찰자|제출서류|입찰서|$)", text)
    scope = section(r"(?:입찰에 부치는 사항|과업 내용|과업내용|사업 내용|사업내용)[-\s:：]+(.+?)(?:입찰|계약|제출|평가|$)", text)
    score = section(r"(?:평가항목|배점|평가 기준|평가기준)[-\s:：]+(.+?)(?:협상|제출|계약|$)", text)
    return {
        "docType": doc_type,
        "summary": clip(scope or text[:500] or f"{doc_type} 파일입니다. 텍스트 추출 가능 여부를 확인한 뒤 세부 내용을 검토해야 합니다.", 360),
        "checklist": [
            clip(qualification or "입찰 참가 자격 및 제한 조건 확인"),
            "제출 서류, 제출 방식, 마감 시간 확인",
            "원문 PDF와 나라장터 공고 상세 정보 대조",
        ],
        "scoreTable": [{"item": "배점표/평가기준", "detail": clip(score or "문서 내 평가항목 또는 배점표 확인 필요")}],
        "analysisSource": "rule",
    }


def llm_document_analysis(text: str, file_name: str) -> dict:
    fallback = rule_document_analysis(text, file_name)
    if not api_key():
        return fallback

    prompt = {
        "fileName": file_name,
        "documentKindHint": fallback["docType"],
        "documentExcerpt": text[:7000] if text else "텍스트 추출 전 또는 추출 불가 문서입니다. 파일명과 문서 유형 힌트만 참고하세요.",
    }
    messages = [
        {
            "role": "system",
            "content": "너는 공공입찰 서류를 검토하는 한국어 분석가다. 문서에 근거한 내용만 요약하고, 사람이 검증할 체크리스트를 짧게 정리한다.",
        },
        {
            "role": "user",
            "content": (
                "아래 PDF 문서를 분석해서 JSON만 반환해줘. 필드는 docType, summary, checklist, scoreTable 네 개야. "
                "docType은 입찰공고문/제안요청서/과업지시서/규격서/첨부서류 중 하나로 분류해줘. "
                "summary는 문서 핵심을 한국어 2문장 이내로 써줘. checklist는 사람이 검증해야 할 항목 3~5개 문자열 배열로 써줘. "
                "scoreTable은 배점표나 평가기준이 있으면 {item, detail} 배열로 정리하고, 없으면 빈 배열로 둬.\n\n"
                + json.dumps(prompt, ensure_ascii=False)
            ),
        },
    ]

    try:
        result = chat_json(messages)
        checklist = result.get("checklist") if isinstance(result.get("checklist"), list) else fallback["checklist"]
        score_table = result.get("scoreTable") if isinstance(result.get("scoreTable"), list) else fallback["scoreTable"]
        return {
            "docType": clip(str(result.get("docType") or fallback["docType"]), 30),
            "summary": clip(str(result.get("summary") or fallback["summary"]), 420),
            "checklist": [clip(str(item), 180) for item in checklist[:5] if str(item).strip()],
            "scoreTable": [
                {"item": clip(str(item.get("item", "평가기준")), 80), "detail": clip(str(item.get("detail", "")), 220)}
                for item in score_table[:6]
                if isinstance(item, dict)
            ],
            "analysisSource": "llm",
        }
    except Exception as exc:
        fallback["analysisError"] = str(exc)
        return fallback


def summarize_notice(text: str) -> dict:
    title = find(r"입찰건명[:：]\s*(.+?)(?:\s+[나-하]\.\s|$)", text, "공고서 제목 확인")
    budget = find(r"사업예산[:：]\s*(.+?)(?:\s+[바-하]\.\s|$)", text)
    deadline = find(r"(?:입찰서제출|제안서.*제출).*마감일시[:：]\s*(.+?)(?:\s+[마-하]\.\s|$)", text)
    method = find(r"입찰방법[:：]\s*(.+?)(?:\s+[라-하]\.\s|$)", text)
    qualification = section(r"3\.\s*입찰참가자격[-\s]+(.+?)4\.\s*낙찰자", text)
    scope = section(r"1\.\s*입찰에 부치는 사항[-\s]+(.+?)2\.\s*입찰", text)

    summary = {
        "title": title,
        "budget": budget,
        "deadline": deadline,
        "method": method,
        "requirements": [
            {"label": "입찰 자격", "text": clip(qualification or "공고서의 입찰참가자격 항목 확인 필요")},
            {"label": "과업 범위", "text": clip(scope or "제안요청서 및 과업지시서 세부 확인 필요")},
        ],
        "strength": "PDF 변환본에서 공고문 텍스트를 직접 추출했습니다. 자격, 일정, 예산 항목을 우선 검토할 수 있습니다.",
        "risk": "원본 HWP와 PDF 변환본 내용이 다를 경우 원본이 우선될 수 있으므로 최종 제출 전 원본 공고서를 함께 확인해야 합니다.",
        "opportunity": "공고서와 제안요청서의 평가항목을 기준으로 당사 강점과 수행 경험을 연결해 제안 전략을 정리할 필요가 있습니다.",
        "timeline": [
            {"label": "입찰 서류 제출 마감", "date": deadline},
            {"label": "공고 상세 일정", "date": "공고서 원문 기준 확인"},
        ],
        "analysisVersion": ANALYSIS_VERSION,
    }
    return llm_notice_insights(text, summary)


def llm_notice_insights(text: str, summary: dict) -> dict:
    if not api_key():
        summary["insightSource"] = "rule"
        return summary

    prompt = {
        "title": summary.get("title"),
        "budget": summary.get("budget"),
        "deadline": summary.get("deadline"),
        "method": summary.get("method"),
        "requirements": summary.get("requirements"),
        "documentExcerpt": text[:7000],
    }
    messages = [
        {
            "role": "system",
            "content": "너는 공공입찰 제안 검토를 돕는 한국어 분석가다. 공고문 내용을 바탕으로 실무자가 바로 볼 수 있는 간략한 인사이트만 작성한다. 과장하지 말고 문서에 근거한 내용으로만 답한다.",
        },
        {
            "role": "user",
            "content": (
                "아래 입찰 공고를 분석해서 JSON만 반환해줘. 필드는 qualification, scope, strength, risk, opportunity 다섯 개야. "
                "qualification은 입찰 참가 자격을, scope는 과업 범위를 요약해줘. 각 값은 한국어 1~2문장으로 짧게 쓰고, 문서에 없는 내용은 추측하지 마.\n\n"
                + json.dumps(prompt, ensure_ascii=False)
            ),
        },
    ]

    try:
        insight = chat_json(messages)
        for key in ("strength", "risk", "opportunity"):
            value = clip(str(insight.get(key, "")), 220)
            if value:
                summary[key] = value
        qualification = clip(str(insight.get("qualification", "")), 300)
        scope = clip(str(insight.get("scope", "")), 300)
        if qualification or scope:
            summary["requirements"] = [
                {"label": "입찰 자격", "text": qualification or summary["requirements"][0]["text"]},
                {"label": "과업 범위", "text": scope or summary["requirements"][1]["text"]},
            ]
        summary["insightSource"] = "llm"
    except Exception as exc:
        summary["insightSource"] = "rule"
        summary["insightError"] = str(exc)
    return summary

