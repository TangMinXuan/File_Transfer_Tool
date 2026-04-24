import asyncio
import json
import os
import socket
import time
import uuid
from typing import Callable, Optional

from aiohttp import web

PORT = 8080
BROADCAST_ADDR = "192.168.31.255"


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.168.1.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class LanNode:
    def __init__(self):
        self.node_id = str(uuid.uuid4())
        self.my_ip = _get_local_ip()
        self.on_message_received: Optional[Callable[[dict], None]] = None

        self._udp_transport: Optional[asyncio.DatagramTransport] = None
        self._seen_msg_ids: set[str] = set()
        self._history: list[dict] = []  # 自己发送的消息历史

    async def start(self):
        """初始化：启动 HTTP 服务 + UDP 广播监听 + 发送 history_query"""
        # 1. 启动 HTTP 服务（文件下载）
        app = web.Application()
        app.router.add_get("/download", self.receive_http)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()

        # 2. 启动 UDP 广播监听
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self),
            local_addr=("0.0.0.0", PORT),
            allow_broadcast=True,
        )
        self._udp_transport = transport

        # 3. 上线后发送 history_query 广播
        await self.send_broadcast("history_query", request_id=str(uuid.uuid4()))

    async def send_broadcast(self, msg_type: str, **kwargs):
        """统一发送广播：chat / file_offer / history_query"""
        msg = {
            "type": msg_type,
            "msg_id": str(uuid.uuid4()),
            "sender_id": self.node_id,
            "sender_ip": self.my_ip,
            "ts": int(time.time() * 1000),
        }
        msg.update(kwargs)

        # 发送 UDP 广播
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self._udp_transport.sendto(data, (BROADCAST_ADDR, PORT))

        # 标记为已见 + 通知 UI + 记录历史
        self._seen_msg_ids.add(msg["msg_id"])
        if msg_type in ("chat", "file_offer"):
            if self.on_message_received:
                self.on_message_received(msg)
            self._history.append(msg)

    async def receive_broadcast(self, msg: dict):
        """统一接收广播：chat / file_offer / history_query / history_reply"""
        # 去重 + 过滤自己
        msg_id = msg.get("msg_id")
        if not msg_id or msg_id in self._seen_msg_ids:
            return
        if msg.get("sender_id") == self.node_id:
            return
        self._seen_msg_ids.add(msg_id)

        msg_type = msg.get("type")

        # 收到普通消息：通知 UI
        if msg_type in ("chat", "file_offer"):
            if self.on_message_received:
                self.on_message_received(msg)

        # 收到 history_query：回复自己的历史
        elif msg_type == "history_query":
            await self.send_broadcast(
                "history_reply",
                request_id=msg.get("request_id"),
                items=list(self._history),
            )

        # 收到 history_reply：展示别人的历史
        elif msg_type == "history_reply":
            items = msg.get("items", [])
            for item in items:
                if item.get("msg_id") in self._seen_msg_ids:
                    continue
                self._seen_msg_ids.add(item["msg_id"])
                if self.on_message_received:
                    self.on_message_received(item)

    async def receive_http(self, request: web.Request):
        """处理 HTTP 下载请求（直接用路径，参考 file_server 简洁写法）"""
        file_path = request.query.get("path")
        if file_path and os.path.exists(file_path):
            return web.FileResponse(file_path)
        else:
            return web.Response(status=404, text="文件已失效或被移动")


# ── 内部辅助：UDP 协议回调 ──────────────────────────────────────────────────
class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, node: LanNode):
        self.node = node

    def connection_made(self, transport):
        self.node._udp_transport = transport

    def datagram_received(self, data: bytes, _addr):
        try:
            msg = json.loads(data.decode("utf-8"))
            asyncio.create_task(self.node.receive_broadcast(msg))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
