from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
from typing import Any


_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_TTS_SPACE_RE = re.compile(r"\s+")
_TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_DATE_RE = re.compile(r"\b([0-3]?\d)[./]([01]?\d)[./](\d{4})\b")
_TTS_SENTENCE_END_RE = re.compile(r"\s*[.!?…]+(?=\s|$)")
_TTS_COMMA_RE = re.compile(r"\s*,\s*")
_PERCENT_RE = re.compile(r"(?<!\w)(-?\d[\d\s]*(?:[.,]\d+)?)\s*%")
_RUBLE_RE = re.compile(r"(?<!\w)(-?\d[\d\s]*(?:[.,]\d+)?)\s*(?:₽|rub|руб\.?|рубля|рублей|руб)(?!\w)", re.IGNORECASE)
_DOLLAR_RE = re.compile(r"(?<!\w)(?:\$|usd\s*)(-?\d[\d\s]*(?:[.,]\d+)?)|(?<!\w)(-?\d[\d\s]*(?:[.,]\d+)?)\s*(?:\$|usd)(?!\w)", re.IGNORECASE)
_EURO_RE = re.compile(r"(?<!\w)(?:€|eur\s*)(-?\d[\d\s]*(?:[.,]\d+)?)|(?<!\w)(-?\d[\d\s]*(?:[.,]\d+)?)\s*(?:€|eur)(?!\w)", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"(?<![\w/])(-?\d[\d\s]*[.,]\d+)(?![\w/])")
_INTEGER_RE = re.compile(r"(?<![\w/.,-])(-?\d[\d\s]*)(?![\w/])")

_ABBREVIATION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bт\.\s?д\.", re.IGNORECASE), "так далее"),
    (re.compile(r"\bт\.\s?п\.", re.IGNORECASE), "тому подобное"),
    (re.compile(r"№\s*", re.IGNORECASE), "номер "),
    (re.compile(r"(?<=\d)\s*г\.", re.IGNORECASE), " год"),
    (re.compile(r"\bг\.\s*", re.IGNORECASE), "город "),
    (re.compile(r"\bул\.\s*", re.IGNORECASE), "улица "),
    (re.compile(r"\bд\.\s*", re.IGNORECASE), "дом "),
    (re.compile(r"\bстр\.\s*", re.IGNORECASE), "страница "),
]

_UNITS = {
    "masc": ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"],
    "fem": ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"],
}
_TEENS = {
    10: "десять",
    11: "одиннадцать",
    12: "двенадцать",
    13: "тринадцать",
    14: "четырнадцать",
    15: "пятнадцать",
    16: "шестнадцать",
    17: "семнадцать",
    18: "восемнадцать",
    19: "девятнадцать",
}
_TENS = {
    2: "двадцать",
    3: "тридцать",
    4: "сорок",
    5: "пятьдесят",
    6: "шестьдесят",
    7: "семьдесят",
    8: "восемьдесят",
    9: "девяносто",
}
_HUNDREDS = {
    1: "сто",
    2: "двести",
    3: "триста",
    4: "четыреста",
    5: "пятьсот",
    6: "шестьсот",
    7: "семьсот",
    8: "восемьсот",
    9: "девятьсот",
}
_SCALES = [
    (1_000_000_000, ("миллиард", "миллиарда", "миллиардов"), "masc"),
    (1_000_000, ("миллион", "миллиона", "миллионов"), "masc"),
    (1_000, ("тысяча", "тысячи", "тысяч"), "fem"),
]
_MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}
_ORDINAL_DAYS = {
    1: "первое",
    2: "второе",
    3: "третье",
    4: "четвертое",
    5: "пятое",
    6: "шестое",
    7: "седьмое",
    8: "восьмое",
    9: "девятое",
    10: "десятое",
    11: "одиннадцатое",
    12: "двенадцатое",
    13: "тринадцатое",
    14: "четырнадцатое",
    15: "пятнадцатое",
    16: "шестнадцатое",
    17: "семнадцатое",
    18: "восемнадцатое",
    19: "девятнадцатое",
    20: "двадцатое",
    21: "двадцать первое",
    22: "двадцать второе",
    23: "двадцать третье",
    24: "двадцать четвертое",
    25: "двадцать пятое",
    26: "двадцать шестое",
    27: "двадцать седьмое",
    28: "двадцать восьмое",
    29: "двадцать девятое",
    30: "тридцатое",
    31: "тридцать первое",
}


class SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalize_text(text: str) -> str:
    cleaned = text.lower().replace("ё", "е")
    cleaned = _NON_WORD_RE.sub(" ", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def render_template(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format_map(SafeFormatDict(context))
    if isinstance(value, list):
        return [render_template(item, context) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, context) for key, item in value.items()}
    return value


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _choose_plural(value: int, forms: tuple[str, str, str]) -> str:
    remainder_100 = value % 100
    remainder_10 = value % 10
    if 11 <= remainder_100 <= 19:
        return forms[2]
    if remainder_10 == 1:
        return forms[0]
    if 2 <= remainder_10 <= 4:
        return forms[1]
    return forms[2]


def _triplet_to_words(value: int, gender: str = "masc") -> list[str]:
    words: list[str] = []
    if value >= 100:
        words.append(_HUNDREDS[value // 100])
        value %= 100
    if 10 <= value <= 19:
        words.append(_TEENS[value])
        return words
    if value >= 20:
        words.append(_TENS[value // 10])
        value %= 10
    if value:
        words.append(_UNITS["fem" if gender == "fem" else "masc"][value])
    return words


def number_to_words_ru(value: int, gender: str = "masc") -> str:
    if value == 0:
        return "ноль"
    if value < 0:
        return "минус " + number_to_words_ru(abs(value), gender=gender)

    remainder = value
    words: list[str] = []
    for scale_value, scale_forms, scale_gender in _SCALES:
        if remainder < scale_value:
            continue
        scale_count = remainder // scale_value
        remainder %= scale_value
        words.extend(_triplet_to_words(scale_count, gender=scale_gender))
        words.append(_choose_plural(scale_count, scale_forms))

    if remainder:
        words.extend(_triplet_to_words(remainder, gender=gender))
    return " ".join(words).strip()


def _parse_decimal_number(raw: str) -> tuple[int, str | None]:
    cleaned = raw.replace(" ", "").replace(",", ".")
    negative = cleaned.startswith("-")
    if negative:
        cleaned = cleaned[1:]
    if "." in cleaned:
        integer_part, fractional_part = cleaned.split(".", 1)
        integer_value = int(integer_part or "0")
        if negative:
            integer_value = -integer_value
        return integer_value, fractional_part.rstrip("0") or "0"
    value = int(cleaned or "0")
    return (-value if negative else value), None


def _format_currency(raw: str, major_forms: tuple[str, str, str], minor_forms: tuple[str, str, str] | None = None) -> str:
    integer_value, fractional_digits = _parse_decimal_number(raw)
    negative_prefix = "минус " if integer_value < 0 or raw.strip().startswith("-") else ""
    absolute_integer = abs(integer_value)
    parts = [f"{negative_prefix}{number_to_words_ru(absolute_integer)} {_choose_plural(absolute_integer, major_forms)}".strip()]
    if minor_forms and fractional_digits is not None:
        fractional_value = int((fractional_digits + "00")[:2])
        parts.append(f"{number_to_words_ru(fractional_value, gender='fem')} {_choose_plural(fractional_value, minor_forms)}")
    return " ".join(part for part in parts if part).strip()


def _replace_dollars(match: re.Match[str]) -> str:
    raw = match.group(1) or match.group(2) or "0"
    return _format_currency(raw, ("доллар", "доллара", "долларов"), ("цент", "цента", "центов"))


def _replace_euros(match: re.Match[str]) -> str:
    raw = match.group(1) or match.group(2) or "0"
    integer_value, fractional_digits = _parse_decimal_number(raw)
    negative_prefix = "минус " if integer_value < 0 or raw.strip().startswith("-") else ""
    absolute_integer = abs(integer_value)
    parts = [f"{negative_prefix}{number_to_words_ru(absolute_integer)} евро".strip()]
    if fractional_digits is not None:
        cents = int((fractional_digits + '00')[:2])
        parts.append(f"{number_to_words_ru(cents, gender='fem')} {_choose_plural(cents, ('цент', 'цента', 'центов'))}")
    return " ".join(part for part in parts if part).strip()


def _replace_rubles(match: re.Match[str]) -> str:
    return _format_currency(match.group(1), ("рубль", "рубля", "рублей"), ("копейка", "копейки", "копеек"))


def _replace_percent(match: re.Match[str]) -> str:
    integer_value, fractional_digits = _parse_decimal_number(match.group(1))
    if fractional_digits is not None:
        digits = " ".join(number_to_words_ru(int(digit)) for digit in fractional_digits)
        return f"{number_to_words_ru(integer_value)} точка {digits} процентов"
    return f"{number_to_words_ru(integer_value)} {_choose_plural(abs(integer_value), ('процент', 'процента', 'процентов'))}"


def _replace_time(match: re.Match[str]) -> str:
    hours = int(match.group(1))
    minutes = int(match.group(2))
    parts = [
        f"{number_to_words_ru(hours)} {_choose_plural(hours, ('час', 'часа', 'часов'))}",
    ]
    if minutes:
        parts.append(
            f"{number_to_words_ru(minutes, gender='fem')} "
            f"{_choose_plural(minutes, ('минута', 'минуты', 'минут'))}"
        )
    return " ".join(parts)


def _replace_date(match: re.Match[str]) -> str:
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    try:
        datetime(year, month, day)
    except ValueError:
        return match.group(0)
    day_text = _ORDINAL_DAYS.get(day, number_to_words_ru(day))
    month_text = _MONTHS_GENITIVE[month]
    year_text = number_to_words_ru(year)
    return f"{day_text} {month_text} {year_text} года"


def _replace_decimal(match: re.Match[str]) -> str:
    integer_value, fractional_digits = _parse_decimal_number(match.group(1))
    if not fractional_digits:
        return number_to_words_ru(integer_value)
    fractional_words = " ".join(number_to_words_ru(int(digit)) for digit in fractional_digits)
    return f"{number_to_words_ru(integer_value)} точка {fractional_words}"


def _replace_integer(match: re.Match[str]) -> str:
    return number_to_words_ru(int(match.group(1).replace(" ", "")))


def prepare_tts_text(text: str) -> str:
    spoken = " ".join(str(text).split()).strip()
    if not spoken:
        return ""

    for pattern, replacement in _ABBREVIATION_PATTERNS:
        spoken = pattern.sub(replacement, spoken)

    spoken = _DATE_RE.sub(_replace_date, spoken)
    spoken = _TIME_RE.sub(_replace_time, spoken)
    spoken = _RUBLE_RE.sub(_replace_rubles, spoken)
    spoken = _DOLLAR_RE.sub(_replace_dollars, spoken)
    spoken = _EURO_RE.sub(_replace_euros, spoken)
    spoken = _PERCENT_RE.sub(_replace_percent, spoken)
    spoken = _DECIMAL_RE.sub(_replace_decimal, spoken)
    spoken = _INTEGER_RE.sub(_replace_integer, spoken)
    spoken = _TTS_SENTENCE_END_RE.sub(",", spoken)
    spoken = _TTS_COMMA_RE.sub(", ", spoken)
    spoken = _TTS_SPACE_RE.sub(" ", spoken)
    return spoken.strip(" ,")
