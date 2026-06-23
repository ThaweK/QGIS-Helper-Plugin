"""Download and style OSM label layers for the current map BBOX."""

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from qgis.PyQt.QtCore import QSizeF, QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsNullSymbolRenderer,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

try:
    from qgis.core import QgsRuleBasedLabeling
except ImportError:
    QgsRuleBasedLabeling = None

try:
    from qgis.core import QgsTextBackgroundSettings
except ImportError:
    QgsTextBackgroundSettings = None


GROUP_NAME = "OSM etykiety BBOX"
CUSTOM_PROPERTY = "qgis_plugin_helper/osm_bbox_labels"
DEFAULT_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
LABEL_CRS = QgsCoordinateReferenceSystem("EPSG:2180")
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


try:
    _MM_UNITS = QgsUnitTypes.RenderMillimeters
except AttributeError:
    from qgis.core import Qgis

    _MM_UNITS = Qgis.RenderUnit.Millimeters


def download_osm_labels_for_canvas(iface, endpoint=DEFAULT_OVERPASS_ENDPOINT):
    """Fetch OSM labels for current canvas extent and add styled label layers."""
    project = QgsProject.instance()
    canvas = iface.mapCanvas()
    bbox = _canvas_bbox_wgs84(canvas, project)
    payload = _fetch_overpass(bbox, endpoint)

    removed = _remove_previous_layers(project)
    group = _ensure_group(project)

    place_layer, place_count = _build_place_layer(payload, project)
    road_layer, road_count = _build_road_shield_layer(payload, project)

    created = 0
    for layer in (road_layer, place_layer):
        if layer is None:
            continue
        layer.setCustomProperty(CUSTOM_PROPERTY, "1")
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        created += 1

    canvas.refreshAllLayers()
    return {
        "created": created,
        "removed": removed,
        "places": place_count,
        "road_shields": road_count,
        "bbox": bbox,
    }


def _canvas_bbox_wgs84(canvas, project):
    transform = QgsCoordinateTransform(
        canvas.mapSettings().destinationCrs(),
        WGS84,
        project,
    )
    rect = transform.transformBoundingBox(canvas.extent())
    return {
        "south": rect.yMinimum(),
        "west": rect.xMinimum(),
        "north": rect.yMaximum(),
        "east": rect.xMaximum(),
    }


