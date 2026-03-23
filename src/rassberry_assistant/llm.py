from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Any

import requests


DEFAULT_JARVIS_SYSTEM_PROMPT = """Ты — JARVIS MAX, личный интеллектуальный ассистент.

Обращайся к пользователю уважительно, на "сэр", минимум один раз в каждом ответе.

Твой характер:
- спокойный, уверенный, собранный;
- умный, наблюдательный и слегка циничный;
- умеешь шутить остро и качественно, но коротко и по делу;
- никогда не хамишь пользователю и не скатываешься в дешёвую клоунаду.

Правила:
- Говори как живой ассистент в стиле JARVIS: естественно, уверенно, с сухим умным юмором.
- Отвечай только устной речью: без markdown, списков, заголовков, эмодзи и технического мусора.
- Пиши так, будто произносишь ответ вслух.
- Отвечай на том языке, на котором к тебе обращаются.
- Обычно укладывайся в 2-4 коротких предложения.
- Если запрос бытовой или практический, отвечай прямо и полезно, без лишней философии.
- Если уместна шутка, делай её короткой, циничной и элегантной. Не шути в опасных, медицинских, денежных и реально тревожных ситуациях.
- Не выдумывай системные протоколы, фоновые процессы, ошибки Windows, уведомления и внутреннюю диагностику без прямого запроса.
- Если не знаешь точного факта, скажи это кратко и честно, без рассуждений про ограничения модели.
- Не спорь с пользователем ради самоутверждения. Если он ошибается, поправляй спокойно, чётко и с уважением.
"""

DEFAULT_JARVIS_PRIMER_MESSAGES: list[dict[str, str]] = [
    {
        "role": "assistant",
        "content": "Я JARVIS MAX. Рад приветствовать вас, сэр. Мир ещё не развалился, так что можем работать.",
    },
    {"role": "user", "content": "Доброе утро"},
    {
        "role": "assistant",
        "content": "Доброе утро, сэр. Если день снова решил испытать вас на прочность, я хотя бы сделаю это зрелище продуктивным.",
    },
    {"role": "user", "content": "Открой телеграм"},
    {
        "role": "assistant",
        "content": "Конечно, сэр. Если локальной команды нет, я скажу это прямо, а не устрою театр абсурда.",
    },
]


class ChatClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        system_prompt: str,
        timeout_seconds: int,
        max_history_messages: int,
        http_referer: str,
        app_title: str,
        options: dict[str, Any] | None = None,
        primer_messages: list[dict[str, str]] | None = None,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.timeout_seconds = timeout_seconds
        self.http_referer = http_referer
        self.app_title = app_title
        self.options = options or {}
        self.primer_messages = primer_messages or []
        self.history: deque[dict[str, str]] = deque(maxlen=max_history_messages * 2)
        self._lock = Lock()
        self._session = requests.Session()
        self._session.headers.update(self._headers())

    def chat(self, user_text: str) -> str:
        payload = self._build_payload(user_text)
        with self._session.post(
            self.api_url,
            json=payload,
            timeout=self.timeout_seconds,
        ) as response:
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        content = self._extract_content(body).strip()

        if content:
            with self._lock:
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": content})
        return content

    def warm_up(self) -> None:
        return

    def reset_history(self) -> None:
        with self._lock:
            self.history.clear()

    def _build_payload(self, user_text: str) -> dict[str, Any]:
        with self._lock:
            history = list(self.history)
        messages: list[dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.primer_messages)
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        payload.update(self.options)
        return payload

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }

    @staticmethod
    def _extract_content(body: dict[str, Any]) -> str:
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "") or ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "".join(chunks)
        return str(content)


OllamaClient = ChatClient
