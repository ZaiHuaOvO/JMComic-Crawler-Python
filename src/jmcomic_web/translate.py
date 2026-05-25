from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, List, Optional

import json
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


@dataclass
class TranslateSettings:
    enabled: bool = False
    provider: str = "google"
    source_lang: str = "auto"
    target_lang: str = "zh-CN"
    timeout: float = 10.0


class BaseTranslator:
    """翻译适配器基类。翻译失败必须回退到原文，不影响下载主流程。"""

    def translate(self, text: str) -> str:
        raise NotImplementedError


class NoopTranslator(BaseTranslator):
    def translate(self, text: str) -> str:
        return text


class GoogleTranslateTranslator(BaseTranslator):
    """使用 Google Translate 的公开接口做轻量机翻。"""

    def __init__(self, source_lang: str = "auto", target_lang: str = "zh-CN", timeout: float = 10.0):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.timeout = timeout

    @lru_cache(maxsize=2048)
    def translate(self, text: str) -> str:
        if not text:
            return text

        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl={quote_plus(self.source_lang)}"
            f"&tl={quote_plus(self.target_lang)}&dt=t&q={quote_plus(text)}"
        )
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

        with urlopen(request, timeout=self.timeout) as resp:
            payload = resp.read().decode("utf-8")

        data = json.loads(payload)
        parts = data[0] if isinstance(data, list) and data else []
        translated = "".join(part[0] for part in parts if part and part[0])
        return translated or text


def build_translator(settings: TranslateSettings) -> BaseTranslator:
    """根据配置构建翻译器。"""
    if not settings.enabled:
        return NoopTranslator()

    provider = (settings.provider or "").strip().lower()
    if provider in {"google", "gtx"}:
        return GoogleTranslateTranslator(
            source_lang=settings.source_lang,
            target_lang=settings.target_lang,
            timeout=settings.timeout,
        )

    # 其他 provider 预留为扩展点，当前先安全回退。
    return NoopTranslator()


def translate_many(translator: BaseTranslator, texts: Iterable[str]) -> List[str]:
    """批量翻译，逐个容错。"""
    result: List[str] = []
    for text in texts:
        try:
            result.append(translator.translate(text))
        except Exception:
            result.append(text)
    return result
