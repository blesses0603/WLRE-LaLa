"""診斷資料結構化清理：預設不輸出憑證欄位的值。"""
from collections.abc import Mapping

_SENSITIVE = frozenset({'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token', 'secret', 'api_key', 'cookie', 'authorization', 'credential', '密碼', '令牌', '憑證'})


def sanitize_fields(data):
    """回傳已遮罩的複本；不可將未清理封包原文直接傳給 Log。"""
    if isinstance(data, Mapping):
        return {str(k): '[已遮罩]' if str(k).casefold() in _SENSITIVE else sanitize_fields(v) for k, v in data.items()}
    if isinstance(data, (tuple, list)):
        return [sanitize_fields(x) for x in data]
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    return '[非預期資料類型]'
