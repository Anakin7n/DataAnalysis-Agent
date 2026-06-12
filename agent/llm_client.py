"""
DeepSeek API 封装 — 通过 OpenAI 兼容接口调用。
只暴露一个函数: chat(system_prompt, user_message) -> str
"""
import json
import re

from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_TIMEOUT

_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, max_retries=0)


def _strip_markdown_fence(text: str) -> str:
    """去掉 LLM 可能添加的 ```json ... ``` 包裹。"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def chat(system_prompt: str, user_message: str) -> str:
    """发送请求到 DeepSeek，返回响应文本。异常直接上抛。"""
    response = _client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        timeout=LLM_TIMEOUT,
    )
    return response.choices[0].message.content


def chat_json(system_prompt: str, user_message: str) -> dict:
    """chat() + JSON 清洗 + 解析。失败直接上抛。"""
    raw = chat(system_prompt, user_message)
    cleaned = _strip_markdown_fence(raw)
    return json.loads(cleaned)
