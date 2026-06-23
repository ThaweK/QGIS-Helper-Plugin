"""Style BDOT10k labels as a dedicated label set.

The preferred mode applies labels directly to existing BDOT10k layers without
changing their renderers. A fallback overlay mode clones source layers, turns
their symbols off, and applies labels above any background map such as ESRI
Topo. Re-running the overlay mode replaces only layers previously created by
this module.

QGIS Python console usage:

    from qgis_plugin_helper.bdot10k_toolbox.topo_90s_labels import (
        apply_topo_90s_labels_in_place,
    )
    apply_topo_90s_labels_in_place(iface)
"""

from dataclasses import dataclass, replace

from qgis.PyQt.QtCore import QSizeF
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    QgsNullSymbolRenderer,
    QgsPalLayerSettings,
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


GROUP_NAME = "BDOT10k etykiety"
LEGACY_GROUP_NAMES = ("BDOT10k napisy - topo lata 90",)
CUSTOM_PROPERTY = "qgis_plugin_helper/topo_90s_label"
IN_PLACE_PROPERTY = "qgis_plugin_helper/topo_90s_label_in_place"


try:
    _MM_UNITS = QgsUnitTypes.RenderMillimeters
    _MAP_UNITS = QgsUnitTypes.RenderMapUnits
except AttributeError:
    from qgis.core import Qgis

    _MM_UNITS = Qgis.RenderUnit.Millimeters
    _MAP_UNITS = Qgis.RenderUnit.MapUnits


@dataclass(frozen=True)
class LabelSpec:
    key: str
    source_code: str
    layer_suffix: str
    expression_kind: str
    subset_kind: str
    geometry_kind: str
    size_mm: float
    color: tuple
    buffer_color: tuple
    buffer_mm: float
    family: str = "Liberation Serif"
    bold: bool = False
    italic: bool = False
    priority: int = 5
    scale_min: int = 0
    scale_max: int = 0
    scale_label: str = ""


SCALE_BANDS = {
    # min/max are map scale denominators. Example: 1:500 => @map_scale = 500.
    "city": (
        ("500-2500", 0, 2500, 5.4),
        ("2500-10000", 2500, 10000, 5.0),
        ("10000-50000", 10000, 50000, 4.6),
        ("50000-200000", 50000, 200000, 4.1),
    ),
    "village": (
        ("500-2500", 0, 2500, 4.8),
        ("2500-10000", 2500, 10000, 4.4),
        ("10000-50000", 10000, 50000, 4.0),
        ("50000-100000", 50000, 100000, 3.7),
    ),
    "city_district": (
        ("500-2500", 0, 2500, 4.2),
        ("2500-10000", 2500, 10000, 3.9),
        ("10000-25000", 10000, 25000, 3.6),
    ),
    "village_part": (
        ("500-2500", 0, 2500, 3.9),
        ("2500-10000", 2500, 10000, 3.6),
    ),
    "municipality": (
        ("10000-50000", 10000, 50000, 4.2),
        ("50000-200000", 50000, 200000, 3.9),
    ),
    "road_number": (
        ("500-2500", 0, 2500, 4.4),
        ("2500-10000", 2500, 10000, 4.1),
        ("10000-50000", 10000, 50000, 3.8),
        ("50000-200000", 50000, 200000, 3.5),
    ),
    "major_road_name": (
        ("500-2500", 0, 2500, 4.0),
        ("2500-10000", 2500, 10000, 3.7),
        ("10000-50000", 10000, 50000, 3.4),
    ),
    "river": (
        ("500-2500", 0, 2500, 4.1),
        ("2500-10000", 2500, 10000, 3.8),
        ("10000-50000", 10000, 50000, 3.5),
        ("50000-200000", 50000, 200000, 3.2),
    ),
    "canal": (
        ("500-2500", 0, 2500, 3.7),
        ("2500-10000", 2500, 10000, 3.4),
        ("10000-25000", 10000, 25000, 3.1),
    ),
    "water_area": (
        ("500-2500", 0, 2500, 4.2),
        ("2500-10000", 2500, 10000, 3.9),
        ("10000-50000", 10000, 50000, 3.6),
        ("50000-200000", 50000, 200000, 3.3),
    ),
}


