"""Load BDOT10k GML/XML files into QGIS and apply styling."""

import os
import glob as glob_mod

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsLayerTreeGroup,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsSymbol,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsSettings,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QApplication

from .style_fixer import fix_layer_renderer

# Layer drawing order (bottom to top)
LAYER_ORDER = [
    "OT_PTUT_A", "OT_PTNZ_A", "OT_PTGN_A", "OT_PTSO_A", "OT_PTWZ_A",
    "OT_PTPL_A", "OT_PTZB_A", "OT_PTTR_A", "OT_PTKM_A",
    "OT_TCON_A", "OT_TCPK_A", "OT_TCPN_A", "OT_TCRZ_A",
    "OT_KUKO_A", "OT_KUHU_A", "OT_KUSC_A", "OT_KUZA_A",
    "OT_PTRK_A", "OT_PTLZ_A", "OT_PTWP_A",
    "OT_ZBIORNIKWODNY",
    "OT_SWRM_L", "OT_SWKN_L", "OT_SWRS_L",
    "OT_CIEK",
    "OT_OIOR_L", "OT_OIMK_A",
    "OT_SULN_L", "OT_SUPR_L",
    "OT_SKJZ_L", "OT_SKDR_L", "OT_SKRP_L",
    "OT_SZLAKDROGOWY", "OT_ULICA",
    "OT_SKTR_L", "OT_SKPP_L",
    "OT_LINIAKOLEJOWA", "OT_WEZELKOLEJOWY",
    "OT_BUIN_L", "OT_BUIN_A",
    "OT_BUBD_A", "OT_BUSP_A", "OT_BUWT_A", "OT_BUZT_A",
    "OT_BUBD_P", "OT_BUSP_P", "OT_BUWT_P",
    "OT_BUBD_L", "OT_BUSP_L",
    "OT_OIKM_P", "OT_OIPR_P",
    "OT_ADMS_A", "OT_ADJA_A",
    "OT_LOTNISKO", "OT_ELEKTROWNIA", "OT_KOPALNIA", "OT_PORT",
]

# Topo 1:10,000 color palette
COLORS = {
    'water_fill': '#b8deff',
    'water_line': '#4488cc',
    'water_label': '#1a5599',
    'forest_fill': '#c8e6a0',
    'forest_line': '#6ca040',
    'shrub': '#d8e8c8',
    'park': '#d8eecc',
    'built_up': '#f0ece4',
    'building': '#1a1a1a',
    'road_motorway': '#d43030',
    'road_primary': '#e08848',
    'road_secondary': '#f0d050',
    'road_local': '#ffffff',
    'road_casing': '#1a1a1a',
    'railway': '#1a1a1a',
    'boundary': '#1a1a1a',
}

