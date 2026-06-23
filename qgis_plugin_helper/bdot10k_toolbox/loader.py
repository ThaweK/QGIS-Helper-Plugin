"""Load BDOT10k GML/XML/SHP files into QGIS with full topo styling."""

import os
import re
import shutil
import glob as glob_mod
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsProject,
    QgsVectorLayer,
    QgsCoordinateReferenceSystem,
    QgsSettings,
    QgsUnitTypes,
    QgsSingleSymbolRenderer,
    QgsCategorizedSymbolRenderer,
    QgsRuleBasedRenderer,
)

try:
    from qgis.core import QgsVectorLayerSimpleLabeling, QgsRuleBasedLabeling
except ImportError:
    QgsVectorLayerSimpleLabeling = None
    QgsRuleBasedLabeling = None

try:
    from qgis.core import QgsPointClusterRenderer
except ImportError:
    QgsPointClusterRenderer = None

from qgis.PyQt.QtWidgets import QApplication

from .style_fixer import fix_layer_renderer

# ---------------------------------------------------------------------------
# Unit constants (handle API differences between QGIS versions)
# ---------------------------------------------------------------------------
try:
    _MAP_UNITS = QgsUnitTypes.RenderMapUnits
    _MM_UNITS = QgsUnitTypes.RenderMillimeters
except AttributeError:
    from qgis.core import Qgis
    _MAP_UNITS = Qgis.RenderUnit.MapUnits
    _MM_UNITS = Qgis.RenderUnit.Millimeters

# At the 1:10,000 reference scale: 1 mm on paper = 10 m on ground = 10 map
# units (EPSG:2180 is in metres).  So MM = MapUnits * 0.1
_MU_TO_MM = 0.1

# ---------------------------------------------------------------------------
# Bundled QML / SVG paths (shipped with this plugin)
# ---------------------------------------------------------------------------
_BUNDLED_QML_DIR = str(
    Path(__file__).resolve().parent.parent / "BDOT10k_GML_SHP" / "BDOT10k_QML"
)
_BUNDLED_SVG_DIR = str(
    Path(__file__).resolve().parent.parent / "BDOT10k_GML_SHP" / "BDOT10k_SVG"
)

# ---------------------------------------------------------------------------
# Subset-filter fragments (XML format)
# ---------------------------------------------------------------------------
_ABOVE_GROUND_XML = (
    "(polozenie = 'ponad powierzchnią gruntu poziom 1' "
    "or polozenie = 'ponad powierzchnią gruntu poziom 2' "
    "or polozenie = 'ponad powierzchnią gruntu poziom 3' "
    "or polozenie = 'ponad powierzchnią gruntu poziom 4')"
)
_BELOW_GROUND_XML = "polozenie = 'pod powierzchnią gruntu'"
_ON_GROUND_XML = "polozenie = 'na powierzchni gruntu'"

_ABOVE_GROUND_SHP = (
    "POLOZENIE = 'ponadPowierzchniaGruntuPoziom1' "
    "or POLOZENIE = 'ponadPowierzchniaGruntuPoziom2'"
)
_BELOW_GROUND_SHP = "POLOZENIE = 'podPowierzchniaGruntu'"
_ON_GROUND_SHP = "POLOZENIE = 'naPowierzchniGruntu'"

_MAJOR_ROAD_NUMBERS_XML = (
    "numerDrogi LIKE 'A%' OR numerDrogi LIKE 'S%' OR numerDrogi LIKE 'DK%' "
    "OR klasaDrogi = 'A' OR klasaDrogi = 'S' "
    "OR klasaDrogi = 'autostrada' OR klasaDrogi = 'ekspresowa' "
    "OR kategoriaZarzadzania = 'drogaKrajowa' "
    "OR kategoriaZarzadzania = 'droga krajowa' "
    "OR kategoriaZarzadzania = 'krajowa'"
)
_MAJOR_ROAD_NUMBERS_SHP = (
    "NUMERDROGI LIKE 'A%' OR NUMERDROGI LIKE 'S%' OR NUMERDROGI LIKE 'DK%' "
    "OR KLASADROGI = 'A' OR KLASADROGI = 'S' "
    "OR KLASADROGI = 'autostrada' OR KLASADROGI = 'ekspresowa' "
    "OR KATZARZADZ = 'drogaKrajowa' "
    "OR KATZARZADZ = 'droga krajowa' "
    "OR KATZARZADZ = 'krajowa'"
)