SPECS = (
    LabelSpec(
        "city",
        "OT_ADMS_P",
        "miasta",
        "place_upper",
        "city",
        "point",
        3.2,
        (28, 24, 20),
        (248, 244, 226),
        0.35,
        bold=True,
        priority=10,
    ),
    LabelSpec(
        "village",
        "OT_ADMS_P",
        "wsie",
        "place",
        "village",
        "point",
        2.45,
        (36, 31, 25),
        (248, 244, 226),
        0.3,
        priority=9,
    ),
    LabelSpec(
        "city_district",
        "OT_ADMS_P",
        "osiedla i czesci wiekszych miast",
        "place",
        "city_district",
        "point",
        2.2,
        (72, 62, 47),
        (248, 244, 226),
        0.25,
        italic=True,
        priority=8,
    ),
    LabelSpec(
        "village_part",
        "OT_ADMS_P",
        "czesci wsi kolonie osady",
        "place",
        "village_part",
        "point",
        1.95,
        (86, 74, 55),
        (248, 244, 226),
        0.23,
        italic=True,
        priority=6,
    ),
    LabelSpec(
        "municipality",
        "OT_ADJA_A",
        "nazwy gmin",
        "admin_name",
        "municipality",
        "polygon",
        2.35,
        (92, 78, 58),
        (248, 244, 226),
        0.25,
        italic=True,
        priority=5,
    ),
    LabelSpec(
        "road_number",
        "OT_SKJZ_L",
        "numery autostrad ekspresowych krajowych",
        "road_number",
        "road_number",
        "line",
        2.1,
        (255, 255, 255),
        (255, 255, 255),
        0.0,
        family="Liberation Sans",
        bold=True,
        priority=10,
    ),
    LabelSpec(
        "major_road_name",
        "OT_SKJZ_L",
        "nazwy autostrad ekspresowych krajowych",
        "road_name",
        "major_road",
        "line",
        1.9,
        (61, 49, 37),
        (248, 244, 226),
        0.25,
        family="Liberation Sans",
        italic=True,
        priority=8,
    ),
    LabelSpec(
        "river",
        "OT_SWRS_L",
        "nazwy rzek",
        "name",
        "current",
        "line",
        2.0,
        (34, 86, 128),
        (238, 244, 232),
        0.22,
        italic=True,
        priority=7,
    ),
    LabelSpec(
        "canal",
        "OT_SWKN_L",
        "nazwy kanalow",
        "name",
        "current",
        "line",
        1.75,
        (34, 86, 128),
        (238, 244, 232),
        0.2,
        italic=True,
        priority=6,
    ),
    LabelSpec(
        "water_area",
        "OT_PTWP_A",
        "nazwy zbiornikow",
        "name",
        "current",
        "polygon",
        2.15,
        (34, 86, 128),
        (238, 244, 232),
        0.22,
        italic=True,
        priority=7,
    ),
)


def apply_topo_90s_labels_to_project(iface=None, project=None):
    """Create label-only BDOT10k overlays for all matching project layers."""
    project = project or QgsProject.instance()
    removed = _remove_previous_layers(project)
    group = _ensure_group(project)

    created = 0
    skipped = []
    source_layers = _collect_source_layers(project, deduplicate=True)

    for spec in SPECS:
        for layer in source_layers.get(spec.source_code, []):
            expression = _expression_for(layer, spec.expression_kind)
            if not expression:
                skipped.append(f"{layer.name()} / {spec.layer_suffix}: brak pola")
                continue

            clone = _clone_layer(layer, spec)
            if not clone:
                skipped.append(f"{layer.name()} / {spec.layer_suffix}: niepoprawna kopia")
                continue

            subset = _subset_for(layer, spec.subset_kind)
            if subset:
                clone.setSubsetString(subset)

            _make_label_only(clone)
            _apply_labeling(clone, spec, expression)
            clone.setCustomProperty(CUSTOM_PROPERTY, "1")
            clone.setCustomProperty(f"{CUSTOM_PROPERTY}/source_layer_id", layer.id())

            project.addMapLayer(clone, False)
            group.addLayer(clone)
            created += 1

    if iface is not None:
        iface.mapCanvas().refreshAllLayers()

    return {
        "created": created,
        "removed": removed,
        "skipped": skipped,
        "group": GROUP_NAME,
    }


