"""
飞书 REST API 封装 — token 管理 + 消息/文件收发。
所有请求同步，在 WS 事件线程中调用。
"""
import json
import time
import logging
import requests

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DOMAIN

log = logging.getLogger(__name__)

_token = {"value": "", "expire": 0}


def _get_token() -> str:
    """获取 tenant_access_token，自动缓存和刷新。"""
    now = time.time()
    if _token["value"] and now < _token["expire"]:
        return _token["value"]

    resp = requests.post(
        f"{FEISHU_DOMAIN}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise Exception(f"获取飞书 token 失败: {data}")

    _token["value"] = data["tenant_access_token"]
    _token["expire"] = now + data.get("expire", 7200) - 300
    return _token["value"]


def _post(path: str, json_body: dict | None = None, files: dict | None = None, data: dict | None = None) -> dict:
    """飞书 POST 请求封装。返回完整 JSON 响应。"""
    headers = {"Authorization": f"Bearer {_get_token()}"}
    kwargs = {"headers": headers, "timeout": 30}
    if files:
        kwargs["files"] = files
        if data:
            kwargs["data"] = data
    else:
        kwargs["json"] = json_body or {}

    resp = requests.post(f"{FEISHU_DOMAIN}{path}", **kwargs)
    result = resp.json()
    code = result.get("code", -1)
    if code != 0:
        log.error(f"飞书 API 错误 [{path}]: code={code} msg={result.get('msg')}")
    return result


# ── 消息发送 ──

def send_text(chat_id: str, text: str):
    """发送文本消息到群聊。"""
    content = json.dumps({"text": text}, ensure_ascii=False)
    _post(
        f"/open-apis/im/v1/messages?receive_id_type=chat_id",
        {"receive_id": chat_id, "msg_type": "text", "content": content},
    )


def send_file(chat_id: str, file_path: str, file_name: str):
    """上传并发送文件到群聊。"""
    # 1. 上传文件获取 file_key
    with open(file_path, "rb") as f:
        resp = _post(
            "/open-apis/im/v1/files",
            files={"file": (file_name, f)},
            data={"file_type": "stream", "file_name": file_name},
        )
    if resp.get("code") != 0:
        return

    file_key = resp["data"]["file_key"]

    # 2. 发送文件消息
    content = json.dumps({"file_key": file_key}, ensure_ascii=False)
    _post(
        f"/open-apis/im/v1/messages?receive_id_type=chat_id",
        {"receive_id": chat_id, "msg_type": "file", "content": content},
    )


# ── 文件下载 ──

def download_file_from_message(message_id: str, file_key: str) -> bytes:
    """从飞书消息中下载文件内容。"""
    headers = {"Authorization": f"Bearer {_get_token()}"}
    url = f"{FEISHU_DOMAIN}/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
    resp = requests.get(url, headers=headers, params={"type": "file"}, timeout=60)
    if resp.status_code != 200:
        detail = resp.text[:500] if resp.text else "(无响应体)"
        raise Exception(f"下载文件失败 HTTP {resp.status_code}: {detail}")
    return resp.content
