from pathlib import Path
from urllib.parse import quote

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QHBoxLayout,
    QFileDialog,
    QSpinBox,
)
from qgis.core import QgsSettings

from .app.main import app
from .app.rectify import map_data
from .app.fetch import close_async_client
from .server import ServerManager

from .qgis_utils import PluginDir, add_raster_layer, log_message, CACHE_DIR


def add_map(port, mapid):
    map_url = f"http://localhost:{port}/tiles/{mapid}/{{z}}/{{x}}/{{y}}"
    map_name = map_data[mapid]
    # URL编码处理
    encoded_url = quote(map_url, safe=":/?=")
    uri = f"type=xyz&url={encoded_url}&zmin=3&zmax=18"
    add_raster_layer(uri, map_name["name"])


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conf = QgsSettings()
        self.port = self.conf.value("gcj-rectify/port", 8080, type=int)
        self.cache_dir = self.conf.value("gcj-rectify/cache_dir", str(CACHE_DIR))
        self.setWindowTitle("设置")
        self.setMinimumWidth(600)
        layout = QVBoxLayout()

        # 端口设置
        port_layout = QHBoxLayout()
        port_label = QLabel("端口：")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.get_port())
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_spin)
        layout.addLayout(port_layout)

        # 缓存目录设置
        cache_layout = QHBoxLayout()
        cache_label = QLabel("缓存目录：")
        self.cache_edit = QLineEdit(self.get_cache_dir())
        self.cache_edit.setPlaceholderText("请选择缓存目录")
        cache_btn = QPushButton("选择...")
        cache_btn.clicked.connect(self.choose_cache_dir)
        cache_layout.addWidget(cache_label)
        cache_layout.addWidget(self.cache_edit)
        cache_layout.addWidget(cache_btn)
        layout.addLayout(cache_layout)

        # 确认和关闭按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def choose_cache_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择缓存目录", "")
        if dir_path:
            self.cache_edit.setText(dir_path)

    def accept(self):
        super().accept()
        self.conf.setValue("gcj-rectify/port", self.port_spin.value())
        self.conf.setValue("gcj-rectify/cache_dir", self.cache_edit.text())
        log_message(
            f"设置已保存: 端口={self.port_spin.value()}, 缓存目录={self.cache_edit.text()}"
        )

    def get_port(self):
        return self.conf.value("gcj-rectify/port", 8080, type=int)

    def get_cache_dir(self):
        return self.conf.value("gcj-rectify/cache_dir", str(CACHE_DIR), type=str)

    def get_settings(self):
        return {
            "port": self.port_spin.value(),
            "cache_dir": self.cache_edit.text(),
        }


class GCJRectifyPlugin:
    def __init__(self, iface):
        self.settings_action = None
        self.conf = QgsSettings()
        self.app = app
        self.port = self.get_port()
        self.iface = iface
        self.server = ServerManager(self.app, port=self.port)
        # 添加动作列表
        self.actions = []
        self.start_action = None
        self.add_map_cations = []
        self.stop_action = None

        # 添加菜单
        self.menu = None

    def initGui(self):
        self.init_config()
        # 创建菜单
        self.menu = self.iface.mainWindow().menuBar().addMenu("&GCJ-Rectify")

        # 启动服务 Action
        icon = QIcon(str(PluginDir / "images" / "start.svg"))
        self.start_action = QAction(icon, "启动服务器", self.iface.mainWindow())
        self.start_action.triggered.connect(self.start_server)

        self.actions.append(self.start_action)

        # 停止服务 Action
        self.stop_action = QAction(
            QIcon(str(PluginDir / "images" / "stop.svg")),
            "停止服务器",
            self.iface.mainWindow(),
        )
        self.stop_action.triggered.connect(self.stop_server)
        self.actions.append(self.stop_action)

        # 添加 Action 到菜单
        self.menu.addAction(self.start_action)
        self.menu.addAction(self.stop_action)
        self.menu.addSeparator()

        # 设置 Action
        self.settings_action = QAction(QIcon(), "设置", self.iface.mainWindow())
        self.settings_action.triggered.connect(self.show_settings_dialog)
        self.actions.append(self.settings_action)
        self.menu.addAction(self.settings_action)
        self.menu.addSeparator()

        # 添加地图 Action
        amap_icon = QIcon(str(PluginDir / "images" / "amap.svg"))
        for mapid in map_data.keys():
            action = QAction(
                amap_icon, map_data[mapid]["name"], self.iface.mainWindow()
            )
            action.triggered.connect(
                lambda checked, mid=mapid: add_map(self.get_port(), mid)
            )
            self.add_map_cations.append(action)

        for action in self.add_map_cations:
            self.actions.append(action)
            self.menu.addAction(action)

        # 初始状态：启动按钮可用，停止按钮不可用
        self.stop_action.setEnabled(False)
        for action in self.add_map_cations:
            action.setEnabled(False)

        log_message(
            f"GCJ-Rectify 插件初始化完成 端口: {self.port} 缓存目录: {self.get_cache_dir()}"
        )

    def init_config(self):
        log_message("初始化 GCJRectifyPlugin 插件...")
        if not self.conf.contains("gcj-rectify/port"):
            log_message("初始化配置文件")
            self.conf.setValue("gcj-rectify/port", 8080)
            self.conf.setValue("gcj-rectify/cache_dir", str(CACHE_DIR))

    def get_port(self):
        """获取当前端口"""
        return self.conf.value("gcj-rectify/port", 8080, type=int)

    def get_cache_dir(self):
        """获取当前缓存目录"""
        return self.conf.value("gcj-rectify/cache_dir", str(CACHE_DIR), type=str)

    def start_server(self):
        self.app.state.cache_dir = Path(self.get_cache_dir())
        self.server.port = self.get_port()
        self.server.cache_dir = self.conf.value("gcj-rectify/cache_dir", str(CACHE_DIR))
        if self.server.start():
            log_message("✅ 服务器启动成功！")
            log_message(f"📦 缓存目录 {self.server.app.state.cache_dir}")
            log_message(
                f"🌐 API 文档地址：http://localhost:{self.server.port}/docs",
            )
            # 更新UI状态
            self.start_action.setEnabled(False)
            self.settings_action.setEnabled(False)
            self.stop_action.setEnabled(True)
            for action in self.add_map_cations:
                action.setEnabled(True)
        else:
            log_message("❌ 服务器启动失败")

    def stop_server(self):
        if self.server.stop():
            # 更新UI状态
            self.start_action.setEnabled(True)
            self.stop_action.setEnabled(False)
            self.settings_action.setEnabled(True)
            for action in self.add_map_cations:
                action.setEnabled(False)
            log_message("✅ 服务器已停止")
            close_async_client()

    def show_settings_dialog(self):
        # 默认值可根据实际情况传递
        dlg = SettingsDialog(self.iface.mainWindow())
        if dlg.exec_():
            settings = dlg.get_settings()
            log_message(
                f"设置已更新: 端口={settings['port']}, 缓存目录={settings['cache_dir']}"
            )

    def unload(self):
        """从QGIS界面卸载插件"""
        log_message("卸载 GCJ-Rectify 插件...")

        # 停止服务器
        self.stop_server()

        # 移除菜单
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())

        # 移除工具栏图标
        for action in self.actions:
            self.iface.removeToolBarIcon(action)

        log_message("GCJ-Rectify 插件已卸载")