def apply_topo_90s_labels_in_place(iface=None, project=None):
    """Apply topo-style labels directly to existing BDOT10k layers.

    This keeps the current renderer/symbolization intact and replaces only the
    labeling configuration on matching BDOT10k source layers.
    """
    project = project or QgsProject.instance()
    changed = 0
    skipped = []
    source_layers = _collect_source_layers(project, deduplicate=False)

    for source_code, layers in source_layers.items():
        source_specs = [spec for spec in SPECS if spec.source_code == source_code]
        if not source_specs:
            continue

        for layer in layers:
            specs = _specs_for_existing_layer(layer, source_specs)
            applied, reason = _apply_specs_to_existing_layer(layer, specs)
            if applied:
                layer.setCustomProperty(IN_PLACE_PROPERTY, "1")
                changed += 1
            elif reason:
                skipped.append(f"{layer.name()}: {reason}")

    if iface is not None:
        iface.mapCanvas().refreshAllLayers()

    return {
        "changed": changed,
        "skipped": skipped,
    }


def _apply_specs_to_existing_layer(layer, specs):
    rule_items = []
    for spec in specs:
        expression = _expression_for(layer, spec.expression_kind)
        if not expression:
            continue

        subset_expression = _subset_for(layer, spec.subset_kind)
        for scaled_spec in _scaled_specs(spec):
            settings = _label_settings(scaled_spec, expression)
            filter_expression = _join_and([
                subset_expression,
                _road_number_spacing_expression(scaled_spec),
                _scale_expression(scaled_spec),
            ])
            rule_items.append((scaled_spec, settings, filter_expression))

    if not rule_items:
        return False, "brak pasujacych pol dla etykiet"

    if len(rule_items) == 1 or QgsRuleBasedLabeling is None:
        spec, settings, filter_expression = rule_items[0]
        if filter_expression:
            settings.dataDefinedProperties().setProperty(
                _pal_property("Show", default=20),
                _expression_to_property(f"({filter_expression})"),
            )
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    else:
        root = QgsRuleBasedLabeling.Rule(QgsPalLayerSettings())
        for spec, settings, filter_expression in rule_items:
            rule = QgsRuleBasedLabeling.Rule(settings)
            rule.setDescription(spec.layer_suffix)
            if filter_expression:
                rule.setFilterExpression(filter_expression)
            root.appendChild(rule)
        layer.setLabeling(QgsRuleBasedLabeling(root))

    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return True, None


def _remove_previous_layers(project):
    layer_ids = [
        layer.id()
        for layer in project.mapLayers().values()
        if layer.customProperty(CUSTOM_PROPERTY) == "1"
    ]
    if layer_ids:
        project.removeMapLayers(layer_ids)

    root = project.layerTreeRoot()
    for group_name in (GROUP_NAME,) + LEGACY_GROUP_NAMES:
        group = root.findGroup(group_name)
        if group is not None and not group.children():
            root.removeChildNode(group)

    return len(layer_ids)


def _ensure_group(project):
    root = project.layerTreeRoot()
    group = root.findGroup(GROUP_NAME)
    if group is None:
        group = root.insertGroup(0, GROUP_NAME)
    return group


def _collect_source_layers(project, deduplicate=True):
    by_code = {}
    seen = set()
    for layer in project.mapLayers().values():
        if layer.customProperty(CUSTOM_PROPERTY) == "1":
            continue
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            continue

        code = _bdot_code(layer)
        if not code:
            continue

        source_key = (code, _source_without_subset(layer.source()))
        if deduplicate and source_key in seen:
            continue
        seen.add(source_key)
        by_code.setdefault(code, []).append(layer)
    return by_code


def _specs_for_existing_layer(layer, source_specs):
    """Narrow rules for already split BDOT label layers."""
    name = _ascii_lower(layer.name())
    keys = []

    if "numery" in name and "drog" in name:
        keys = ["road_number"]
    elif "nazwy ulic" in name or "nazwy drog" in name or "wiekszych drog" in name:
        keys = ["major_road_name"]
    elif "nazwy miast" in name and "czesci" not in name:
        keys = ["city"]
    elif "nazwy wsi" in name and "czesci" not in name:
        keys = ["village"]
    elif "czesci miast" in name or "osiedl" in name or "dzielnic" in name:
        keys = ["city_district"]
    elif "czesci wsi" in name or "kolonii" in name or "osad" in name:
        keys = ["village_part"]
    elif "gmin" in name:
        keys = ["municipality"]
    elif "nazwy rzek" in name:
        keys = ["river"]
    elif "nazwy kanal" in name:
        keys = ["canal"]
    elif "nazwy zbiornik" in name:
        keys = ["water_area"]

    if keys:
        selected = [spec for spec in source_specs if spec.key in keys]
        if selected:
            return selected
    return source_specs


