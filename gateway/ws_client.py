"""
飞书 WebSocket 客户端 — 长连接 + protobuf 编解码 + 事件分发到 Agent。
核心逻辑与三个已有 Bot 一致，差异在于 dispatch 接入 Agent 而非固定 handler。
"""
import asyncio
import concurrent.futures
import inspect
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests
import websockets

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_DOMAIN, WS_ENDPOINT_URI, LOG_LEVEL, LOG_FILE,
)
from gateway.feishu_api import send_text, send_file, download_file_from_message

log = logging.getLogger("gateway")
log.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

# ── Protobuf 编解码（飞书 WS 帧格式）──

def _pb_varint(buf: bytearray, n: int):
    while n > 127:
        buf.append((n & 0x7F) | 0x80)
        n >>= 7
    buf.append(n & 0x7F)


def _pb_tag(buf: bytearray, field: int, wire: int):
    _pb_varint(buf, (field << 3) | wire)


def _pb_string(buf: bytearray, field: int, value: str):
    _pb_tag(buf, field, 2)
    encoded = value.encode("utf-8")
    _pb_varint(buf, len(encoded))
    buf.extend(encoded)


def _pb_uint64(buf: bytearray, field: int, value: int):
    _pb_tag(buf, field, 0)
    _pb_varint(buf, value)


def _pb_int32(buf: bytearray, field: int, value: int):
    _pb_tag(buf, field, 0)
    _pb_varint(buf, value)


def encode_ping(service_id: int) -> bytes:
    buf = bytearray()
    h = bytearray()
    _pb_string(h, 1, "type")
    _pb_string(h, 2, "ping")
    _pb_int32(buf, 4, 0)
    _pb_uint64(buf, 2, 0)
    _pb_uint64(buf, 1, 0)
    _pb_tag(buf, 3, 0)
    _pb_varint(buf, service_id)
    _pb_tag(buf, 5, 2)
    _pb_varint(buf, len(h))
    buf.extend(h)
    return bytes(buf)


def decode_frame(data: bytes) -> dict:
    """解析飞书 WS 二进制帧，提取 field 4(帧类型) 和 field 8(payload)。"""
    result = {}
    pos = 0
    while pos < len(data):
        tag = data[pos]; pos += 1
        field = tag >> 3
        wire = tag & 0x07
        if wire == 0:
            value = shift = 0
            while pos < len(data):
                b = data[pos]; pos += 1
                value |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            result[field] = value
        elif wire == 2:
            length = shift = 0
            while pos < len(data):
                b = data[pos]; pos += 1
                length |= (b & 0x7F) << shift
                if not (b & 0x80): break
                shift += 7
            result[field] = data[pos:pos + length]
            pos += length
        elif wire == 1:
            pos += 8
        elif wire == 5:
            pos += 4
        else:
            break
    return result


# ── 消息去重 ──

_SEEN_FILE = Path(__file__).parent.parent / ".seen_msg_ids"
_SEEN_MAX = 500
_SEEN_KEEP = 300
_seen: set[str] | None = None
_seen_lock = threading.RLock()


def _init_seen():
    global _seen
    _seen = set()
    if _SEEN_FILE.exists():
        with open(_SEEN_FILE, "r") as f:
            for line in f:
                s = line.strip()
                if s:
                    _seen.add(s)


