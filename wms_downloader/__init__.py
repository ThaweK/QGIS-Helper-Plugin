"""
WMS/WMTS Layer Downloader - QGIS Plugin
Downloads WMS/WMTS layers to local GeoTIFF at a chosen zoom level.
"""

def classFactory(iface):
    from .plugin import WmsDownloaderPlugin
    return WmsDownloaderPlugin(iface)
