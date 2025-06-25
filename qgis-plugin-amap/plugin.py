from urllib.parse import quote

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .server import ServerManager, app
from .tile import amap_name
from .utils import PluginDir, add_raster_layer, log_message


def add_map(mapid):
    map_url = f"http://localhost:8080/tile/amap/{mapid}/{{z}}/{{x}}/{{y}}"
    map_name = amap_name[mapid]
    # URL编码处理
    encoded_url = quote(map_url, safe=":/?=")
    uri = f"type=xyz&url={encoded_url}&zmax=18&zmin=2"
    add_raster_layer(uri, f"高德地图 - {map_name}")


class AMAP:
    def __init__(self, iface):
        self.iface = iface
        self.server = ServerManager(app, port=8080)
        # 添加动作列表
        self.actions = []
        self.start_action = None
        self.add_map_cations = []
        self.stop_action = None
        # 添加菜单
        self.menu = None

    def initGui(self):
        """创建菜单项和工具栏图标"""
        log_message("初始化AMAP插件...")

        # 创建菜单
        self.menu = self.iface.mainWindow().menuBar().addMenu("&AMAP")

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

        # 添加地图 Action
        amap_icon = QIcon(str(PluginDir / "images" / "amap.svg"))
        for mapid in amap_name:
            action = QAction(
                amap_icon, f"高德地图 - {amap_name[mapid]}", self.iface.mainWindow()
            )
            action.triggered.connect(lambda checked, mid=mapid: add_map(mid))
            self.add_map_cations.append(action)

        for action in self.add_map_cations:
            self.actions.append(action)
            self.menu.addAction(action)

        # 添加动作到工具栏
        # self.iface.addToolBarIcon(self.start_action)
        # self.iface.addToolBarIcon(self.stop_action)

        # 初始状态：启动按钮可用，停止按钮不可用
        self.stop_action.setEnabled(False)
        for action in self.add_map_cations:
            action.setEnabled(False)

        log_message("AMAP插件初始化完成")

    def start_server(self):
        if self.server.start():
            log_message("✅ 服务器启动成功！")
            log_message(
                f"🌐 可以访问以下地址：http://localhost:{self.server.port}/docs",
            )
            # 更新UI状态
            self.start_action.setEnabled(False)
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
            for action in self.add_map_cations:
                action.setEnabled(False)
            log_message("✅ 服务器已停止")

    def unload(self):
        """从QGIS界面卸载插件"""
        log_message("卸载AMAP插件...")

        # 停止服务器
        self.stop_server()

        # 移除菜单
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())

        # 移除工具栏图标
        for action in self.actions:
            self.iface.removeToolBarIcon(action)

        print("AMAP插件已卸载")
