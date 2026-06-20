_MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DAYS_BEFORE_MONTH = [
    0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334,
]


def _is_leap_year(year):
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _days_since_epoch(year, month, day):
    """Days from 1970-01-01 to the given date."""
    y = year - 1
    days = y * 365 + y // 4 - y // 100 + y // 400
    days -= 719162  # days from year 0 to 1969-12-31
    days += _DAYS_BEFORE_MONTH[month] + day
    if month > 2 and _is_leap_year(year):
        days += 1
    return days


def _to_unix_epoch(year, month, day, hour, minute, second):
    """Convert date/time components to Unix epoch seconds (UTC)."""
    days = _days_since_epoch(year, month, day)
    return days * 86400 + hour * 3600 + minute * 60 + second


def parse_iso_datetime(s):
    """Parse ISO 8601 datetime string to Unix epoch seconds.

    Example: '2026-02-25T11:04:41.596Z' -> 1772017481
    """
    year = int(s[0:4])
    month = int(s[5:7])
    day = int(s[8:10])
    hour = int(s[11:13])
    minute = int(s[14:16])
    second = int(s[17:19])
    return _to_unix_epoch(year, month, day, hour, minute, second)


def parse_http_date(s):
    """Parse HTTP Date header to Unix epoch seconds.

    Example: 'Thu, 27 Feb 2026 12:00:00 GMT' -> 1772193600
    """
    parts = s.split()
    day = int(parts[1])
    month = _MONTH_NAMES.get(parts[2].lower()[:3], 1)
    year = int(parts[3])
    t = parts[4].split(":")
    hour = int(t[0])
    minute = int(t[1])
    second = int(t[2])
    return _to_unix_epoch(year, month, day, hour, minute, second)