_CITY_PARTS_XML = (
    "rodzaj = 'czescMiasta' OR rodzaj = 'część miasta' "
    "OR rodzaj = 'dzielnica' OR rodzaj = 'dzielnica miasta' "
    "OR rodzaj = 'czescDzielnicy' OR rodzaj = 'część dzielnicy' "
    "OR rodzaj = 'jednostkaPomocnicza' "
    "OR rodzaj = 'jednostka pomocnicza' OR rodzaj = 'osiedle'"
)
_CITY_PARTS_SHP = (
    "RODZAJ = 'czescMiasta' OR RODZAJ = 'część miasta' "
    "OR RODZAJ = 'dzielnica' OR RODZAJ = 'dzielnica miasta' "
    "OR RODZAJ = 'czescDzielnicy' OR RODZAJ = 'część dzielnicy' "
    "OR RODZAJ = 'jednostkaPomocnicza' "
    "OR RODZAJ = 'jednostka pomocnicza' OR RODZAJ = 'osiedle'"
)

# ---------------------------------------------------------------------------
# Layer definitions — ordered top-of-panel to bottom (top renders last = on
# top of the map).  Each tuple:
#   (source_layer, display_suffix, qml_file, group_type,
#    subset_xml_extra, subset_shp_extra)
#
# group_type: 'labels' → added to the napisy subgroup
#             'main'   → added to the main group
#
# subset_*_extra: additional SQL fragment BESIDES the standard
#   "koniecWersjiObiektu is null" filter.  None means no extra filter.
# ---------------------------------------------------------------------------
LAYER_DEFS = [
    # ── Labels / napisy (z = 65) ──────────────────────────────────────────
    ("OT_SKJZ_L", "numery drog A/S/DK (poziom 65)", "numery drog [65].qml",
     "labels", _MAJOR_ROAD_NUMBERS_XML, _MAJOR_ROAD_NUMBERS_SHP),
    ("OT_SKJZ_L", "nazwy ulic (poziom 65)", "nazwy ulic [65].qml",
     "labels", None, None),
    ("OT_PTPL_A", "nazwy placow (poziom 65)", "nazwy placow [65].qml",
     "labels", None, None),
    ("OT_ADMS_P", "nazwy miast (poziom 65)", "nazwy miast [65].qml",
     "labels", "rodzaj = 'miasto'", "RODZAJ = 'miasto'"),
    ("OT_ADMS_P", "nazwy czesci miast i osiedli (poziom 65)",
     "nazwy czesci miast i osiedli [65].qml", "labels",
     _CITY_PARTS_XML, _CITY_PARTS_SHP),
    ("OT_ADMS_P", "nazwy wsi (poziom 65)", "nazwy wsi [65].qml",
     "labels", "rodzaj = 'wies'", "RODZAJ = 'wies'"),
    ("OT_ADMS_P", "nazwy czesci wsi i kolonii i osad (poziom 65)",
     "nazwy czesci wsi i kolonii i osad [65].qml", "labels",
     "rodzaj = 'czescWsi' OR rodzaj = 'kolonia' OR rodzaj = 'osada'",
     "RODZAJ = 'czescWsi' OR RODZAJ = 'kolonia' OR RODZAJ = 'osada'"),
    ("OT_SWKN_L", "nazwy kanalow (poziom 65) - nad linia",
     "nazwy kanalow [65] - nad linia.qml", "labels", None, None),
    ("OT_SWKN_L", "nazwy kanalow (poziom 65) - na linii",
     "nazwy kanalow [65] - na linii.qml", "labels", None, None),
    ("OT_SWRS_L", "nazwy rzek (poziom 65) - nad linia",
     "nazwy rzek [65] - nad linia.qml", "labels", None, None),
    ("OT_SWRS_L", "nazwy rzek (poziom 65) - na linii",
     "nazwy rzek [65] - na linii.qml", "labels", None, None),
    ("OT_PTWP_A", "nazwy zbiornikow (poziom 65)",
     "nazwy zbiornikow [65].qml", "labels", None, None),
    ("OT_RTPW_P", "opis punktow wysokosciowych (poziom 65)",
     "opis punktow wysokosciowych [65].qml", "labels",
     "rodzaj = 'punkt wysokościowy w terenie'",
     "RODZAJ = 'punkt wysokościowy w terenie'"),
    ("OT_RTPW_P", "opis kopcow hald dolow (poziom 65)",
     "opis kopcow hald dolow [65].qml", "labels",
     "wysokosc >= 2 and rodzaj in ('dół', 'kopiec lub hałda')",
     "WYSOKOSC >= 2 and RODZAJ in ('dół', 'kopiec lub hałda')"),
    ("OT_RTLW_L", "opis skarp i wawozow (poziom 65)",
     "opis skarp i wawozow [65].qml", "labels",
     "wysokosc >= 2 and rodzaj in ('skarpa', 'wąwóz')",
     "WYSOKOSC >= 2 and RODZAJ in ('skarpa', 'wąwóz')"),
    ("OT_RTLW_L", "opis poziomic (poziom 65)",
     "opis poziomic [65].qml", "labels",
     "kodKarto10k IN ('0010_802', '0010_803')",
     "KOD10K IN ('0010_802', '0010_803')"),
    ("OT_BUBD_A", "skroty dla budynkow (poziom 65)",
     "skrot budynku [65].qml", "labels",
     "skrotKartograficzny is not null",
     "skrKARTO is not null"),
    ("OT_KUSK_A", "OT_KUSK_A opis", "OT_KUSK_A opis.qml",
     "labels", None, None),
    ("OT_KUKO_A", "OT_KUKO_A opis", "OT_KUKO_A opis.qml",
     "labels", None, None),
    ("OT_KUZA_A", "OT_KUZA_A opis", "OT_KUZA_A opis.qml",
     "labels", None, None),
    ("OT_KUOS_A", "OT_KUOS_A opis", "OT_KUOS_A opis.qml",
     "labels", None, None),
    ("OT_OIKM_P", "OT_OIKM_P opis", "OT_OIKM_P opis.qml",
     "labels", None, None),

    # ── Main feature layers (z descending: top of map → bottom) ───────────
    ("OT_RTPW_P", "OT_RTPW_P (poziom 63-64)",
     "OT_RTPW_P [63-64].qml", "main", None, None),
    ("OT_KUKO_P", "OT_KUKO_P (poziom 61)",
     "OT_KUKO_P [61].qml", "main", None, None),
    ("OT_OIKM_P", "OT_OIKM_P (poziom 61)",
     "OT_OIKM_P [61].qml", "main", None, None),
    ("OT_OIOR_P", "OT_OIOR_P (poziom 60)",
     "OT_OIOR_P [60].qml", "main", None, None),
    ("OT_OIOR_A", "OT_OIOR_A wiatrak (poziom 60)",
     "OT_OIOR_A wiatrak [60].qml", "main", None, None),
    ("OT_BUWT_P", "OT_BUWT_P (poziom 59)",
     "OT_BUWT_P [59].qml", "main", None, None),
    ("OT_BUIT_P", "OT_BUIT_P (poziom 58)",
     "OT_BUIT_P [58].qml", "main", None, None),
    ("OT_BUIT_A", "OT_BUIT_A (poziom 57-58)",
     "OT_BUIT_A [57-58].qml", "main", None, None),
    ("OT_BUZT_P", "OT_BUZT_P (poziom 56)",
     "OT_BUZT_P [56].qml", "main", None, None),
    ("OT_BUZT_A", "OT_BUZT_A (poziom 55)",
     "OT_BUZT_A [55].qml", "main", None, None),
    ("OT_BUTR_P", "OT_BUTR_P (poziom 54)",
     "OT_BUTR_P [54].qml", "main", None, None),
    ("OT_SULN_L", "OT_SULN_L (poziom 53)",
     "OT_SULN_L [53].qml", "main", None, None),
    ("OT_SUPR_L", "OT_SUPR_L (poziom 52)",
     "OT_SUPR_L [52].qml", "main", None, None),
    ("OT_BUTR_L", "OT_BUTR_L (poziom 51)",
     "OT_BUTR_L [51].qml", "main", None, None),
    ("OT_OIPR_P", "OT_OIPR_P (poziom 50)",
     "OT_OIPR_P [50].qml", "main", None, None),
    ("OT_BUHD_L", "OT_BUHD_L (poziom 49)",
     "OT_BUHD_L [49].qml", "main", None, None),
    ("OT_BUHD_A", "OT_BUHD_A (poziom 49)",
     "OT_BUHD_A [49].qml", "main", None, None),
    ("OT_SKPP_L", "OT_SKPP_L (poziom 48)",
     "OT_SKPP_L [48].qml", "main", None, None),
    ("OT_BUIN_L", "OT_BUIN_L zejscie (poziom 47)",
     "OT_BUIN_L zejscie [47].qml", "main", None, None),
    ("OT_SKRP_L", "OT_SKRP_L nad gruntem (poziom 47)",
     "OT_SKRP_L nad gruntem [47].qml", "main",
     _ABOVE_GROUND_XML, _ABOVE_GROUND_SHP),
    ("OT_SKTR_L", "OT_SKTR_L nad gruntem (poziom 47)",
     "OT_SKTR_L nad gruntem [47].qml", "main",
     _ABOVE_GROUND_XML, _ABOVE_GROUND_SHP),
    ("OT_SKJZ_L", "OT_SKJZ_L nad gruntem (poziom 47)",
     "OT_SKJZ_L nad gruntem [47].qml", "main",
     _ABOVE_GROUND_XML, _ABOVE_GROUND_SHP),
    ("OT_BUIN_L", "OT_BUIN_L (poziom 46)",
     "OT_BUIN_L [46].qml", "main", None, None),
    ("OT_BUUO_L", "OT_BUUO_L (poziom 45)",
     "OT_BUUO_L [45].qml", "main", None, None),
    ("OT_OIOR_L", "OT_OIOR_L (poziom 44)",
     "OT_OIOR_L [44].qml", "main", None, None),
    ("OT_BUBD_A", "OT_BUBD_A symbol (poziom 43)",
     "OT_BUBD_A symbol [43].qml", "main", None, None),
    ("OT_BUBD_A", "OT_BUBD_A (poziom 42)",
     "OT_BUBD_A [42].qml", "main", None, None),
    ("OT_BUWT_A", "OT_BUWT_A (poziom 42)",
     "OT_BUWT_A [42].qml", "main", None, None),
    ("OT_OIOR_A", "OT_OIOR_A (poziom 42)",
     "OT_OIOR_A [42].qml", "main", None, None),
    ("OT_BUIB_A", "OT_BUIB_A (poziom 41)",
     "OT_BUIB_A [41].qml", "main", None, None),
    ("OT_BUIB_L", "OT_BUIB_L (poziom 41)",
     "OT_BUIB_L [41].qml", "main", None, None),
    ("OT_SKTR_L", "OT_SKTR_L (poziom 40)",
     "OT_SKTR_L [40].qml", "main",
     _ON_GROUND_XML, _ON_GROUND_SHP),
    ("OT_OIKM_L", "OT_OIKM_L (poziom 39)",
     "OT_OIKM_L [39].qml", "main", None, None),
    ("OT_SKJZ_L", "OT_SKJZ_L (poziom 33-38)",
     "OT_SKJZ_L [33-38].qml", "main",
     _ON_GROUND_XML, _ON_GROUND_SHP),
    ("OT_SKDR_L", "OT_SKDR_L (poziom 32)",
     "OT_SKDR_L [32].qml", "main", None, None),
    ("OT_SKJZ_L", "OT_SKJZ_L (poziom 31)",
     "OT_SKJZ_L [31].qml", "main",
     _ON_GROUND_XML, _ON_GROUND_SHP),
    ("OT_SKRP_L", "OT_SKRP_L (poziom 30)",
     "OT_SKRP_L [30].qml", "main", None, None),
    ("OT_ADJA_A", "OT_ADJA_A (poziom 25-29)",
     "OT_ADJA_A [25-29].qml", "main", None, None),
    ("OT_TCPN_A", "OT_TCPN_A (poziom 24)",
     "OT_TCPN_A [24].qml", "main", None, None),
    ("OT_TCRZ_A", "OT_TCRZ_A (poziom 23)",
     "OT_TCRZ_A [23].qml", "main", None, None),
    ("OT_TCPK_A", "OT_TCPK_A (poziom 22)",
     "OT_TCPK_A [22].qml", "main", None, None),
    ("OT_KUPW_A", "OT_KUPW_A (poziom 21)",
     "OT_KUPW_A [21].qml", "main", None, None),
    ("OT_SKTR_L", "OT_SKTR_L pod gruntem (poziom 20)",
     "OT_SKTR_L pod gruntem [20].qml", "main",
     _BELOW_GROUND_XML, _BELOW_GROUND_SHP),
    ("OT_SKJZ_L", "OT_SKJZ_L pod gruntem (poziom 20)",
     "OT_SKJZ_L pod gruntem [20].qml", "main",
     _BELOW_GROUND_XML, _BELOW_GROUND_SHP),
    ("OT_BUSP_L", "OT_BUSP_L (poziom 20)",
     "OT_BUSP_L [20].qml", "main", None, None),
    ("OT_BUSP_A", "OT_BUSP_A (poziom 19)",
     "OT_BUSP_A [19].qml", "main", None, None),
    ("OT_OIPR_L", "OT_OIPR_L (poziom 17-18)",
     "OT_OIPR_L [17-18].qml", "main", None, None),
    ("OT_KUSC_A", "OT_KUSC_A (poziom 16)",
     "OT_KUSC_A [16].qml", "main", None, None),
    ("OT_OISZ_A", "OT_OISZ_A (poziom 15)",
     "OT_OISZ_A [15].qml", "main", None, None),
    ("OT_PTWP_A", "OT_PTWP_A (poziom 13)",
     "OT_PTWP_A [13].qml", "main", None, None),
    ("OT_SWRS_L", "OT_SWRS_L (poziom 12)",
     "OT_SWRS_L [12].qml", "main", None, None),
    ("OT_SWKN_L", "OT_SWKN_L (poziom 12)",
     "OT_SWKN_L [12].qml", "main", None, None),
    ("OT_SWRM_L", "OT_SWRM_L (poziom 12)",
     "OT_SWRM_L [12].qml", "main", None, None),
    ("OT_PTPL_A", "OT_PTPL_A (poziom 11)",
     "OT_PTPL_A [11].qml", "main", None, None),
    ("OT_PTKM_A", "OT_PTKM_A (poziom 11)",
     "OT_PTKM_A [11].qml", "main", None, None),
    ("OT_PTZB_A", "OT_PTZB_A plac (poziom 11)",
     "OT_PTZB_A plac [11].qml", "main", None, None),
    ("OT_OIMK_A", "OT_OIMK_A (poziom 10)",
     "OT_OIMK_A [10].qml", "main", None, None),
    ("OT_BUZM_L", "OT_BUZM_L (poziom 7)",
     "OT_BUZM_L [7].qml", "main", None, None),
    ("OT_RTLW_L", "OT_RTLW_L (poziom 5-6)",
     "OT_RTLW_L [5-6].qml", "main", None, None),
    ("OT_KUPG_A", "OT_KUPG_A (poziom 4)",
     "OT_KUPG_A [4].qml", "main", None, None),
    ("OT_PTSO_A", "OT_PTSO_A (poziom 3)",
     "OT_PTSO_A [3].qml", "main", None, None),
    ("OT_PTWZ_A", "OT_PTWZ_A skladowisko (poziom 3)",
     "OT_PTWZ_A skladowisko [3].qml", "main", None, None),
    ("OT_PTWZ_A", "OT_PTWZ_A (poziom 1)",
     "OT_PTWZ_A [1].qml", "main", None, None),
    ("OT_PTGN_A", "OT_PTGN_A (poziom 1)",
     "OT_PTGN_A [1].qml", "main", None, None),
    ("OT_PTZB_A", "OT_PTZB_A roslinnosc (poziom 0)",
     "OT_PTZB_A roslinnosc [0].qml", "main", None, None),
    ("OT_PTTR_A", "OT_PTTR_A (poziom 0)",
     "OT_PTTR_A [0].qml", "main", None, None),
    ("OT_PTLZ_A", "OT_PTLZ_A (poziom 0)",
     "OT_PTLZ_A [0].qml", "main", None, None),
    ("OT_PTRK_A", "OT_PTRK_A (poziom 0)",
     "OT_PTRK_A [0].qml", "main", None, None),
    ("OT_PTUT_A", "OT_PTUT_A (poziom 0)",
     "OT_PTUT_A [0].qml", "main", None, None),
    ("OT_TCON_A", "OT_TCON_A (bez symbolizacji)",
     "OT_TCON_A.qml", "main", None, None),
]