# Fallback styles for layers without QML (layer_prefix -> style params)
FALLBACK_STYLES = {
    'OT_PTLZ': {'type': 'fill', 'color': '#c8e6a0', 'outline': '#6ca040'},
    'OT_PTRK': {'type': 'fill', 'color': '#d8e8c8', 'outline': '#6ca040'},
    'OT_PTWP': {'type': 'fill', 'color': '#b8deff', 'outline': '#4488cc'},
    'OT_ZBIORNIKWODNY': {'type': 'fill', 'color': '#b8deff', 'outline': '#4488cc'},
    'OT_PTZB': {'type': 'fill', 'color': '#f0ece4', 'outline': '#c0b8a8'},
    'OT_PTTR': {'type': 'fill', 'color': '#f0ece4', 'outline': '#c0b8a8'},
    'OT_PTKM': {'type': 'fill', 'color': '#d8eecc', 'outline': '#6ca040'},
    'OT_PTUT': {'type': 'fill', 'color': '#ffffff', 'outline': '#c8c8c8'},
    'OT_PTNZ': {'type': 'fill', 'color': '#ffffff', 'outline': '#c8c8c8'},
    'OT_PTPL': {'type': 'fill', 'color': '#f0ece4', 'outline': '#c0b8a8'},
    'OT_BUBD': {'type': 'fill', 'color': '#1a1a1a', 'outline': '#1a1a1a'},
    'OT_BUSP': {'type': 'fill', 'color': '#1a1a1a', 'outline': '#1a1a1a'},
    'OT_BUWT': {'type': 'fill', 'color': '#1a1a1a', 'outline': '#1a1a1a'},
    'OT_BUZT': {'type': 'fill', 'color': '#1a1a1a', 'outline': '#1a1a1a'},
    'OT_BUIN': {'type': 'fill', 'color': '#808080', 'outline': '#1a1a1a'},
    'OT_SWRS': {'type': 'line', 'color': '#4488cc', 'width': 1.0},
    'OT_SWKN': {'type': 'line', 'color': '#4488cc', 'width': 0.8},
    'OT_SWRM': {'type': 'line', 'color': '#4488cc', 'width': 0.5},
    'OT_CIEK': {'type': 'line', 'color': '#4488cc', 'width': 1.0},
    'OT_SKJZ': {'type': 'line', 'color': '#1a1a1a', 'width': 1.5},
    'OT_SKDR': {'type': 'line', 'color': '#1a1a1a', 'width': 0.8},
    'OT_SKRP': {'type': 'line', 'color': '#1a1a1a', 'width': 0.4},
    'OT_SKTR': {'type': 'line', 'color': '#1a1a1a', 'width': 1.2},
    'OT_SKPP': {'type': 'line', 'color': '#1a1a1a', 'width': 0.5},
    'OT_SZLAKDROGOWY': {'type': 'line', 'color': '#1a1a1a', 'width': 1.0},
    'OT_ULICA': {'type': 'line', 'color': '#1a1a1a', 'width': 0.8},
    'OT_LINIAKOLEJOWA': {'type': 'line', 'color': '#1a1a1a', 'width': 1.2},
    'OT_SULN': {'type': 'line', 'color': '#808080', 'width': 0.3},
    'OT_SUPR': {'type': 'line', 'color': '#808080', 'width': 0.3},
    'OT_OIOR': {'type': 'line', 'color': '#1a1a1a', 'width': 0.3},
    'OT_ADMS': {'type': 'fill', 'color': 'transparent', 'outline': '#1a1a1a'},
    'OT_ADJA': {'type': 'fill', 'color': 'transparent', 'outline': '#1a1a1a'},
    'OT_TCON': {'type': 'fill', 'color': '#d8eecc', 'outline': '#6ca040'},
    'OT_TCPK': {'type': 'fill', 'color': '#d8eecc', 'outline': '#6ca040'},
    'OT_TCPN': {'type': 'fill', 'color': '#d8eecc', 'outline': '#6ca040'},
    'OT_TCRZ': {'type': 'fill', 'color': '#d8eecc', 'outline': '#6ca040'},
}


def find_bdot10k_gml_shp_plugin():
    """Check if the BDOT10k_GML_SHP plugin is installed and find its QML dir."""
    plugins_dir = os.path.join(
        os.path.expanduser("~"), ".local", "share", "QGIS", "QGIS3", "profiles",
        "default", "python", "plugins", "BDOT10k_GML_SHP"
    )
    if not os.path.isdir(plugins_dir):
        # Try alternative paths
        for base in [
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                         "QGIS", "QGIS3", "profiles", "default", "python",
                         "plugins", "BDOT10k_GML_SHP"),
            os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                         "QGIS", "QGIS3", "profiles", "default", "python",
                         "plugins", "BDOT10k_GML_SHP"),
        ]:
            if os.path.isdir(base):
                plugins_dir = base
                break
        else:
            return None, None

    qml_dir = os.path.join(plugins_dir, "BDOT10k_QML")
    svg_dir = os.path.join(plugins_dir, "BDOT10k_SVG")

    if not os.path.isdir(qml_dir):
        return None, None

    return qml_dir, svg_dir if os.path.isdir(svg_dir) else None


def register_svg_paths(svg_dir):
    """Register SVG directory in QGIS settings for point symbol rendering."""
    if not svg_dir:
        return
    settings = QgsSettings()
    paths = settings.value("svg/searchPathsForSVG", []) or []
    if svg_dir not in paths:
        paths.append(svg_dir)
        settings.setValue("svg/searchPathsForSVG", paths)


def _layer_sort_key(name):
    """Get sort key for layer ordering."""
    # Strip geometry suffix for matching
    base = name
    for suffix in ('_A', '_L', '_P'):
        if name.endswith(suffix):
            base = name[:-2]
            break

    for i, ordered_name in enumerate(LAYER_ORDER):
        if name == ordered_name or ordered_name.startswith(base):
            return i
    return len(LAYER_ORDER)


