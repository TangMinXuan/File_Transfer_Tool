from aiohttp import web
import os


async def handle_download(request):
    print("收到下载请求:", request.query)
    file_path = request.query.get('path')

    if file_path and os.path.exists(file_path):
        return web.FileResponse(file_path) # aiohttp 自带的 FileResponse 会自动处理大文件分块传输，不会撑爆内存！
    else:
        return web.Response(status=404, text="文件已失效或被移动")


async def start_file_server(port=8080):
    app = web.Application()
    app.add_routes([web.get('/download', handle_download)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"文件服务器已启动: http://0.0.0.0:{port}")