# Pattern to detect BDOT10k data files
_FILE_PATTERN = re.compile(
    r"PL\.PZGiK\.\d{3,4}\.\d{4}(__OT_|_OT_)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# MapUnit → MM conversion  (so labels / symbols scale with print & zoom)
# ---------------------------------------------------------------------------

def _is_map_unit(unit):
    """Check if a render unit is MapUnits (handles API variations)."""
    return unit == _MAP_UNITS


def _convert_text_format(fmt):
    """Convert MapUnit sizes inside a QgsTextFormat to MM."""
    changed = False

    if _is_map_unit(fmt.sizeUnit()):
        fmt.setSize(fmt.size() * _MU_TO_MM)
        fmt.setSizeUnit(_MM_UNITS)
        changed = True

    buf = fmt.buffer()
    if buf.enabled() and _is_map_unit(buf.sizeUnit()):
        buf.setSize(buf.size() * _MU_TO_MM)
        buf.setSizeUnit(_MM_UNITS)
        fmt.setBuffer(buf)
        changed = True

    shadow = fmt.shadow()
    if shadow.enabled() and _is_map_unit(shadow.offsetUnit()):
        shadow.setOffsetDistance(shadow.offsetDistance() * _MU_TO_MM)
        shadow.setOffsetUnit(_MM_UNITS)
        fmt.setShadow(shadow)
        changed = True

    return changed


def _convert_pal_settings(settings):
    """Convert a QgsPalLayerSettings text format from MapUnit to MM."""
    fmt = settings.format()
    if _convert_text_format(fmt):
        settings.setFormat(fmt)
        return True
    return False


def _convert_labeling_to_mm(layer):
    """Walk the layer's labeling config and convert MapUnit fonts to MM."""
    try:
        labeling = layer.labeling()
    except (RuntimeError, SystemError):
        return
    if labeling is None:
        return

    try:
        if QgsVectorLayerSimpleLabeling and isinstance(
            labeling, QgsVectorLayerSimpleLabeling
        ):
            settings = labeling.settings()
            if _convert_pal_settings(settings):
                layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))

        elif QgsRuleBasedLabeling and isinstance(labeling, QgsRuleBasedLabeling):
            def _walk(rule):
                try:
                    s = rule.settings()
                    if s is not None:
                        if _convert_pal_settings(s):
                            rule.setSettings(s)
                except (RuntimeError, SystemError):
                    pass
                for child in rule.children():
                    _walk(child)
            _walk(labeling.rootRule())
            layer.setLabeling(labeling)
    except (RuntimeError, SystemError):
        pass


