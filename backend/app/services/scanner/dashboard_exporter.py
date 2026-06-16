"""
dashboard_exporter.py
웹 대시보드가 읽을 공고 JSON 생성 모듈
"""

import json
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    from filters import CODE_NAMES, parse_date
else:
    from .filters import CODE_NAMES, parse_date


def _to_iso(raw: str) -> str:
    dt = parse_date(raw)
    return dt.isoformat() if dt else ""


def _to_number(raw: str) -> int:
    try:
        return int(float(str(raw).replace(",", "").replace(" ", "") or "0"))
    except (TypeError, ValueError):
        return 0


def _task_label(bid: dict) -> str:
    kind = bid.get("ntceKindNm", "")
    if "물품" in kind:
        return "물품"
    return "용역"


def _category_label(bid: dict) -> str:
    text = f"{bid.get('bidMthdNm', '')} {bid.get('bidNtceNm', '')}"
    return "긴급" if "긴급" in text else "일반"


def _industry_label(codes: list[str]) -> str:
    if not codes:
        return "미분류"
    if "9999" in codes and len(codes) == 1:
        return "기타자유업종"
    return " / ".join(CODE_NAMES.get(code, code) for code in codes)


def _region_label(bid: dict) -> str:
    text = f"{bid.get('ntceInsttNm', '')} {bid.get('dmndInsttNm', '')} {bid.get('bidNtceNm', '')}"
    regions = (
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    )
    for region in regions:
        if region in text:
            return region
    return "전국"


def _deep_link(bid: dict) -> str:
    bid_no = bid.get("bidNtceNo", "")
    bid_ord = bid.get("bidNtceOrd", "000") or "000"
    return (
        "https://www.g2b.go.kr/link/PNPE027_01/single/"
        f"?bidPbancNo={bid_no}&bidPbancOrd={bid_ord}"
    )


def _notice_from_bid(keyword: str, bid: dict) -> dict:
    matched_codes = bid.get("_matched_codes", [])
    return {
        "keyword": keyword,
        "task": _task_label(bid),
        "number": bid.get("bidNtceFullNo", bid.get("bidNtceNo", "")),
        "bidNtceNo": bid.get("bidNtceNo", ""),
        "bidNtceOrd": bid.get("bidNtceOrd", ""),
        "category": _category_label(bid),
        "title": bid.get("bidNtceNm", ""),
        "agency": bid.get("ntceInsttNm", ""),
        "demandAgency": bid.get("dmndInsttNm", ""),
        "region": _region_label(bid),
        "closeAt": _to_iso(bid.get("bidClseDt", "")),
        "postedAt": _to_iso(bid.get("bidNtceDt", "")),
        "method": bid.get("bidMthdNm", ""),
        "industry": _industry_label(matched_codes),
        "matchedCodes": matched_codes,
        "qualificationSource": bid.get("_license_source_label", ""),
        "budget": _to_number(bid.get("presmptPrce", bid.get("asignBdgtAmt", "0"))),
        "score": bid.get("_score", 0),
        "grade": bid.get("_grade", ""),
        "reasons": bid.get("_reasons", []),
        "deepLink": _deep_link(bid),
    }


def build_dashboard_payload(keyword_results: dict[str, dict],
                            generated_at: datetime) -> dict:
    notices_by_no: dict[str, dict] = {}

    for keyword, result in keyword_results.items():
        for bid in result.get("qualified", []):
            notice = _notice_from_bid(keyword, bid)
            key = notice["bidNtceNo"] or notice["number"]
            if key not in notices_by_no:
                notice["keywords"] = [keyword]
                notices_by_no[key] = notice
            elif keyword not in notices_by_no[key]["keywords"]:
                notices_by_no[key]["keywords"].append(keyword)

    notices = sorted(
        notices_by_no.values(),
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    return {
        "generatedAt": generated_at.isoformat(),
        "summary": {
            "qualified": len(notices),
            "disqualified": sum(
                len(result.get("disqualified", []))
                for result in keyword_results.values()
            ),
            "keywords": list(keyword_results.keys()),
        },
        "notices": notices,
    }


def write_dashboard_json(keyword_results: dict[str, dict],
                         output_paths: list[Path],
                         generated_at: datetime) -> list[str]:
    payload = build_dashboard_payload(keyword_results, generated_at)
    written = []

    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(str(path))

    return written
