from __future__ import annotations

import logging
import re


_SENSITIVE_QUERY_VALUE = re.compile(
    r"([?&](?:api_key|access_token|refresh_token|token|secret|key)=)[^&\s]*",
    flags=re.IGNORECASE,
)


def redact_access_path(value: str) -> str:
    return _SENSITIVE_QUERY_VALUE.sub(r"\1[REDACTED]", value)


class AccessLogSecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            values = list(record.args)
            if isinstance(values[2], str):
                values[2] = redact_access_path(values[2])
                record.args = tuple(values)
        return True


def install_access_log_secret_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, AccessLogSecretFilter) for item in logger.filters):
        return
    logger.addFilter(AccessLogSecretFilter())
