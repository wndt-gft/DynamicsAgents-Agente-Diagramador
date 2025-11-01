import os


TRUE_VALUES = {"1", "true", "yes", "on", "y"}
FALSE_VALUES = {"0", "false", "no", "off", "n"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    v = value.strip().lower()
    if v in TRUE_VALUES:
        return True
    if v in FALSE_VALUES:
        return False
    return default


def is_logging_enabled() -> bool:
    """
    Return True if LOGGING_ENABLE is set truthy in environment (.env supported).
    Defaults to False to avoid leaking sensitive data by default.
    """
    return parse_bool(os.getenv("LOGGING_ENABLE"), default=False)
