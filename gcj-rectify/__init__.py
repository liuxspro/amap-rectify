try:
    from .plugin import GCJRectifyPlugin
except ImportError as e:
    GCJRectifyPlugin = None
    print(f"Not in QGIS ({e})")


def classFactory(iface):
    """QGIS Plugin"""
    return GCJRectifyPlugin(iface)
