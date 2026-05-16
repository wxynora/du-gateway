def message_content_chars(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                total += len(str(part or ""))
                continue
            if str(part.get("type") or "").strip().lower() == "text":
                total += len(str(part.get("text") or ""))
            elif part.get("image_url") is not None:
                total += 1
        return total
    return len(str(content or ""))