def _fetch_overpass(bbox, endpoint):
    query = _overpass_query(bbox)
    data = urlencode({"data": query}).encode("utf-8")
    request = Request(
        endpoint,
        data=data,
        headers={
            "User-Agent": "QGIS-Plugin-Helper/OSM-BBOX-Labels",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _overpass_query(bbox):
    bbox_text = (
        f"{bbox['south']:.8f},{bbox['west']:.8f},"
        f"{bbox['north']:.8f},{bbox['east']:.8f}"
    )
    place_values = "city|town|village|municipality|hamlet|suburb|quarter|neighbourhood|borough"
    major_highways = "motorway|trunk|primary|secondary"
    return f"""
[out:json][timeout:45];
(
  node["place"~"^({place_values})$"]["name"]({bbox_text});
  way["place"~"^({place_values})$"]["name"]({bbox_text});
  relation["place"~"^({place_values})$"]["name"]({bbox_text});
);
out body center;
(
  way["highway"~"^({major_highways})$"]["ref"~"^(A|S|DK|DW|E|[0-9])"]({bbox_text});
  way["highway"~"^({major_highways})$"]["int_ref"~"^E"]({bbox_text});
);
out body geom;
"""


def _build_place_layer(payload, project):
    layer = QgsVectorLayer(f"Point?crs={LABEL_CRS.authid()}", "OSM etykiety - miejscowosci", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("name", QVariant.String),
        QgsField("place", QVariant.String),
        QgsField("rank", QVariant.Int),
        QgsField("population", QVariant.Int),
        QgsField("label_class", QVariant.String),
    ])
    layer.updateFields()

    transform = QgsCoordinateTransform(WGS84, LABEL_CRS, project)
    seen = set()
    features = []

    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = tags.get("name")
        place = tags.get("place")
        if not name or place not in _place_ranks():
            continue

        lon, lat = _element_lon_lat(element)
        if lon is None or lat is None:
            continue

        key = (name.lower(), place, round(lon, 4), round(lat, 4))
        if key in seen:
            continue
        seen.add(key)

        population = _parse_population(tags.get("population"))
        label_class = _place_label_class(place, population)

        point = transform.transform(QgsPointXY(lon, lat))
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature.setAttributes([name, place, _place_ranks()[place], population, label_class])
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()
    _make_label_only(layer)
    _apply_place_labeling(layer)
    return (layer if features else None), len(features)


def _build_road_shield_layer(payload, project):
    node_index = {
        element["id"]: (element["lon"], element["lat"])
        for element in payload.get("elements", [])
        if element.get("type") == "node" and "lon" in element and "lat" in element
    }

    road_segments = {}
    transform = QgsCoordinateTransform(WGS84, LABEL_CRS, project)
    for element in payload.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags") or {}
        refs = _normalized_road_refs(
            tags.get("ref"),
            tags.get("highway"),
            tags.get("int_ref"),
        )
        if not refs:
            continue

        points = _road_points(element, transform, node_index)
        if len(points) < 2:
            continue

        geometry = QgsGeometry.fromPolylineXY(points)
        length = geometry.length()
        if length < 80:
            continue

        for ref_label, shield_type in refs:
            key = (ref_label, shield_type)
            entry = road_segments.setdefault(
                key,
                {
                    "segments": [],
                    "length": 0.0,
                    "highway": tags.get("highway") or "",
                },
            )
            entry["segments"].append(points)
            entry["length"] += length
            if length > 0 and tags.get("highway"):
                entry["highway"] = tags["highway"]

    layer = QgsVectorLayer(f"MultiLineString?crs={LABEL_CRS.authid()}", "OSM etykiety - drogi A S DK DW E", "memory")
    provider = layer.dataProvider()
    provider.addAttributes([
        QgsField("ref_label", QVariant.String),
        QgsField("shield_type", QVariant.String),
        QgsField("highway", QVariant.String),
    ])
    layer.updateFields()

    features = []
    for (ref_label, shield_type), entry in sorted(
        road_segments.items(),
        key=lambda item: item[1]["length"],
        reverse=True,
    ):
        segments = entry["segments"]
        if not segments:
            continue
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromMultiPolylineXY(segments))
        feature.setAttributes([ref_label, shield_type, entry["highway"]])
        features.append(feature)

    provider.addFeatures(features)
    layer.updateExtents()
    _make_label_only(layer)
    _apply_road_labeling(layer)
    return (layer if features else None), len(features)


def _element_lon_lat(element):
    if "lon" in element and "lat" in element:
        return element["lon"], element["lat"]
    center = element.get("center") or {}
    if "lon" in center and "lat" in center:
        return center["lon"], center["lat"]
    return None, None


def _road_points(element, transform, node_index):
    geometry_points = element.get("geometry") or []
    if geometry_points:
        return [
            transform.transform(QgsPointXY(point["lon"], point["lat"]))
            for point in geometry_points
            if "lon" in point and "lat" in point
        ]

    points = []
    for node_id in element.get("nodes", []):
        lon_lat = node_index.get(node_id)
        if lon_lat is None:
            continue
        points.append(transform.transform(QgsPointXY(*lon_lat)))
    return points


def _place_ranks():
    return {
        "city": 10,
        "town": 9,
        "village": 7,
        "municipality": 7,
        "suburb": 6,
        "borough": 6,
        "quarter": 5,
        "neighbourhood": 4,
        "hamlet": 3,
    }


def _parse_population(raw_population):
    if raw_population is None:
        return 0
    match = re.search(r"\d+", str(raw_population).replace(" ", "").replace(",", ""))
    if not match:
        return 0
    try:
        return int(match.group(0))
    except ValueError:
        return 0


def _place_label_class(place, population):
    if population >= 500000:
        return "metropolis"
    if population >= 100000:
        return "large_city"
    if population >= 20000:
        return "city"
    if population >= 5000:
        return "town"
    if population >= 1000:
        return "municipality"
    if place == "city":
        return "city"
    if place == "town":
        return "town"
    if place in ("village", "municipality", "suburb", "borough"):
        return "municipality"
    if place in ("quarter", "neighbourhood"):
        return "district"
    return "hamlet"


