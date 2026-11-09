"""LLM 接入层。

对外只暴露 complete_json 与 stream_json 两个方法，业务代码不感知具体供应商。
交付期把本地推理服务配成 openai_compatible 即可，无需改动业务代码。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.config import settings

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class LLMError(RuntimeError):
    pass


class LLMTruncatedError(LLMError):
    """输出被 max_tokens 截断。

    与"模型乱写"不同：截断时前半段 JSON 通常是合法的，重试需要让模型精简表述，
    而不是重复同样的请求。
    """


def extract_json(text: str) -> dict[str, Any]:
    """从模型输出中提取 JSON 对象，容忍代码围栏与前后说明文字。"""
    if not text or not text.strip():
        raise LLMError("模型返回为空")

    candidates: list[str] = []
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text.strip())

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    preview = text[:300].replace("\n", " ")
    raise LLMError(f"模型输出无法解析为 JSON：{preview}")


class BaseProvider:
    name = "base"

    async def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""  # pragma: no cover


class OpenAICompatibleProvider(BaseProvider):
    """智谱开放平台与任何 OpenAI 兼容服务（含本地部署）共用此实现。"""

    def __init__(self, base_url: str, api_key: str, model: str, name: str) -> None:
        from openai import AsyncOpenAI

        self.name = name
        self.model = model
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=settings.timeout,
        )

    def _messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    async def complete(self, system: str, user: str) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(system, user),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMTruncatedError(
                f"输出被 max_tokens({settings.max_tokens}) 截断。"
                "请提高 LLM_MAX_TOKENS 或要求模型精简表述。"
            )
        return choice.message.content or ""

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(system, user),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            stream=True,
        )
        finish_reason = None
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            if delta and delta.content:
                yield delta.content

        if finish_reason == "length":
            raise LLMTruncatedError(
                f"输出被 max_tokens({settings.max_tokens}) 截断。"
                "请提高 LLM_MAX_TOKENS 或要求模型精简表述。"
            )


class AnthropicCompatibleProvider(BaseProvider):
    """智谱 Anthropic 兼容端点。

    GLM-4.6 是思考模型，返回的 content 是块列表（thinking 块 + text 块），
    只取 text 块作为正文；thinking 块仅用于观察，不参与 JSON 解析。
    """

    name = "anthropic_compatible"

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self.model = model
        self._client = AsyncAnthropic(
            base_url=base_url,
            api_key=api_key,
            timeout=settings.timeout,
        )

    def _kwargs(self, system: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": settings.max_tokens,
        }
        if not settings.thinking_enabled:
            kwargs["thinking"] = {"type": "disabled"}
            # anthropic SDK 2.6 起 messages.create/stream 不再接受顶层 temperature，
            # 只能经 extra_body 透传给上游；思考开启时上游也不接受自定义 temperature。
            kwargs["extra_body"] = {"temperature": settings.temperature}
        return kwargs

    async def complete(self, system: str, user: str) -> str:
        message = await self._client.messages.create(**self._kwargs(system, user))
        if message.stop_reason == "max_tokens":
            raise LLMTruncatedError(
                f"输出被 max_tokens({settings.max_tokens}) 截断，"
                f"已产出 {message.usage.output_tokens} token。请提高 LLM_MAX_TOKENS 或要求模型精简表述。"
            )
        return "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        async with self._client.messages.stream(**self._kwargs(system, user)) as stream:
            async for event in stream:
                if event.type != "content_block_delta":
                    continue
                delta = event.delta
                # 只透出正文增量，thinking 增量不进 JSON 缓冲区
                if getattr(delta, "type", "") == "text_delta":
                    yield delta.text
            final = await stream.get_final_message()

        if final.stop_reason == "max_tokens":
            raise LLMTruncatedError(
                f"输出被 max_tokens({settings.max_tokens}) 截断，"
                f"已产出 {final.usage.output_tokens} token。请提高 LLM_MAX_TOKENS 或要求模型精简表述。"
            )


class MockProvider(BaseProvider):
    """离线占位实现，仅供前端联调使用。

    返回的内容带有明显的 [MOCK] 标记，便于区分真实模型输出。
    """

    name = "mock"

    async def complete(self, system: str, user: str) -> str:
        from app.llm.mock_payload import build_mock_payload

        return json.dumps(build_mock_payload(system, user), ensure_ascii=False)

    async def stream(self, system: str, user: str) -> AsyncIterator[str]:
        payload = await self.complete(system, user)
        step = 160
        for index in range(0, len(payload), step):
            yield payload[index : index + step]


_provider: BaseProvider | None = None


def get_provider() -> BaseProvider:
    global _provider
    if _provider is not None:
        return _provider

    provider = settings.llm_provider
    if provider == "mock":
        _provider = MockProvider()
    elif provider == "anthropic_compatible":
        if not settings.anthropic_api_key:
            raise LLMError(
                "未配置 ANTHROPIC_COMPAT_API_KEY。请在 backend/.env 中填入智谱密钥。"
            )
        _provider = AnthropicCompatibleProvider(
            base_url=settings.anthropic_base_url,
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    elif provider == "openai_compatible":
        _provider = OpenAICompatibleProvider(
            base_url=settings.compat_base_url,
            api_key=settings.compat_api_key,
            model=settings.compat_model,
            name="openai_compatible",
        )
    else:
        if not settings.zhipu_api_key:
            raise LLMError(
                "未配置 ZHIPU_API_KEY。请复制 backend/.env.example 为 backend/.env 并填入密钥，"
                "或设置 LLM_PROVIDER=mock 以离线联调前端。"
            )
        _provider = OpenAICompatibleProvider(
            base_url=settings.zhipu_base_url,
            api_key=settings.zhipu_api_key,
            model=settings.zhipu_model,
            name="zhipu",
        )
    return _provider
