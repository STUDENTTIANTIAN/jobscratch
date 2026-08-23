#!/usr/bin/env python3
"""LLM 连接层 — 调用 OpenAI 兼容 chat 接口,只负责收发,不关心业务数据。"""

import json
import requests

try:
    from .llm_config import LLMConfig
except ImportError:
    from llm_config import LLMConfig


def llm_chat(messages, config: LLMConfig, timeout=120) -> str:
    """调用 OpenAI 兼容 chat 接口,返回 assistant 文本内容。

    参数:
        messages: list[dict],如 [{"role":"system","content":...}, {"role":"user","content":...}]
        config: LLMConfig,必填项缺失时由 validate() 抛 RuntimeError
        timeout: 秒,网络超时

    返回:
        assistant 的文本回复

    异常:
        RuntimeError: 配置缺失必填项
        requests.RequestException: 网络/接口错误(由调用方决定是否降级)
    """
    config.validate()
    if not messages:
        raise ValueError("messages 不能为空")

    url = config.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # 兼容两种返回形态:choices[].message.content / choices[].text
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"LLM 返回异常,无 choices: {json.dumps(data, ensure_ascii=False)[:200]}")
    content = (
        choices[0].get("message", {}).get("content")
        or choices[0].get("text")
    )
    if not content:
        raise RuntimeError("LLM 返回的 content 为空")
    return content.strip()


if __name__ == "__main__":
    cfg = LLMConfig()
    print(cfg)
    reply = llm_chat(
        [{"role": "user", "content": "只回复两个字:你好"}],
        cfg,
    )
    print(f"回复: {reply}")