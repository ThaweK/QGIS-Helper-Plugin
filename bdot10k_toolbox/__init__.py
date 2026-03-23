"""BDOT10k Toolbox - Download, load, and style BDOT10k data from GUGiK."""


def classFactory(iface):
    from .plugin import BDOT10kToolbox
    return BDOT10kToolbox(iface)