def _is_duplicate(msg_id: str) -> bool:
    global _seen
    with _seen_lock:
        if _seen is None:
            _init_seen()
        if msg_id in _seen:
            return True
        _seen.add(msg_id)
        with open(_SEEN_FILE, "a") as f:
            f.write(msg_id + "\n")
        if len(_seen) > _SEEN_MAX:
            with open(_SEEN_FILE, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            _seen = set(lines[-_SEEN_KEEP:])
            with open(_SEEN_FILE, "w") as f:
                for line in lines[-_SEEN_KEEP:]:
                    f.write(line + "\n")
        return False


# ── FeishuWsClient ──

class FeishuWsClient:
    """飞书 WebSocket 长连接客户端。"""

    def __init__(self, agent):
        self._agent = agent
        self._service_id = ""
        self._reconnect_interval = 120
        self._ping_interval = 120
        self._ws = None
        self._ping_task = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    def _get_ws_url(self) -> str:
        resp = requests.post(
            f"{FEISHU_DOMAIN}{WS_ENDPOINT_URI}",
            headers={"locale": "zh"},
            json={"AppID": FEISHU_APP_ID, "AppSecret": FEISHU_APP_SECRET},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"获取 WS 地址失败: {data}")
        dd = data.get("data", {})
        if dd.get("ClientConfig"):
            cc = dd["ClientConfig"]
            self._reconnect_interval = cc.get("ReconnectInterval", 120)
            self._ping_interval = cc.get("PingInterval", 120)
        return dd["URL"]

    async def _ping_loop(self):
        while True:
            try:
                if self._ws is not None:
                    sid = int(self._service_id) if self._service_id else 0
                    await self._ws.send(encode_ping(sid))
            except Exception:
                pass
            await asyncio.sleep(self._ping_interval)

    # ── 事件分发 ──

    def _dispatch(self, event_data: dict):
        """在独立线程中处理事件 → 调用 Agent → 回复。"""
        try:
            event = event_data.get("event", {})
            header = event_data.get("header", {})
            event_type = header.get("event_type", event.get("type", "?"))
            msg = event.get("message", {})
            msg_id = msg.get("message_id", "")
            msg_type = msg.get("message_type", "?")

            log.info(f"[事件] type={event_type} msg_type={msg_type} msg_id={msg_id[:8]}...")

            if _is_duplicate(msg_id):
                log.info("[事件] 重复消息，跳过")
                return

            # 跳过过旧消息（>180s）
            ct = msg.get("create_time", "")
            if ct:
                try:
                    age = time.time() - int(ct) / 1000
                    if age > 180:
                        log.info(f"[事件] 消息过旧({age:.0f}s)，跳过")
                        return
                except (ValueError, OSError):
                    pass

            # 跳过 app 自己的消息
            sender = event.get("sender", {})
            if sender.get("sender_type") == "app":
                log.info("[事件] 来自 app，跳过")
                return

            chat_id = msg.get("chat_id", "")
            user_id = sender.get("sender_id", {}).get("open_id", "unknown")

            content_str = msg.get("content", "{}")
            try:
                content = json.loads(content_str)
            except json.JSONDecodeError:
                content = {}

            # ── 文本消息 ──
            if msg_type == "text":
                text = content.get("text", "")
                if not text:
                    log.info("[事件] 空文本，跳过")
                    return
                # 去掉 @机器人 前缀
                original = text
                text = re.sub(r'@\S+\s*', '', text).strip()
                if not text:
                    log.info(f"[事件] 仅@机器人无内容: {original[:80]}")
                    # 仅 @ 了机器人但没说话，给个引导
                    send_text(chat_id, "你好！我是数据处理助手，可以帮你：\n1) 清洗影院数据\n2) 预测影片落位\n3) 提取开场数据\n\n直接告诉我需求即可~")
                    return

                log.info(f"[消息] user={user_id[:12]} text={text[:80]}")
                response = self._agent.handle_message(user_id, chat_id, text)
                self._send_response(chat_id, response)
                if response.get("_deferred"):
                    result = self._agent.execute_deferred(user_id)
                    self._send_response(chat_id, result)
                return

            # ── 文件消息 ──
            if msg_type == "file":
                file_key = content.get("file_key", "")
                file_name = content.get("file_name", "")
                log.info(f"[文件] name={file_name} key={file_key[:20]}...")
                if not file_name.lower().endswith(('.xlsx', '.xls')):
                    log.info(f"[文件] 非Excel: {file_name}")
                    return

                try:
                    file_bytes = download_file_from_message(msg_id, file_key)
                except Exception as e:
                    log.error(f"下载文件失败: {e}")
                    send_text(chat_id, f"文件下载失败: {e}")
                    return

                files = [(file_name, file_bytes)]
                response = self._agent.handle_message(user_id, chat_id, "", files)
                self._send_response(chat_id, response)
                if response.get("_deferred"):
                    result = self._agent.execute_deferred(user_id)
                    self._send_response(chat_id, result)
                return

            # 非文本非文件消息
            log.info(f"[事件] 不支持的消息类型: {msg_type}，跳过")

        except Exception:
            log.error(f"[分发异常] {traceback.format_exc()[-500:]}")

    def _send_response(self, chat_id: str, response: dict):
        """将 Agent 返回的 response dict 发送到飞书。"""
        text = response.get("text", "")
        extra_text = response.get("extra_text", "")
        files = response.get("files", [])

        def _send_text_safe(msg: str):
            """发送单条文本，超长则分段。"""
            if not msg:
                return
            if len(msg) > 8000:
                parts = [msg[i:i+8000] for i in range(0, len(msg), 8000)]
                for part in parts:
                    try:
                        send_text(chat_id, part)
                    except Exception as e:
                        log.error(f"发送文本失败: {e}")
                    time.sleep(0.3)
            else:
                try:
                    send_text(chat_id, msg)
                except Exception as e:
                    log.error(f"发送文本失败: {e}")

        _send_text_safe(text)
        if extra_text:
            time.sleep(0.5)  # 两条消息之间稍作停顿
            _send_text_safe(extra_text)

        for fpath in files:
            if os.path.exists(fpath):
                fname = os.path.basename(fpath)
                try:
                    send_file(chat_id, fpath, fname)
                    time.sleep(0.3)
                except Exception as e:
                    log.error(f"发送文件失败 {fname}: {e}")
                finally:
                    # 清理临时文件，避免磁盘泄漏
                    try:
                        os.remove(fpath)
                        # 如果父目录是空的临时目录，也一并清理
                        parent = os.path.dirname(fpath)
                        if os.path.isdir(parent) and not os.listdir(parent):
                            os.rmdir(parent)
                    except OSError:
                        pass

    def _dispatch_sync(self, event_data: dict):
        """同步包装，供 executor 调用。"""
        try:
            self._dispatch(event_data)
        except Exception:
            log.error(f"[dispatch 异常] {traceback.format_exc()[-300:]}")

    async def _process(self, event_data: dict):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._dispatch_sync, event_data)

    # ── 连接管理 ──

    async def _read_loop(self):
        while True:
            try:
                raw = await self._ws.recv()
                if isinstance(raw, str):
                    continue
                frame = decode_frame(raw)
                ft = frame.get(4, -1)
                if ft == 0:
                    continue
                elif ft == 1:
                    payload = frame.get(8, b"")
                    if not payload:
                        continue
                    event_data = json.loads(payload.decode("utf-8"))
                    asyncio.create_task(self._process(event_data))
            except websockets.exceptions.ConnectionClosed:
                log.warning("WebSocket 断开")
                break
            except Exception:
                log.error(f"[读取异常] {traceback.format_exc()[-200:]}")
                break

    async def _try_connect(self):
        url = self._get_ws_url()
        q = parse_qs(urlparse(url).query)
        self._service_id = q.get("service_id", [""])[0]
        log.info(f"WS 连接中... service_id={self._service_id}")

        params = inspect.signature(websockets.connect).parameters
        kwargs = {"proxy": None} if "proxy" in params else {}
        self._ws = await websockets.connect(url, **kwargs)
        log.info("WS 已连接 ✓")
        self._ping_task = asyncio.create_task(self._ping_loop())
        await self._read_loop()

    async def connect(self):
        while True:
            try:
                await self._try_connect()
            except Exception as e:
                log.error(f"连接失败: {e}")
            if self._ws:
                try: await self._ws.close()
                except Exception: pass
                self._ws = None
            if self._ping_task:
                self._ping_task.cancel()
                self._ping_task = None
            log.info(f"{self._reconnect_interval}s 后重连...")
            await asyncio.sleep(self._reconnect_interval)

    def start(self):
        asyncio.run(self.connect())