def _convert_symbol_to_mm(symbol):
    """Convert MapUnit sizes on every symbol-layer inside *symbol*."""
    if symbol is None:
        return
    try:
        count = symbol.symbolLayerCount()
    except (RuntimeError, SystemError):
        return
    for i in range(count):
        try:
            sl = symbol.symbolLayer(i)
            if sl is None:
                continue
        except (RuntimeError, SystemError):
            continue
        try:
            # Line width (QgsSimpleLineSymbolLayer, etc.)
            if hasattr(sl, 'widthUnit') and hasattr(sl, 'setWidthUnit'):
                if _is_map_unit(sl.widthUnit()):
                    sl.setWidth(sl.width() * _MU_TO_MM)
                    sl.setWidthUnit(_MM_UNITS)
            # Stroke / outline width (QgsSimpleFillSymbolLayer, etc.)
            if hasattr(sl, 'strokeWidthUnit') and hasattr(sl, 'setStrokeWidthUnit'):
                if _is_map_unit(sl.strokeWidthUnit()):
                    sl.setStrokeWidth(sl.strokeWidth() * _MU_TO_MM)
                    sl.setStrokeWidthUnit(_MM_UNITS)
            # Marker size
            if hasattr(sl, 'sizeUnit') and hasattr(sl, 'setSizeUnit'):
                if _is_map_unit(sl.sizeUnit()):
                    sl.setSize(sl.size() * _MU_TO_MM)
                    sl.setSizeUnit(_MM_UNITS)
        except (RuntimeError, SystemError):
            continue


