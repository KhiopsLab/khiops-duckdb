"""Khiops date and time formats as DuckDB ``strftime`` formats."""

from itertools import product

FORMAT_KEYS = {
    "Date": "DateFormat",
    "Time": "TimeFormat",
    "Timestamp": "TimestampFormat",
    "TimestampTZ": "TimestampTZFormat",
}
_NATIVE = {
    "Date": "YYYY-MM-DD",
    "Time": "HH:MM:SS.",
    "Timestamp": "YYYY-MM-DD HH:MM:SS.",
    "TimestampTZ": "YYYY-MM-DD HH:MM:SS.zzzzzz",
}
_ZONES = {"zzzzzz": "+00:00", "zzzzz": "+0000"}
_COMPACT_TIMES = ("HHMMSS", "HHMMSS.", "HHMM")


def _date_formats() -> dict[str, str]:
    codes = {"YYYY": "%Y", "MM": "%m", "DD": "%d"}
    orders = (
        ("YYYY", "MM", "DD"),
        ("DD", "MM", "YYYY"),
        ("YYYY", "DD", "MM"),
        ("MM", "DD", "YYYY"),
    )
    return {
        separator.join(order): separator.join(codes[field] for field in order)
        for order, separator in product(orders, ("-", "/", ".", ""))
    }


def _time_formats() -> dict[str, str]:
    formats = {"HHMMSS": "%H%M%S", "HHMMSS.": "%H%M%S.%g", "HHMM": "%H%M"}
    padded = (("HH", "MM", "SS"), ("%H", "%M", "%S"))
    unpadded = (("(H)H", "(M)M", "(S)S"), ("%-H", "%-M", "%-S"))
    for separator, (names, codes) in product((":", "."), (padded, unpadded)):
        short = separator.join(names[:2]), separator.join(codes[:2])
        full = separator.join(names), separator.join(codes)
        formats[short[0]] = short[1]
        formats[full[0]] = full[1]
        formats[full[0] + "."] = full[1] + ".%g"
    return formats


_DATES = _date_formats()
_TIMES = _time_formats()


def _timestamp_format(khiops_format: str) -> str | None:
    for date, date_code in _DATES.items():
        if not khiops_format.startswith(date):
            continue
        rest = khiops_format[len(date) :]
        if rest[:1] in (" ", "-", "_", "T") and rest[1:] in _TIMES:
            return date_code + rest[0] + _TIMES[rest[1:]]
        if date.isalpha() and rest in _COMPACT_TIMES:
            return date_code + _TIMES[rest]
    return None


def strftime_format(kind: str, khiops_format: str | None) -> tuple[str, str] | None:
    """Return the ``strftime`` format and UTC zone suffix, or None if unknown.

    A ``khiops_format`` of None means the native Khiops format of ``kind``.
    """
    text = _NATIVE[kind] if khiops_format is None else khiops_format
    zone = ""
    if kind == "TimestampTZ":
        marker = next((name for name in _ZONES if text.endswith(name)), None)
        if marker is None:
            return None
        text, zone = text[: -len(marker)], _ZONES[marker]
    if kind == "Date":
        code = _DATES.get(text)
    elif kind == "Time":
        code = _TIMES.get(text)
    else:
        code = _timestamp_format(text)
    return None if code is None else (code, zone)
