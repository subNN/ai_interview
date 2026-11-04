from __future__ import annotations

import threading
from typing import Callable

from openai import OpenAI

from ..models import AppSettings, Secrets


class LlmError(RuntimeError):
    pass


class LlmClient:
    def __init__(self, settings: AppSettings, secrets: Secrets, system_prompt: str):
        self.settings = settings
        self.secrets = secrets
        self.system_prompt = system_prompt
        key = (
            secrets.deepseek_api_key
            if settings.llm_provider == "deepseek"
            else secrets.openai_api_key
        ).strip()
        if not key:
            raise LlmError("\u672a\u914d\u7f6e\u5f53\u524d\u6a21\u578b\u7684 API Key")
        self._api_key = key
        self._base_url = settings.llm_api_base.strip()
        self._clients = {}

    def _base_candidates(self) -> list[str | None]:
        if not self._base_url:
            return [None]
        base = self._base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
        candidates = [base]
        if not base.endswith("/v1"):
            candidates.append(base + "/v1")
        result = []
        for candidate in candidates:
            if candidate not in result:
                result.append(candidate)
        return result

    def _client(self, base_url: str | None) -> OpenAI:
        if base_url not in self._clients:
            kwargs = {"api_key": self._api_key, "timeout": 30.0}
            if base_url:
                kwargs["base_url"] = base_url
            self._clients[base_url] = OpenAI(**kwargs)
        return self._clients[base_url]

    @staticmethod
    def _choice_text(value) -> str:
        if not value:
            return ""
        choices = getattr(value, "choices", None) or []
        if not choices:
            return ""
        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is not None:
            for field in ("content", "reasoning_content"):
                text = getattr(message, field, None)
                if text:
                    return str(text)
        for field in ("text", "content", "reasoning_content"):
            text = getattr(choice, field, None)
            if text:
                return str(text)
        return ""

    @staticmethod
    def _delta_text(chunk) -> tuple[str, str]:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return "", ""
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return "", ""
        content = str(getattr(delta, "content", None) or "")
        reasoning = str(getattr(delta, "reasoning_content", None) or "")
        return content, reasoning

    def _messages(self, question: str, history: list[dict[str, str]]):
        messages = [{"role": "system", "content": self.system_prompt}]
        if self.settings.max_history > 0:
            messages.extend(history[-self.settings.max_history * 2 :])
        messages.append({"role": "user", "content": question})
        return messages

    def _request_kwargs(self, messages, stream: bool, fast_mode: bool = False):
        kwargs = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
            "stream": stream,
        }
        if fast_mode and not self.settings.llm_thinking_enabled:
            kwargs["reasoning_effort"] = "none"
            kwargs["extra_body"] = {
                "thinking": {"type": "disabled"},
                "enable_thinking": False,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        return kwargs

    def ask_stream(
        self,
        question: str,
        history: list[dict[str, str]],
        on_delta: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> str:
        messages = self._messages(question, history)
        errors: list[str] = []
        request_modes = (
            [False]
            if self.settings.llm_thinking_enabled
            else [True, False]
        )
        for base_url in self._base_candidates():
            for fast_mode in request_modes:
                if cancel_event.is_set():
                    return "\u5df2\u505c\u6b62"
                client = self._client(base_url)
                label = "fast" if fast_mode else "normal"
                try:
                    response = client.chat.completions.create(
                        **self._request_kwargs(messages, True, fast_mode)
                    )
                    answer_parts: list[str] = []
                    reasoning_parts: list[str] = []
                    for chunk in response:
                        if cancel_event.is_set():
                            return "\u5df2\u505c\u6b62"
                        content, reasoning = self._delta_text(chunk)
                        if content:
                            answer_parts.append(content)
                            on_delta(content)
                        if reasoning:
                            reasoning_parts.append(reasoning)
                    answer = "".join(answer_parts).strip()
                    if answer:
                        return answer
                    reasoning_text = "".join(reasoning_parts).strip()
                    if reasoning_text:
                        on_delta(reasoning_text)
                        return reasoning_text
                    errors.append(f"{label} {base_url or 'default'}: stream returned no content")
                except Exception as exc:
                    errors.append(f"{label} {base_url or 'default'}: {exc}")

                if cancel_event.is_set():
                    return "\u5df2\u505c\u6b62"
                try:
                    response = client.chat.completions.create(
                        **self._request_kwargs(messages, False, fast_mode)
                    )
                    answer = self._choice_text(response).strip()
                    if answer:
                        on_delta(answer)
                        return answer
                    errors.append(f"{label} {base_url or 'default'}: response returned no content")
                except Exception as exc:
                    errors.append(f"{label} {base_url or 'default'}: {exc}")

        detail = "; ".join(errors[-6:])
        raise LlmError(
            "AI \u56de\u7b54\u751f\u6210\u5931\u8d25\uff1a"
            + (detail or "\u670d\u52a1\u672a\u8fd4\u56de\u6709\u6548\u5185\u5bb9")
        )