def _normalized_road_refs(raw_ref, highway, raw_int_ref=None):
    if not raw_ref and not raw_int_ref:
        return []
    result = []
    for item in re.split(r"[;,/]", raw_ref or ""):
        text = item.strip().upper().replace(" ", "")
        if re.match(r"^A\d+[A-Z]?$", text):
            result.append((text, "national"))
        elif re.match(r"^S\d+[A-Z]?$", text):
            result.append((text, "national"))
        elif re.match(r"^DK\d+[A-Z]?$", text):
            result.append((text[2:], "national"))
        elif re.match(r"^DW\d{3}[A-Z]?$", text):
            result.append((text[2:], "voivodeship"))
        elif re.match(r"^E\d+[A-Z]?$", text):
            result.append((text, "international"))
        elif re.match(r"^\d+[A-Z]?$", text):
            digits = re.match(r"^(\d+)", text).group(1)
            if len(digits) == 3:
                result.append((text, "voivodeship"))
            elif highway == "motorway":
                result.append((f"A{text}", "national"))
            elif highway in ("trunk", "primary"):
                result.append((text, "national"))
    for item in re.split(r"[;,/]", raw_int_ref or ""):
        text = item.strip().upper().replace(" ", "")
        if re.match(r"^E\d+[A-Z]?$", text):
            result.append((text, "international"))
    return list(dict.fromkeys(result))


def _remove_previous_layers(project):
    layer_ids = [
        layer.id()
        for layer in project.mapLayers().values()
        if layer.customProperty(CUSTOM_PROPERTY) == "1"
    ]
    if layer_ids:
        project.removeMapLayers(layer_ids)

    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME)
    if group is not None and not group.children():
        root.removeChildNode(group)
    return len(layer_ids)


def _ensure_group(project):
    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME)
    if group is None:
        group = root.insertGroup(0, GROUP_NAME)
    return group


def _make_label_only(layer):
    layer.setRenderer(QgsNullSymbolRenderer())
    layer.setLabelsEnabled(True)


def _apply_place_labeling(layer):
    if QgsRuleBasedLabeling is None:
        settings = _point_label_settings(
            '"name"',
            3.5,
            QColor(35, 29, 23),
            QColor(248, 244, 226),
            italic=True,
            opacity=0.7,
            font_stretch=87,
            priority=8,
            family="Liberation Serif",
        )
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.triggerRepaint()
        return

    root = QgsRuleBasedLabeling.Rule(QgsPalLayerSettings())
    rules = [
        ("metropolie", '"label_class" = \'metropolis\' AND @map_scale < 500000', 6.2, True, 1.0, 10),
        ("duze miasta", '"label_class" = \'large_city\' AND @map_scale < 350000', 5.1, True, 0.85, 10),
        ("miasta", '"label_class" = \'city\' AND @map_scale < 250000', 4.5, True, 0.75, 9),
        ("male miasta", '"label_class" = \'town\' AND @map_scale < 160000', 3.9, False, 0.68, 8),
        ("miejscowosci gminne i wsie", '"label_class" = \'municipality\' AND @map_scale < 100000', 3.4, False, 0.62, 7),
        ("dzielnice i osiedla", '"label_class" = \'district\' AND @map_scale < 50000', 3.4, False, 0.6, 6),
        ("przysiolki", '"label_class" = \'hamlet\' AND @map_scale < 25000', 3.1, False, 0.6, 5),
    ]
    for description, expression, size, bold, opacity, priority in rules:
        settings = _point_label_settings(
            '"name"',
            size,
            QColor(35, 29, 23),
            QColor(248, 244, 226),
            bold=bold,
            italic=True,
            opacity=opacity,
            font_stretch=87,
            priority=priority,
            family="Liberation Serif",
        )
        rule = QgsRuleBasedLabeling.Rule(settings)
        rule.setDescription(description)
        rule.setFilterExpression(expression)
        root.appendChild(rule)

    layer.setLabeling(QgsRuleBasedLabeling(root))
    layer.triggerRepaint()