def _ascii_lower(value):
    replacements = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
    }
    text = value.lower()
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def _bdot_code(layer):
    haystack = f"{layer.name()} {layer.source()}".upper()
    for spec in SPECS:
        if spec.source_code in haystack:
            return spec.source_code
    return None


def _source_without_subset(source):
    return source.split("|subset=", 1)[0].split("|SUBSET=", 1)[0]


def _clone_layer(layer, spec):
    provider = layer.providerType()
    source = _source_without_subset(layer.source())
    clone_name = f"{GROUP_NAME} - {spec.layer_suffix} - {layer.name()}"
    clone = QgsVectorLayer(source, clone_name, provider)
    if not clone.isValid():
        return None
    try:
        clone.setCrs(layer.crs())
    except (RuntimeError, SystemError):
        pass
    return clone


def _make_label_only(layer):
    try:
        layer.setRenderer(QgsNullSymbolRenderer())
    except (RuntimeError, SystemError):
        pass
    layer.setLabelsEnabled(True)


def _apply_labeling(layer, spec, expression):
    scaled_specs = _scaled_specs(spec)
    if QgsRuleBasedLabeling and len(scaled_specs) > 1:
        root = QgsRuleBasedLabeling.Rule(QgsPalLayerSettings())
        for scaled_spec in scaled_specs:
            settings = _label_settings(scaled_spec, expression)
            rule = QgsRuleBasedLabeling.Rule(settings)
            rule.setDescription(_rule_description(scaled_spec))
            filter_expression = _join_and([
                _road_number_spacing_expression(scaled_spec),
                _scale_expression(scaled_spec),
            ])
            if filter_expression:
                rule.setFilterExpression(filter_expression)
            root.appendChild(rule)
        layer.setLabeling(QgsRuleBasedLabeling(root))
    else:
        settings = _label_settings(scaled_specs[0], expression)
        filter_expression = _join_and([
            _road_number_spacing_expression(scaled_specs[0]),
            _scale_expression(scaled_specs[0]),
        ])
        if filter_expression:
            settings.dataDefinedProperties().setProperty(
                _pal_property("Show", default=20),
                _expression_to_property(filter_expression),
            )
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.triggerRepaint()


def _label_settings(spec, expression):
    settings = QgsPalLayerSettings()
    settings.fieldName = expression
    settings.isExpression = True
    settings.priority = spec.priority
    settings.obstacle = False

    if spec.geometry_kind == "line":
        settings.placement = _pal_enum("Curved", "Line", default=3)
        settings.placementFlags = _pal_enum("OnLine", default=2)
        if spec.key == "road_number":
            settings.repeatDistance = 2000
            settings.repeatDistanceUnit = _MAP_UNITS
            if hasattr(settings, "labelPerPart"):
                settings.labelPerPart = False
            if hasattr(settings, "minFeatureSize"):
                settings.minFeatureSize = 1800
        else:
            settings.repeatDistance = 90
            settings.repeatDistanceUnit = _MM_UNITS
        settings.mergeLines = True
    elif spec.geometry_kind == "polygon":
        settings.placement = _pal_enum("Horizontal", "AroundPoint", default=0)
        settings.centroidInside = True
    else:
        settings.placement = _pal_enum("AroundPoint", "OverPoint", default=0)
        settings.dist = 1.2
        settings.distUnits = _MM_UNITS

    settings.setFormat(_text_format(spec))
    return settings


def _scaled_specs(spec):
    bands = SCALE_BANDS.get(spec.key)
    if not bands:
        return [spec]
    return [
        replace(
            spec,
            size_mm=size_mm,
            scale_min=scale_min,
            scale_max=scale_max,
            scale_label=label,
        )
        for label, scale_min, scale_max, size_mm in bands
    ]