def _collect_symbols(renderer):
    """Return all QgsSymbol objects from a renderer."""
    if renderer is None:
        return []
    syms = []
    try:
        if isinstance(renderer, QgsSingleSymbolRenderer):
            s = renderer.symbol()
            if s is not None:
                syms.append(s)
        elif isinstance(renderer, QgsCategorizedSymbolRenderer):
            for cat in renderer.categories():
                try:
                    s = cat.symbol()
                    if s is not None:
                        syms.append(s)
                except (RuntimeError, SystemError):
                    continue
        elif isinstance(renderer, QgsRuleBasedRenderer):
            def _walk(rule):
                try:
                    s = rule.symbol()
                    if s is not None:
                        syms.append(s)
                except (RuntimeError, SystemError):
                    pass
                for child in rule.children():
                    _walk(child)
            _walk(renderer.rootRule())
        if QgsPointClusterRenderer and isinstance(
            renderer, QgsPointClusterRenderer
        ):
            syms.extend(_collect_symbols(renderer.embeddedRenderer()))
    except (RuntimeError, SystemError):
        pass
    return syms


def _convert_renderer_to_mm(layer):
    """Convert MapUnit symbol sizes to MM for consistent print output."""
    try:
        for sym in _collect_symbols(layer.renderer()):
            _convert_symbol_to_mm(sym)
    except (RuntimeError, SystemError):
        pass


