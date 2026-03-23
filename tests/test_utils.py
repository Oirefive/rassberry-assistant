import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rassberry_assistant.utils import normalize_text, prepare_tts_text, render_template


class UtilsTests(unittest.TestCase):
    def test_normalize_text(self) -> None:
        self.assertEqual(normalize_text("Привет,   Ёж!"), "привет еж")

    def test_render_template(self) -> None:
        payload = {"text": "Привет, {name}!", "items": ["{name}", 1]}
        rendered = render_template(payload, {"name": "Джарвис"})
        self.assertEqual(rendered["text"], "Привет, Джарвис!")
        self.assertEqual(rendered["items"][0], "Джарвис")

    def test_prepare_tts_text_expands_abbreviations(self) -> None:
        spoken = prepare_tts_text("г. Москва, ул. Ленина, д. 7, стр. 12, № 5 и т.д.")
        self.assertEqual(
            spoken,
            "город Москва, улица Ленина, дом семь, страница двенадцать, номер пять и так далее",
        )

    def test_prepare_tts_text_formats_date_time_and_currency(self) -> None:
        spoken = prepare_tts_text("Встреча 17.03.2026 в 08:05, бюджет 1250,50 ₽")
        self.assertEqual(
            spoken,
            "Встреча семнадцатое марта две тысячи двадцать шесть года в восемь часов пять минут, бюджет одна тысяча двести пятьдесят рублей пятьдесят копеек",
        )

    def test_prepare_tts_text_formats_rub_currency_code(self) -> None:
        spoken = prepare_tts_text("Бюджет 1250.50 RUB")
        self.assertEqual(
            spoken,
            "Бюджет одна тысяча двести пятьдесят рублей пятьдесят копеек",
        )

    def test_prepare_tts_text_formats_percent_and_decimal(self) -> None:
        spoken = prepare_tts_text("Загрузка 12.5% и курс 3.14")
        self.assertEqual(
            spoken,
            "Загрузка двенадцать точка пять процентов и курс три точка один четыре",
        )

    def test_prepare_tts_text_formats_minutes_in_feminine_gender(self) -> None:
        spoken = prepare_tts_text("Сейчас 02:32.")
        self.assertEqual(spoken, "Сейчас два часа тридцать две минуты")

    def test_prepare_tts_text_strips_sentence_endings_for_tts(self) -> None:
        spoken = prepare_tts_text("Первое предложение. Второе предложение? Третье!")
        self.assertEqual(spoken, "Первое предложение, Второе предложение, Третье")


if __name__ == "__main__":
    unittest.main()
