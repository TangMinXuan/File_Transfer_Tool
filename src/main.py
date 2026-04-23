import asyncio
import os
import flet as ft
from flet import Padding

from lan_discovery import LanNode


async def main(page: ft.Page):
    page.title = "极速局域网快传"
    node = LanNode()

    # ── UI 组件 ──────────────────────────────────────────────────────────────────
    status_badge = ft.Text("⏳ 启动中...", size=13, color=ft.Colors.GREY_600)
    chat_list = ft.ListView(expand=True, spacing=10)
    input_box = ft.TextField(hint_text="输入消息...", expand=True)

    # ── 文件选择与发送 ────────────────────────────────────────────────────────────
    def on_file_picker_result(files):
        print("DEBUG: on_file_picker_result triggered with files:", files)
        if not files:
            chat_list.controls.append(ft.Text("未选择文件"))
            page.update()
            return

        for f in files:
            try:
                if not f.path:
                    chat_list.controls.append(ft.Text(f"跳过: {f.name} (无本地路径)"))
                    continue

                size = os.path.getsize(f.path)
                asyncio.create_task(
                    node.send_broadcast(
                        "file_offer",
                        path=f.path,
                        name=f.name,
                        size=size,
                    )
                )
                chat_list.controls.append(ft.Text(f"已发送文件广播: {f.name}"))
            except Exception as ex:
                chat_list.controls.append(ft.Text(f"文件发送失败: {f.name}, {ex}"))

        page.update()

    file_picker = ft.FilePicker()
    # file_picker.on_result = on_file_picker_result
    if hasattr(page, "services"):
        page.services.append(file_picker)
    else:
        page.overlay.append(file_picker)

    async def pick_and_send(_):
        files = await file_picker.pick_files(allow_multiple=True)
        on_file_picker_result(files)

    async def send_text():
        text = input_box.value.strip()
        if not text:
            return
        input_box.value = ""
        page.update()
        await node.send_broadcast("chat", text=text)

    def on_send_click(_):
        asyncio.create_task(send_text())

    def on_message_received(msg: dict):
        if msg.get("type") == "file_offer":
            name = msg.get("name", "未知文件")
            size_kb = msg.get("size", 0) // 1024
            sender_ip = msg.get("sender_ip", "?")
            file_path = msg.get("path")
            
            # 构造下载 URL（直接用路径）
            download_url = f"http://{sender_ip}:8080/download?path={file_path}"
            chat_list.controls.append(
                ft.Row([
                    ft.Icon(ft.Icons.ATTACH_FILE),
                    ft.Text(f"📁 {name} ({size_kb} KB) 来自 {sender_ip}"),
                    ft.TextButton("下载", url=download_url),
                ])
            )
            page.update()
        elif msg.get("type") == "chat":
            sender = "我" if msg.get("sender_id") == node.node_id else msg.get("sender_ip", "?")
            text = msg.get("text", "")
            chat_list.controls.append(ft.Text(f"[{sender}] {text}"))
            page.update()

    node.on_message_received = on_message_received

    # ── 构建页面 ─────────────────────────────────────────────────────────────────
    page.add(
        ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.WIFI, size=16), status_badge]),
            ]),
            padding=Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=ft.Colors.BLUE_GREY_50,
            border_radius=8,
        ),
        ft.Divider(height=1),
        chat_list,
        ft.Row([
            input_box,
            ft.IconButton(icon=ft.Icons.SEND, on_click=on_send_click),
            ft.IconButton(icon=ft.Icons.ATTACH_FILE, on_click=pick_and_send),
        ]),
    )
    input_box.on_submit = on_send_click

    # ── 启动节点 ──────────────────────────────────────────────────────────────────
    await node.start()
    status_badge.value = f"🟢 广播模式已启动  {node.my_ip}:{8080}"
    status_badge.color = ft.Colors.GREEN_700
    page.update()


ft.run(main)