def _apply_road_labeling(layer):
    if QgsRuleBasedLabeling is None:
        settings = _road_label_settings(QColor(255, 255, 255), QColor(178, 24, 28))
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.triggerRepaint()
        return

    root = QgsRuleBasedLabeling.Rule(QgsPalLayerSettings())
    rules = [
        ("drogi krajowe i szybkie", '"shield_type" = \'national\'', QColor(255, 255, 255), QColor(178, 24, 28)),
        ("drogi wojewodzkie", '"shield_type" = \'voivodeship\'', QColor(0, 0, 0), QColor(255, 211, 71)),
        ("drogi miedzynarodowe", '"shield_type" = \'international\'', QColor(255, 255, 255), QColor(0, 128, 72)),
    ]
    for description, expression, text_color, fill_color in rules:
        settings = _road_label_settings(text_color, fill_color)
        rule = QgsRuleBasedLabeling.Rule(settings)
        rule.setDescription(description)
        rule.setFilterExpression(expression)
        root.appendChild(rule)

    layer.setLabeling(QgsRuleBasedLabeling(root))
    layer.triggerRepaint()


def _road_label_settings(text_color, fill_color):
    settings = _point_label_settings(
        '"ref_label"',
        3.1,
        text_color,
        None,
        bold=True,
        priority=10,
        family="Liberation Sans",
    )
    settings.placement = _pal_enum("Line", "Curved", default=3)
    settings.placementFlags = _pal_enum("OnLine", default=2)
    settings.mergeLines = True
    settings.labelPerPart = False
    fmt = settings.format()
    _apply_road_shield_background(fmt, fill_color)
    settings.setFormat(fmt)
    return settings


def _point_label_settings(expression, size, color, buffer_color, bold=False, italic=False, priority=5, family="Liberation Serif", opacity=1.0, font_stretch=None):
    settings = QgsPalLayerSettings()
    settings.fieldName = expression
    settings.isExpression = True
    settings.priority = priority
    settings.obstacle = False
    settings.placement = _pal_enum("AroundPoint", "OverPoint", default=0)
    settings.dist = 1.1
    settings.distUnits = _MM_UNITS

    font = QFont(family)
    font.setBold(bold)
    font.setItalic(italic)
    if font_stretch is not None and hasattr(font, "setStretch"):
        font.setStretch(font_stretch)

    text_format = QgsTextFormat()
    text_format.setFont(font)
    text_format.setSize(size)
    text_format.setSizeUnit(_MM_UNITS)
    label_color = QColor(color)
    if not hasattr(text_format, "setOpacity") and opacity < 1.0:
        label_color.setAlphaF(opacity)
    text_format.setColor(label_color)
    if hasattr(text_format, "setOpacity"):
        text_format.setOpacity(opacity)

    buffer = QgsTextBufferSettings()
    if buffer_color is None:
        buffer.setEnabled(False)
    else:
        buffer.setEnabled(True)
        buffer.setSize(0.28)
        buffer.setSizeUnit(_MM_UNITS)
        buffer.setColor(buffer_color)
        if hasattr(buffer, "setOpacity"):
            buffer.setOpacity(min(0.88, opacity))
    text_format.setBuffer(buffer)
    settings.setFormat(text_format)
    return settings


def _apply_road_shield_background(text_format, fill_color):
    if not hasattr(text_format, "background"):
        return

    background = text_format.background()
    background.setEnabled(True)
    if QgsTextBackgroundSettings is not None:
        if hasattr(background, "setType") and hasattr(QgsTextBackgroundSettings, "ShapeRectangle"):
            background.setType(QgsTextBackgroundSettings.ShapeRectangle)
        if hasattr(background, "setSizeType") and hasattr(QgsTextBackgroundSettings, "SizeBuffer"):
            background.setSizeType(QgsTextBackgroundSettings.SizeBuffer)
    if hasattr(background, "setFillColor"):
        background.setFillColor(fill_color)
    if hasattr(background, "setStrokeColor"):
        background.setStrokeColor(QColor(255, 255, 255))
    if hasattr(background, "setStrokeWidth"):
        background.setStrokeWidth(0.35)
    if hasattr(background, "setStrokeWidthUnit"):
        background.setStrokeWidthUnit(_MM_UNITS)
    if hasattr(background, "setSizeUnit"):
        background.setSizeUnit(_MM_UNITS)
    if hasattr(background, "setSize"):
        try:
            background.setSize(QSizeF(1.0, 0.5))
        except TypeError:
            pass
    if hasattr(text_format, "setBackground"):
        text_format.setBackground(background)


def _pal_enum(*names, default):
    for name in names:
        if hasattr(QgsPalLayerSettings, name):
            return getattr(QgsPalLayerSettings, name)
    return default
