import re
from datetime import date

from backend.forecast.errors import ForecastSourceInvalidError


QUARTER_PATTERNS = (
    re.compile(r"([1-4])Q(\d{2})F"),
    re.compile(r"Q([1-4])\s+(\d{4})"),
)


def parse_quarter_end(label: str) -> date:
    cleaned = " ".join(label.split())
    for index, pattern in enumerate(QUARTER_PATTERNS):
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue
        quarter = int(match.group(1))
        raw_year = int(match.group(2))
        year = 2000 + raw_year if index == 0 else raw_year
        month, day = {
            1: (3, 31),
            2: (6, 30),
            3: (9, 30),
            4: (12, 31),
        }[quarter]
        return date(year, month, day)
    raise ForecastSourceInvalidError()