def _convert_sizes_to_mm(layer):
    """Convert MapUnit label sizes to MM for readable print output.

    The bundled QML styles are authored at 1:10,000 with MapUnit sizing.
    Converting labels to MM makes them readable at any zoom level and
    any print scale (e.g. 1:60,000).

    Note: renderer symbol sizes are left as MapUnit intentionally —
    accessing QgsSymbol objects from categorized renderers via SIP
    bindings can cause SIGSEGV crashes (null C++ pointer dereference)
    when the underlying objects are garbage-collected during iteration.
    """
    try:
        _convert_labeling_to_mm(layer)
    except (RuntimeError, SystemError):
        pass
    try:
        layer.triggerRepaint()
    except (RuntimeError, SystemError):
        pass


def register_svg_paths():
    """Register the bundled SVG directory in QGIS settings."""
    if not os.path.isdir(_BUNDLED_SVG_DIR):
        return
    # Also copy to user SVG dir for symbol rendering
    svg_qgis = os.path.join(
        QgsApplication.qgisSettingsDirPath(), "SVG", "KARTO10k"
    )
    karto_src = os.path.join(_BUNDLED_SVG_DIR, "KARTO10k")
    if os.path.isdir(karto_src) and not os.path.isdir(svg_qgis):
        try:
            shutil.copytree(karto_src, svg_qgis)
        except Exception:
            pass
    settings = QgsSettings()
    paths = settings.value("svg/searchPathsForSVG", []) or []
    if _BUNDLED_SVG_DIR not in paths:
        paths.append(_BUNDLED_SVG_DIR)
        settings.setValue("svg/searchPathsForSVG", paths)


