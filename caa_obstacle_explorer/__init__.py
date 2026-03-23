"""CAA-PL Obstacle Explorer - Download aviation obstacle data from Polish CAA ArcGIS services."""


def classFactory(iface):
    from .plugin import CAAObstacleExplorer
    return CAAObstacleExplorer(iface)
