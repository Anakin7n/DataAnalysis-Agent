"""
DeepSeek API 封装 — 通过 OpenAI 兼容接口调用。
只暴露一个函数: chat(system_prompt, user_message) -> str
"""
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS, LLM_TIMEOUT

_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


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