def _scale_expression(spec):
    parts = []
    if spec.scale_min:
        parts.append(f"@map_scale >= {spec.scale_min}")
    if spec.scale_max:
        parts.append(f"@map_scale < {spec.scale_max}")
    return " AND ".join(parts)


def _road_number_spacing_expression(spec):
    if spec.key != "road_number":
        return ""
    return "length($geometry) >= 1800"


def _rule_description(spec):
    if spec.scale_label:
        return f"{spec.layer_suffix} 1:{spec.scale_label}"
    return spec.layer_suffix


def _pal_property(name, default):
    try:
        from qgis.core import QgsPalLayerSettings

        if hasattr(QgsPalLayerSettings, name):
            return getattr(QgsPalLayerSettings, name)
    except ImportError:
        pass
    return default


def _expression_to_property(expression):
    try:
        from qgis.core import QgsProperty

        return QgsProperty.fromExpression(expression)
    except ImportError:
        return expression


def _text_format(spec):
    font = QFont(spec.family)
    font.setBold(spec.bold)
    font.setItalic(spec.italic)

    fmt = QgsTextFormat()
    fmt.setFont(font)
    fmt.setSize(spec.size_mm)
    fmt.setSizeUnit(_MM_UNITS)
    fmt.setColor(QColor(*spec.color))

    buffer = QgsTextBufferSettings()
    if spec.key == "road_number":
        buffer.setEnabled(False)
        _apply_road_shield_background(fmt)
    else:
        buffer.setEnabled(True)
        buffer.setSize(spec.buffer_mm)
        buffer.setSizeUnit(_MM_UNITS)
        buffer.setColor(QColor(*spec.buffer_color))
        if hasattr(buffer, "setOpacity"):
            buffer.setOpacity(0.88)
    fmt.setBuffer(buffer)
    return fmt


def _apply_road_shield_background(fmt):
    if not hasattr(fmt, "background"):
        return

    background = fmt.background()
    background.setEnabled(True)

    if QgsTextBackgroundSettings is not None:
        _set_if_available(
            background,
            "setType",
            QgsTextBackgroundSettings,
            ("ShapeRectangle", "Rectangle"),
        )
        _set_if_available(
            background,
            "setSizeType",
            QgsTextBackgroundSettings,
            ("SizeBuffer", "Buffer"),
        )

    if hasattr(background, "setFillColor"):
        background.setFillColor(QColor(178, 24, 28))
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
            background.setSize(QSizeF(1.15, 0.55))
        except TypeError:
            pass

    if hasattr(fmt, "setBackground"):
        fmt.setBackground(background)


def _set_if_available(target, setter_name, enum_owner, enum_names):
    setter = getattr(target, setter_name, None)
    if setter is None:
        return
    for enum_name in enum_names:
        if hasattr(enum_owner, enum_name):
            setter(getattr(enum_owner, enum_name))
            return


def _pal_enum(*names, default):
    for name in names:
        if hasattr(QgsPalLayerSettings, name):
            return getattr(QgsPalLayerSettings, name)
    return default


def _expression_for(layer, kind):
    if kind == "place_upper":
        field = _field(layer, ("nazwa", "NAZWA"))
        return f'upper("{field}")' if field else None
    if kind in ("place", "name"):
        field = _field(
            layer,
            (
                "nazwa",
                "NAZWA",
                "nazwaGlowna",
                "NAZWAGLOWN",
                "nazwaCieku",
                "NAZWACIEKU",
            ),
        )
        return f'"{field}"' if field else None
    if kind == "admin_name":
        field = _field(
            layer,
            (
                "nazwa",
                "NAZWA",
                "nazwaJednostki",
                "NAZWAJEDN",
                "nazwaJednostkiAdministracyjnej",
                "NAZWAJEDNOSTKIADMINISTRACYJNEJ",
                "JPT_NAZWA_",
                "JPT_NAZWA",
                "NAZWA_GMI",
            ),
        )
        return f'"{field}"' if field else None
    if kind == "road_number":
        number_field = _road_number_field(layer)
        if not number_field:
            return None

        class_field = _road_class_field(layer)
        category_field = _field(
            layer,
            (
                "kategoriaZarzadzania",
                "KATZARZADZ",
                "katZarzadzania",
                "KATZARZ",
            ),
        )
        return _road_number_expression(number_field, class_field, category_field)
    if kind == "road_name":
        fields = _layer_field_map(layer)
        road_name = _field_from_map(fields, ("nazwaDrogi", "NAZWADROGI"))
        if road_name:
            return f'"{road_name}"'

        prefix = _field_from_map(
            fields,
            ("ulicaNazwa2", "ULICANAZWA2", "przedrostek2", "PRZEDROST2"),
        )
        name = _field_from_map(
            fields,
            ("ulicaNazwa1", "ULICANAZWA1", "nazwa1", "NAZWA1", "nazwa", "NAZWA"),
        )
        if prefix and name:
            return f'trim(concat(coalesce("{prefix}", \'\'), \' \', coalesce("{name}", \'\')))'
        if name:
            return f'"{name}"'
    return None


