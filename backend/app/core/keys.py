import hashlib


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