def find_bdot10k_data_dirs(root_folder):
    """Recursively find all directories containing BDOT10k data files.

    Handles folder structures like:
        BDOT10k/2466/PL.PZGiK.238.2466/BDOT10k/
    or flat folders with PL.PZGiK.XXX.XXXX__OT_*.xml files.

    Returns list of (data_dir, namespace_prefix, file_format) tuples.
    """
    results = []
    seen_dirs = set()

    for dirpath, dirnames, filenames in os.walk(root_folder):
        for fname in filenames:
            if not (fname.lower().endswith(('.xml', '.shp', '.gml'))):
                continue
            if not _FILE_PATTERN.match(fname):
                continue

            if dirpath in seen_dirs:
                continue
            seen_dirs.add(dirpath)

            # Extract namespace prefix and format
            parts = re.split(r'__', fname)
            ns_prefix = parts[0] if len(parts) > 1 else None
            if ns_prefix is None:
                parts = re.split(r'_OT_', fname, maxsplit=1)
                ns_prefix = parts[0] if len(parts) > 1 else None

            fmt = "xml"
            if fname.lower().endswith(".shp"):
                fmt = "shp"
            elif fname.lower().endswith(".gml"):
                fmt = "xml"

            if ns_prefix:
                results.append((dirpath, ns_prefix, fmt))

    return results