def _subset_for(layer, kind):
    parts = [_current_feature_subset(layer)]

    if kind == "city":
        parts.append(_kind_subset(layer, ("miasto",)))
    elif kind == "village":
        parts.append(_kind_subset(layer, ("wies", "wieś")))
    elif kind == "city_district":
        parts.append(
            _kind_subset(
                layer,
                (
                    "czescMiasta",
                    "część miasta",
                    "czesc miasta",
                    "dzielnica",
                    "dzielnica miasta",
                    "czescDzielnicy",
                    "część dzielnicy",
                    "czesc dzielnicy",
                    "jednostkaPomocnicza",
                    "jednostka pomocnicza",
                    "osiedle",
                ),
            )
        )
    elif kind == "village_part":
        parts.append(_kind_subset(layer, ("czescWsi", "część wsi", "kolonia", "osada")))
    elif kind == "municipality":
        parts.append(_admin_unit_subset(layer))
    elif kind == "road_number":
        parts.append(_not_empty_subset(layer, _road_number_field_candidates()))
        parts.append(_major_road_subset(layer) or "0 = 1")
    elif kind == "major_road":
        parts.append(_major_road_subset(layer) or "0 = 1")

    return _join_and([part for part in parts if part])


def _current_feature_subset(layer):
    field = _field(layer, ("koniecWersjiObiektu", "KONWERSJI", "KONIECWERS"))
    return f'"{field}" IS NULL' if field else None


def _kind_subset(layer, values):
    field = _field(layer, ("rodzaj", "RODZAJ"))
    if not field:
        return None
    quoted = ", ".join(_quote_sql(value) for value in values)
    return f'"{field}" IN ({quoted})'


def _admin_unit_subset(layer):
    field = _field(
        layer,
        (
            "rodzaj",
            "RODZAJ",
            "rodzajJednostki",
            "RODZAJJEDN",
            "rodzajJednostkiAdministracyjnej",
            "RODZAJJEDNOSTKIADMINISTRACYJNEJ",
            "JPT_KOD_JE",
            "JPT_SJR_KO",
        ),
    )
    if not field:
        return None

    values = (
        "gmina",
        "gmina miejska",
        "gmina wiejska",
        "gmina miejsko-wiejska",
        "GM",
        "GW",
        "GMW",
    )
    quoted = ", ".join(_quote_sql(value) for value in values)
    return f'"{field}" IN ({quoted})'


def _not_empty_subset(layer, candidates):
    field = _field(layer, candidates)
    if not field:
        return None
    return f'("{field}" IS NOT NULL AND "{field}" <> \'\')'


def _major_road_subset(layer):
    class_field = _road_class_field(layer)
    category_field = _field(
        layer,
        (
            "kategoriaZarzadzania",
            "KATZARZADZ",
            "katZarzadzania",
            "KATZARZ",
        ),
    )
    number_field = _road_number_field(layer)

    parts = []
    class_values = _road_class_values()
    category_values = _national_road_category_values()

    if class_field:
        quoted = ", ".join(_quote_sql(value) for value in class_values)
        parts.append(f'"{class_field}" IN ({quoted})')
    if category_field:
        quoted = ", ".join(_quote_sql(value) for value in category_values)
        parts.append(f'"{category_field}" IN ({quoted})')
    if number_field:
        parts.append(
            _join_or(
                [
                    f'"{number_field}" LIKE \'A%\'',
                    f'"{number_field}" LIKE \'a%\'',
                    f'"{number_field}" LIKE \'S%\'',
                    f'"{number_field}" LIKE \'s%\'',
                    f'"{number_field}" LIKE \'DK%\'',
                    f'"{number_field}" LIKE \'Dk%\'',
                    f'"{number_field}" LIKE \'dk%\'',
                ]
            )
        )

    return _join_or(parts)


