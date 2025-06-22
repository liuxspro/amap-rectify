import json
import socket
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsMessageLog, Qgis

from .tile import get_tile, get_tile_async, close_async_client
from .utils import log_message

# AMAP服务器路由定义
# 注意：现在使用原生socket服务器，这些路由在plugin.py中直接处理

# 路由映射
ROUTES = {
    "/": "AMAP服务器运行正常！",
    "/test": "服务器测试成功！",
    "/status": {"status": "running", "message": "AMAP服务器正在运行"},
}


class AmapServer(QObject):
    """Bottle服务器 - 使用原生socket和QTimer"""

    def __init__(self, host="localhost", port=8080):
        super().__init__()
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.timer = None
        self.clients = []
        # 添加线程池用于异步处理
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.async_loop = None
        self.async_thread = None

    def start(self):
        """启动服务器"""
        if self.running:
            return True

        try:
            self.running = True
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.socket.setblocking(False)

            # 启动异步事件循环
            self.start_async_loop()

            # 创建定时器处理服务器操作
            self.timer = QTimer()
            self.timer.timeout.connect(self.process_server)
            self.timer.start(100)  # 100ms间隔

            log_message(f"AMAP服务器启动成功: http://{self.host}:{self.port}")
            return True

        except Exception as e:
            log_message(f"启动服务器失败: {str(e)}")
            self.stop()
            return False

    def start_async_loop(self):
        """启动异步事件循环"""
        def run_async_loop():
            self.async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.async_loop)
            self.async_loop.run_forever()
        
        self.async_thread = threading.Thread(target=run_async_loop, daemon=True)
        self.async_thread.start()

    def stop(self):
        """停止服务器"""
        self.running = False

        if self.timer:
            self.timer.stop()
            self.timer = None

        # 关闭所有客户端连接
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        self.clients.clear()

        # 停止异步事件循环
        if self.async_loop:
            self.async_loop.call_soon_threadsafe(self.async_loop.stop)
            if self.async_thread:
                self.async_thread.join(timeout=2)

        # 关闭线程池
        if self.thread_pool:
            self.thread_pool.shutdown(wait=False)

        # 关闭异步HTTP客户端
        if self.async_loop:
            try:
                future = asyncio.run_coroutine_threadsafe(close_async_client(), self.async_loop)
                future.result(timeout=2)
            except:
                pass

        if self.socket:
            self.socket.close()
            self.socket = None

        log_message("AMAP服务器已停止")

    def process_server(self):
        """处理服务器操作（由定时器调用）"""
        if not self.running or not self.socket:
            return

        try:
            # 接受新连接
            try:
                client, address = self.socket.accept()
                client.setblocking(False)
                self.clients.append(client)
                # QgsMessageLog.logMessage(f"客户端连接: {address}", "AMAP")
            except BlockingIOError:
                pass  # 没有等待的连接
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"接受连接时出错: {str(e)}", "AMAP", Qgis.Warning
                )

            # 处理现有连接
            for client in self.clients[:]:  # 使用副本进行迭代
                try:
                    # 尝试接收数据
                    try:
                        data = client.recv(8192)
                        if data:
                            # 处理HTTP请求
                            response = self.handle_http_request(data)
                            client.sendall(response)
                        else:
                            # 客户端断开连接
                            # QgsMessageLog.logMessage("客户端断开连接", "AMAP")
                            client.close()
                            self.clients.remove(client)
                    except BlockingIOError:
                        pass  # 没有可用数据
                    except Exception as e:
                        QgsMessageLog.logMessage(
                            f"接收数据时出错: {str(e)}", "AMAP", Qgis.Warning
                        )
                        client.close()
                        self.clients.remove(client)

                except Exception as e:
                    QgsMessageLog.logMessage(
                        f"处理客户端时出错: {str(e)}", "AMAP", Qgis.Warning
                    )
                    if client in self.clients:
                        self.clients.remove(client)
                    try:
                        client.close()
                    except:
                        pass

        except Exception as e:
            log_message(f"服务器错误: {str(e)}")

    def handle_http_request(self, data):
        """处理HTTP请求"""
        try:
            # 解析HTTP请求
            request = data.decode("utf-8")
            lines = request.split("\n")

            if not lines:
                return self.create_http_response("400 Bad Request", "Invalid request")

            # 解析请求行
            request_line = lines[0].strip()
            parts = request_line.split()
            if len(parts) < 2:
                return self.create_http_response(
                    "400 Bad Request", "Invalid request line"
                )

            method = parts[0]
            path = parts[1]

            # 简单的路由处理
            if path == "/":
                return self.create_http_response("200 OK", "AMAP服务器运行正常！")
            elif path == "/test":
                return self.create_http_response("200 OK", "服务器测试成功！")
            elif path == "/status":
                status_data = {"status": "running", "message": "AMAP服务器正在运行"}
                return self.create_http_response(
                    "200 OK", json.dumps(status_data), "application/json"
                )
            elif path.startswith("/tile/amap/"):
                # 处理瓦片请求 /tile/amap/<mapid>/<z>/<x>/<y>
                return self.handle_tile_request(path)
            else:
                return self.create_http_response("404 Not Found", "页面未找到")

        except Exception as e:
            QgsMessageLog.logMessage(
                f"处理HTTP请求时出错: {str(e)}", "AMAP", Qgis.Warning
            )
            return self.create_http_response(
                "500 Internal Server Error", "服务器内部错误"
            )

    def handle_tile_request(self, path):
        """处理瓦片请求 /tile/amap/<mapid>/<z>/<x>/<y>"""
        try:
            # 解析路径 /tile/amap/<mapid>/<z>/<x>/<y>
            path_parts = path.split("/")
            if len(path_parts) != 7:  # /tile/amap/mapid/z/x/y
                return self.create_http_response("400 Bad Request", "Invalid tile path")
            mapid = path_parts[3]
            z = path_parts[4]  # 缩放级别
            x = path_parts[5]  # X坐标
            y = path_parts[6]  # Y坐标

            # 验证参数是否为数字
            try:
                z_int = int(z)
                x_int = int(x)
                y_int = int(y)
            except ValueError:
                return self.create_http_response(
                    "400 Bad Request", "Invalid tile coordinates"
                )

            # 使用异步方式获取瓦片图片
            try:
                # 在线程池中运行异步瓦片获取
                future = self.thread_pool.submit(self._get_tile_async, x_int, y_int, z_int, mapid)
                image = future.result(timeout=30)  # 30秒超时
                
                if image:
                    # 将PIL Image转换为PNG字节数据
                    img_buffer = BytesIO()
                    image.save(img_buffer, format="PNG")
                    image_data = img_buffer.getvalue()
                    img_buffer.close()

                    # 返回图片数据
                    return self.create_image_response("200 OK", image_data, "image/png")
                else:
                    return self.create_http_response("404 Not Found", "瓦片不存在")
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"获取瓦片图片失败: {str(e)}", "AMAP", Qgis.Warning
                )
                return self.create_http_response(
                    "500 Internal Server Error", "瓦片获取失败"
                )

        except Exception as e:
            QgsMessageLog.logMessage(
                f"处理瓦片请求时出错: {str(e)}", "AMAP", Qgis.Warning
            )
            return self.create_http_response(
                "500 Internal Server Error", "瓦片处理错误"
            )

    def _get_tile_async(self, x: int, y: int, z: int, mapid: str):
        """在线程中运行异步瓦片获取"""
        if self.async_loop:
            future = asyncio.run_coroutine_threadsafe(
                get_tile_async(x, y, z, mapid), self.async_loop
            )
            return future.result(timeout=30)
        else:
            # 如果异步循环不可用，回退到同步方式
            return get_tile(x, y, z, mapid)

    def create_image_response(self, status, image_data, content_type="image/png"):
        """创建图片HTTP响应"""
        response = f"""HTTP/1.1 {status}
Content-Type: {content_type}
Content-Length: {len(image_data)}
Cache-Control: public, max-age=3600
Connection: close

"""
        # 返回响应头 + 图片数据
        return response.encode("utf-8") + image_data

    def create_http_response(
        self, status, body, content_type="text/html; charset=utf-8"
    ):
        """创建HTTP响应"""
        response = f"""HTTP/1.1 {status}
Content-Type: {content_type}
Content-Length: {len(body.encode('utf-8'))}
Connection: close

{body}"""
        return response.encode("utf-8")
