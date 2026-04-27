"""QGIS Plugin Helper — unified entry point for all helper tools."""


def classFactory(iface):
    from .plugin import QgisPluginHelper
    return QgisPluginHelper(iface)
