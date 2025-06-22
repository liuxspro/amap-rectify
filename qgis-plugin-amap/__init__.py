from .plugin import AMAP


def classFactory(iface):
    """QGIS Plugin"""
    return AMAP(iface)