def apply_fallback_style(layer, layer_name):
    """Apply basic fallback style based on layer name prefix."""
    # Find matching style
    style = None
    for prefix, s in FALLBACK_STYLES.items():
        if layer_name.startswith(prefix):
            style = s
            break

    if style is None:
        return

    geom_type = layer.geometryType()

    if style['type'] == 'fill' and geom_type == 2:  # Polygon
        sym = QgsFillSymbol.createSimple({})
        fill_color = style['color']
        if fill_color == 'transparent':
            sym.setColor(QColor(0, 0, 0, 0))
        else:
            sym.setColor(QColor(fill_color))
        sym.symbolLayer(0).setStrokeColor(QColor(style['outline']))
        sym.symbolLayer(0).setStrokeWidth(0.3)
        layer.renderer().setSymbol(sym)
        layer.triggerRepaint()

    elif style['type'] == 'line' and geom_type == 1:  # Line
        sym = QgsLineSymbol.createSimple({})
        sym.setColor(QColor(style['color']))
        sym.setWidth(style.get('width', 0.5))
        layer.renderer().setSymbol(sym)
        layer.triggerRepaint()

    elif style['type'] == 'fill' and geom_type == 0:  # Point with fill style
        sym = QgsMarkerSymbol.createSimple({})
        sym.setColor(QColor(style['color']))
        sym.setSize(2.0)
        layer.renderer().setSymbol(sym)
        layer.triggerRepaint()


def load_bdot10k_folder(folder_path, group_name=None, apply_styles=True):
    """Load all BDOT10k XML/GML files from a folder into QGIS.

    Args:
        folder_path: path to extracted BDOT10k data
        group_name: name for layer group (auto-detected if None)
        apply_styles: whether to apply topo styling

    Returns:
        list of loaded QgsVectorLayer objects
    """
    # Find all XML/GML files recursively
    xml_files = []
    for ext in ('*.xml', '*.XML', '*.gml', '*.GML'):
        xml_files.extend(glob_mod.glob(
            os.path.join(folder_path, '**', ext), recursive=True
        ))

    if not xml_files:
        return []

    # Detect QML plugin
    qml_dir, svg_dir = find_bdot10k_gml_shp_plugin()
    if svg_dir:
        register_svg_paths(svg_dir)

    # Create layer group
    root = QgsProject.instance().layerTreeRoot()
    if group_name is None:
        group_name = f"BDOT10k — {os.path.basename(folder_path)}"
    group = root.findGroup(group_name)
    if group is None:
        group = root.insertGroup(0, group_name)

    # Sort files by layer order
    def file_sort_key(path):
        basename = os.path.splitext(os.path.basename(path))[0]
        # Extract layer name from patterns like PL.PZGiK.238.2466__OT_BUBD_A
        parts = basename.split('__')
        layer_name = parts[-1] if len(parts) > 1 else basename
        return _layer_sort_key(layer_name)

    xml_files.sort(key=file_sort_key)

    layers = []
    crs = QgsCoordinateReferenceSystem("EPSG:2180")

    for xml_path in xml_files:
        basename = os.path.splitext(os.path.basename(xml_path))[0]
        parts = basename.split('__')
        layer_name = parts[-1] if len(parts) > 1 else basename

        # Skip non-BDOT10k files
        if not layer_name.startswith('OT_'):
            continue

        QApplication.processEvents()

        layer = QgsVectorLayer(xml_path, layer_name, "ogr")
        if not layer.isValid():
            continue

        layer.setCrs(crs)

        # Try to apply QML style from BDOT10k_GML_SHP plugin
        style_applied = False
        if apply_styles and qml_dir:
            qml_name = layer_name + ".qml"
            qml_path = os.path.join(qml_dir, qml_name)
            if os.path.isfile(qml_path):
                msg, success = layer.loadNamedStyle(qml_path)
                if success:
                    style_applied = True
                    fix_layer_renderer(layer)

        # Apply fallback style if no QML
        if apply_styles and not style_applied:
            apply_fallback_style(layer, layer_name)

        QgsProject.instance().addMapLayer(layer, False)
        group.addLayer(layer)
        layers.append(layer)

    return layers
