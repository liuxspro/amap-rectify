import threading
import time
from typing import Optional

from fastapi import FastAPI
from uvicorn import Server, Config

from .qgis_utils import log_message


class ServerManager:
    def __init__(self, _app: FastAPI, host: str = "0.0.0.0", port: int = 8080):
        self.app = _app
        self.host = host
        self.port = port
        self.server: Optional[Server] = None
        self.server_thread: Optional[threading.Thread] = None
        self._is_running = False

    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self._is_running and self.server_thread and self.server_thread.is_alive()

    def start(self) -> bool:
        # 如果服务器已在运行，先停止
        if self.is_running():
            self.stop()

        try:
            # 创建服务器配置
            config = Config(
                app=self.app,
                host=self.host,
                port=self.port,
                lifespan="on",
                log_config=None,
            )
            self.server = Server(config)

            # 创建并启动服务器线程
            self.server_thread = threading.Thread(target=self._run_server)
            self.server_thread.daemon = True
            self.server_thread.start()

            # 等待服务器启动（最多5秒）
            start_time = time.time()
            while not self._is_running and (time.time() - start_time) < 5:
                time.sleep(0.1)

            if self._is_running:
                return True
            else:
                return False
        except Exception as e:
            log_message(f"Error: {e}")
            return False

    def _run_server(self):
        """内部方法：运行服务器"""
        try:
            self._is_running = True
            # 确保在新线程中有新的事件循环
            self.server.run()
        except Exception as e:
            print(f"🚨 Server crashed: {str(e)}")
        finally:
            self._is_running = False

    def stop(self, timeout: float = 5.0) -> bool | None:
        if not self.is_running():
            return False

        try:
            # 通知服务器退出
            if self.server:
                self.server.should_exit = True

            # 等待线程结束
            if self.server_thread:
                self.server_thread.join(timeout=timeout)

            # 如果线程仍然存活，强制终止
            if self.server_thread and self.server_thread.is_alive():
                if self.server:
                    self.server.force_exit = True
                self.server_thread.join(timeout=1.0)
                # 最后尝试强制终止
                if self.server_thread.is_alive():
                    return False
            return True
        except Exception as e:
            print(f"Error: {e}")
            return False
        finally:
            # 清理资源
            self.server = None
            self.server_thread = None
            self._is_running = False
