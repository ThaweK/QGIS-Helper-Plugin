"""Fix the KOD10K rendering bug in BDOT10k layers.

The GUGiK BDOT10k_GML_SHP plugin applies QML styles that classify on 'KOD10K',
but in publicly distributed GML files that field is always NULL.
The actual kartographic code lives in 'x_kodKarto10k'.
"""

from qgis.core import (
    QgsProject,
    QgsCategorizedSymbolRenderer,
)

try:
    from qgis.core import QgsPointClusterRenderer
    HAS_CLUSTER = True
except ImportError:
    HAS_CLUSTER = False


def fix_layer_renderer(layer):
    """Fix a single layer's renderer from KOD10K to x_kodKarto10k.

    Returns True if a fix was applied.
    """
    renderer = layer.renderer()
    if renderer is None:
        return False

    fixed = False

    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        if renderer.classAttribute() == 'KOD10K':
            if layer.fields().indexOf('x_kodKarto10k') >= 0:
                renderer.setClassAttribute('x_kodKarto10k')
                layer.triggerRepaint()
                fixed = True

    if HAS_CLUSTER and isinstance(renderer, QgsPointClusterRenderer):
        embedded = renderer.embeddedRenderer()
        if isinstance(embedded, QgsCategorizedSymbolRenderer):
            if embedded.classAttribute() == 'KOD10K':
                if layer.fields().indexOf('x_kodKarto10k') >= 0:
                    embedded.setClassAttribute('x_kodKarto10k')
                    renderer.setEmbeddedRenderer(embedded)
                    layer.triggerRepaint()
                    fixed = True

    return fixed


def fix_all_layers():
    """Scan all project layers and fix KOD10K renderers.

    Returns count of fixed layers.
    """
    count = 0
    for layer in QgsProject.instance().mapLayers().values():
        if fix_layer_renderer(layer):
            count += 1
    return count