def _road_number_expression(number_field, class_field=None, category_field=None):
    number = f'trim(coalesce("{number_field}", \'\'))'
    upper_number = f"upper({number})"
    stripped_number = f"regexp_replace({upper_number}, '\\\\s+', '')"
    numeric_number = f"regexp_replace({upper_number}, '[^0-9]', '')"
    cases = [
        (
            f"regexp_match({upper_number}, '^A\\\\s*[0-9]')",
            stripped_number,
        ),
        (
            f"regexp_match({upper_number}, '^S\\\\s*[0-9]')",
            stripped_number,
        ),
        (
            f"regexp_match({upper_number}, '^DK\\\\s*[0-9]')",
            f"concat('DK ', {numeric_number})",
        ),
    ]

    if class_field:
        class_expr = _field_in_expression(class_field, _road_class_values("autostrada"))
        cases.append(
            (
                f"{class_expr} AND regexp_match({upper_number}, '^[0-9]+')",
                f"concat('A', {upper_number})",
            )
        )

        class_expr = _field_in_expression(class_field, _road_class_values("ekspresowa"))
        cases.append(
            (
                f"{class_expr} AND regexp_match({upper_number}, '^[0-9]+')",
                f"concat('S', {upper_number})",
            )
        )

    if category_field:
        category_expr = _field_in_expression(
            category_field,
            _national_road_category_values(),
        )
        cases.append(
            (
                f"{category_expr} AND regexp_match({upper_number}, '^[0-9]+')",
                f"concat('DK ', {upper_number})",
            )
        )

    case_lines = ["CASE"]
    case_lines.extend(f"WHEN {condition} THEN {value}" for condition, value in cases)
    case_lines.append("END")
    return " ".join(case_lines)


def _field_in_expression(field, values):
    quoted = ", ".join(_quote_sql(_ascii_lower(value)) for value in values)
    return f'lower("{field}") IN ({quoted})'


def _road_class_values(kind=None):
    autostrada = ("autostrada", "A", "a", "droga klasy A", "klasa A")
    ekspresowa = (
        "ekspresowa",
        "droga ekspresowa",
        "drogaEkspresowa",
        "S",
        "s",
        "droga klasy S",
        "klasa S",
    )
    if kind == "autostrada":
        return autostrada
    if kind == "ekspresowa":
        return ekspresowa
    return autostrada + ekspresowa


def _road_number_field(layer):
    return _field(layer, _road_number_field_candidates())


def _road_number_field_candidates():
    return (
        "numerDrogi",
        "NUMERDROGI",
        "nrDrogi",
        "NRDROGI",
        "nr_drogi",
        "NR_DROGI",
        "numer",
        "NUMER",
    )


def _road_class_field(layer):
    return _field(
        layer,
        (
            "klasaDrogi",
            "KLASADROGI",
            "klasa",
            "KLASA",
            "klasaTechniczna",
            "KLASATECH",
        ),
    )


def _national_road_category_values():
    return (
        "drogaKrajowa",
        "droga krajowa",
        "krajowa",
        "DK",
    )


def _join_and(parts):
    clean = [part for part in parts if part]
    if not clean:
        return ""
    return " AND ".join(f"({part})" for part in clean)


def _join_or(parts):
    clean = [part for part in parts if part]
    if not clean:
        return None
    return " OR ".join(f"({part})" for part in clean)


def _quote_sql(value):
    return "'" + value.replace("'", "''") + "'"


def _field(layer, candidates):
    return _field_from_map(_layer_field_map(layer), candidates)


def _field_from_map(fields, candidates):
    for candidate in candidates:
        exact = fields.get(candidate)
        if exact:
            return exact
        lowered = fields.get(candidate.lower())
        if lowered:
            return lowered
    return None


def _layer_field_map(layer):
    result = {}
    for field in layer.fields():
        name = field.name()
        result[name] = name
        result[name.lower()] = name
    return result