def _build_subset(subset_extra, fmt, layer):
    """Build the complete subset string for a layer."""
    has_version = layer.fields().indexFromName("koniecWersjiObiektu") >= 0
    version_filter = "koniecWersjiObiektu is null" if has_version else None

    if fmt == "shp":
        extra = subset_extra  # subset_shp is passed directly
    else:
        extra = subset_extra  # subset_xml is passed directly

    parts = [p for p in (extra, version_filter) if p]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"({parts[0]}) and {parts[1]}"


def load_bdot10k_folder(folder_path, group_name=None, apply_styles=True):
    """Load all BDOT10k data from a folder into QGIS.

    Handles both flat folders and nested structures like
    BDOT10k/{TERYT}/PL.PZGiK.238.{TERYT}/BDOT10k/.

    Supports multiple powiats in one folder tree.

    Args:
        folder_path: path to BDOT10k data (can be top-level or direct)
        group_name: name for layer group (auto-detected if None)
        apply_styles: whether to apply topo styling

    Returns:
        list of loaded QgsVectorLayer objects
    """
    data_dirs = find_bdot10k_data_dirs(folder_path)
    if not data_dirs:
        return []

    all_layers = []
    for i, (data_dir, ns_prefix, fmt) in enumerate(data_dirs):
        layers = _load_single_dataset(
            data_dir, ns_prefix, fmt, group_name, apply_styles
        )
        all_layers.extend(layers)
        # Let Qt fully process between datasets to avoid C++ object
        # lifetime issues when loading many powiats at once
        QApplication.processEvents()

    return all_layers


def _load_single_dataset(data_dir, ns_prefix, fmt, group_name, apply_styles):
    """Load one BDOT10k dataset (one powiat)."""
    from .teryt_registry import get_powiat_name

    # Register SVG paths
    register_svg_paths()

    # Detect TERYT from namespace
    teryt_match = re.search(r'\.(\d{4})$', ns_prefix)
    teryt = teryt_match.group(1) if teryt_match else None
    powiat_name = get_powiat_name(teryt) if teryt else None

    # Build group name
    if group_name is None:
        if powiat_name and teryt:
            gname = f"BDOT10k POWIAT {powiat_name}"
        else:
            gname = f"BDOT10k — {os.path.basename(data_dir)}"
    else:
        gname = group_name

    root = QgsProject.instance().layerTreeRoot()
    group = root.insertGroup(0, gname)
    group.setExpanded(False)

    labels_group = group.addGroup(f"{ns_prefix} napisy")
    labels_group.setExpanded(False)

    path = data_dir.replace("\\", "/") + "/"
    crs = QgsCoordinateReferenceSystem("EPSG:2180")
    qml_dir = _BUNDLED_QML_DIR
    layers = []

    # First pass: create all layers without adding to project
    # (avoids processEvents mid-iteration which can crash)
    pending = []
    for (source_layer, display_suffix, qml_file, group_type,
         subset_xml, subset_shp) in LAYER_DEFS:

        # Check if source file exists
        source_file = f"{path}{ns_prefix}__{source_layer}.{fmt}"
        if not os.path.exists(source_file):
            continue

        # Create layer
        layer_name = f"{ns_prefix}__{display_suffix}"
        layer = QgsVectorLayer(source_file, layer_name, "ogr")
        if not layer.isValid() or layer.featureCount() == 0:
            continue

        layer.setCrs(crs)

        # Apply subset filter
        subset_extra = subset_xml if fmt == "xml" else subset_shp
        subset_str = _build_subset(subset_extra, fmt, layer)
        if subset_str:
            layer.setSubsetString(subset_str)
            if layer.featureCount() == 0:
                continue

        # Apply QML style (before adding to project — no repaint yet)
        if apply_styles and os.path.isdir(qml_dir):
            qml_path = os.path.join(qml_dir, qml_file)
            if os.path.isfile(qml_path):
                msg, success = layer.loadNamedStyle(qml_path)
                if success:
                    fix_layer_renderer(layer)
                    _convert_sizes_to_mm(layer)

        pending.append((layer, group_type))

    # Second pass: add all layers to the project in one batch
    for layer, group_type in pending:
        QgsProject.instance().addMapLayer(layer, False)
        target_group = labels_group if group_type == "labels" else group
        target_group.addLayer(layer)

        node = root.findLayer(layer.id())
        if node:
            node.setExpanded(False)

        layers.append(layer)

    return layers
