"""Shared BDOT10k layer visibility and merge tools."""

import hashlib
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsField,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .loader import LAYER_DEFS

BDOT_CODE_RE = re.compile(r"OT_[A-Z0-9]{4}_[ALP]", re.IGNORECASE)
GENERATED_LABEL_PROPERTY = "qgis_plugin_helper/topo_90s_label"
KNOWN_TITLES_TO_CODE = None


@dataclass
class LayerType:
    key: str
    title: str
    code: str
    layers: list


class BdotLayerManagerDialog(QDialog):
    """Manage matching BDOT10k layer types across many powiat groups."""

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.project = QgsProject.instance()
        self.layer_types = []
        self.setWindowTitle("BDOT10k - wspolne warstwy i merge")
        self.setMinimumSize(620, 520)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self.visibility_list = QListWidget()
        self.visibility_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._build_visibility_tab()

        self.merge_list = QListWidget()
        self.merge_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._build_merge_tab()

        self.style_code_combo = QComboBox()
        self.style_source_combo = QComboBox()
        self._build_style_tab()

        self.status_label = QLabel()
        root.addWidget(self.status_label)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Odswiez / Refresh")
        self.btn_close = QPushButton("Zamknij / Close")
        row.addWidget(self.btn_refresh)
        row.addStretch()
        row.addWidget(self.btn_close)
        root.addLayout(row)

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_close.clicked.connect(self.close)

    def _build_visibility_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Zaznaczenie dotyczy typu warstwy we wszystkich grupach BDOT10k, "
            "np. we wszystkich powiatach naraz."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addWidget(self.visibility_list)

        row = QHBoxLayout()
        self.btn_vis_all = QPushButton("Zaznacz wszystkie")
        self.btn_vis_none = QPushButton("Odznacz wszystkie")
        self.btn_apply_visibility = QPushButton("Zastosuj widocznosc")
        row.addWidget(self.btn_vis_all)
        row.addWidget(self.btn_vis_none)
        row.addStretch()
        row.addWidget(self.btn_apply_visibility)
        layout.addLayout(row)

        self.btn_vis_all.clicked.connect(lambda: self._set_all(self.visibility_list, True))
        self.btn_vis_none.clicked.connect(lambda: self._set_all(self.visibility_list, False))
        self.btn_apply_visibility.clicked.connect(self.apply_visibility)
        self.tabs.addTab(tab, "Widocznosc")

    def _build_merge_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Scalanie zapisuje kazdy wybrany typ jako osobna warstwe "
            "w jednym GeoPackage."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.only_visible_checkbox = QCheckBox("Scalaj tylko aktualnie widoczne warstwy")
        layout.addWidget(self.only_visible_checkbox)
        self.load_after_merge_checkbox = QCheckBox("Wczytaj wynik do projektu w uporzadkowanej grupie")
        self.load_after_merge_checkbox.setChecked(True)
        layout.addWidget(self.load_after_merge_checkbox)
        layout.addWidget(self.merge_list)

        row = QHBoxLayout()
        self.btn_merge_all = QPushButton("Zaznacz wszystkie")
        self.btn_merge_none = QPushButton("Odznacz wszystkie")
        self.btn_merge = QPushButton("Scal do GeoPackage...")
        row.addWidget(self.btn_merge_all)
        row.addWidget(self.btn_merge_none)
        row.addStretch()
        row.addWidget(self.btn_merge)
        layout.addLayout(row)

        self.btn_merge_all.clicked.connect(lambda: self._set_all(self.merge_list, True))
        self.btn_merge_none.clicked.connect(lambda: self._set_all(self.merge_list, False))
        self.btn_merge.clicked.connect(self.merge_selected)
        self.tabs.addTab(tab, "Merge")

    def _build_style_tab(self):
        tab = QGroupBox()
        layout = QVBoxLayout(tab)

        info = QLabel(
            "Edytuj styl jednej warstwy reprezentatywnej, a potem skopiuj go "
            "na wszystkie warstwy tego samego kodu BDOT, np. OT_SKJZ_L."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("Kod BDOT:"))
        layout.addWidget(self.style_code_combo)
        layout.addWidget(QLabel("Warstwa wzorcowa:"))
        layout.addWidget(self.style_source_combo)

        row = QHBoxLayout()
        self.btn_open_style = QPushButton("Otworz edytor stylu warstwy wzorcowej")
        self.btn_apply_style = QPushButton("Zastosuj styl na wszystkie tego kodu")
        row.addWidget(self.btn_open_style)
        row.addWidget(self.btn_apply_style)
        layout.addLayout(row)

        self.style_code_combo.currentIndexChanged.connect(self._populate_style_sources)
        self.btn_open_style.clicked.connect(self.open_style_editor)
        self.btn_apply_style.clicked.connect(self.apply_style_to_code)
        self.tabs.addTab(tab, "Style")

    def refresh(self):
        self.layer_types = collect_bdot_layer_types(self.project)
        self._populate_list(self.visibility_list, checked_from_visibility=True)
        self._populate_list(self.merge_list, checked_from_visibility=False)
        self._populate_style_codes()
        total_layers = sum(len(item.layers) for item in self.layer_types)
        code_count = len(_collect_layers_by_code(self.layer_types))
        self.status_label.setText(
            f"Wykryto {len(self.layer_types)} typow BDOT10k, "
            f"{code_count} kodow, {total_layers} warstw lacznie."
        )

    def _populate_list(self, widget, checked_from_visibility):
        widget.clear()
        for layer_type in self.layer_types:
            visible_count = _visible_layer_count(layer_type.layers, self.project)
            text = (
                f"{layer_type.title}  [{layer_type.code}]  "
                f"({len(layer_type.layers)} warstw, widoczne: {visible_count})"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, layer_type.key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = visible_count > 0 if checked_from_visibility else False
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            widget.addItem(item)

    def _set_all(self, widget, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(widget.count()):
            widget.item(i).setCheckState(state)

    def apply_visibility(self):
        selected = self._checked_keys(self.visibility_list)
        count = 0
        for layer_type in self.layer_types:
            visible = layer_type.key in selected
            for layer in layer_type.layers:
                count += set_layer_tree_visibility(self.project, layer, visible)

        self.iface.mapCanvas().refreshAllLayers()
        self.refresh()
        self.status_label.setText(f"Zmieniono widocznosc {count} wpisow drzewa warstw.")

    def merge_selected(self):
        keys = self._checked_keys(self.merge_list)
        selected = [item for item in self.layer_types if item.key in keys]
        if not selected:
            QMessageBox.warning(self, "BDOT10k merge", "Wybierz co najmniej jeden typ warstwy.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz GeoPackage",
            "",
            "GeoPackage (*.gpkg)",
        )
        if not path:
            return
        if not path.lower().endswith(".gpkg"):
            path += ".gpkg"

        style_sources = choose_style_sources_for_layer_types(selected, self)
        if style_sources is None:
            return

        try:
            written = merge_layer_types_to_gpkg(
                selected,
                path,
                self.project,
                only_visible=self.only_visible_checkbox.isChecked(),
                style_sources=style_sources,
            )
        except Exception as exc:
            QMessageBox.critical(self, "BDOT10k merge", f"Merge nie powiodl sie:\n{exc}")
            return

        if written == 0:
            QMessageBox.warning(
                self,
                "BDOT10k merge",
                "Nie zapisano zadnej warstwy. Sprawdz wybor albo opcje widocznosci.",
            )
            return

        loaded = 0
        if self.load_after_merge_checkbox.isChecked():
            loaded = load_merged_gpkg_to_group(
                path,
                selected,
                self.project,
                group_name=f"BDOT10k merge - {os.path.basename(path)}",
            )
            self.iface.mapCanvas().refreshAllLayers()

        QMessageBox.information(
            self,
            "BDOT10k merge",
            f"Zapisano {written} warstw do:\n{path}\nWczytano do projektu: {loaded}.",
        )

    def _populate_style_codes(self):
        current = self.style_code_combo.currentData()
        self.style_code_combo.blockSignals(True)
        self.style_code_combo.clear()

        for code, layers in sorted(_collect_layers_by_code(self.layer_types).items()):
            label = _code_label(code, self.layer_types)
            self.style_code_combo.addItem(f"{label} ({len(layers)} warstw)", code)

        index = self.style_code_combo.findData(current)
        if index >= 0:
            self.style_code_combo.setCurrentIndex(index)
        self.style_code_combo.blockSignals(False)
        self._populate_style_sources()

    def _populate_style_sources(self, *_args):
        code = self.style_code_combo.currentData()
        self.style_source_combo.clear()
        if not code:
            return

        for layer in _collect_layers_by_code(self.layer_types).get(code, []):
            self.style_source_combo.addItem(layer.name(), layer.id())

    def _selected_style_layer(self):
        layer_id = self.style_source_combo.currentData()
        return self.project.mapLayer(layer_id) if layer_id else None

    def open_style_editor(self):
        layer = self._selected_style_layer()
        if layer is None:
            QMessageBox.warning(self, "BDOT10k style", "Wybierz warstwe wzorcowa.")
            return
        self.iface.showLayerProperties(layer)

    def apply_style_to_code(self):
        source = self._selected_style_layer()
        code = self.style_code_combo.currentData()
        if source is None or not code:
            QMessageBox.warning(self, "BDOT10k style", "Wybierz kod BDOT i warstwe wzorcowa.")
            return

        layers = [
            layer for layer in _collect_layers_by_code(self.layer_types).get(code, [])
            if layer.id() != source.id()
        ]
        if not layers:
            QMessageBox.information(self, "BDOT10k style", "Brak innych warstw do aktualizacji.")
            return

        reply = QMessageBox.question(
            self,
            "BDOT10k style",
            f"Skopiowac styl z:\n{source.name()}\n\nna {len(layers)} warstw kodu {code}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        changed = copy_layer_style_to_layers(source, layers)
        self.iface.mapCanvas().refreshAllLayers()
        QMessageBox.information(
            self,
            "BDOT10k style",
            f"Zaktualizowano styl {changed} warstw kodu {code}.",
        )

    def _checked_keys(self, widget):
        keys = set()
        for i in range(widget.count()):
            item = widget.item(i)
            if item.checkState() == Qt.Checked:
                keys.add(item.data(Qt.UserRole))
        return keys


def collect_bdot_layer_types(project=None):
    """Return BDOT layer types grouped across all powiat layer groups."""
    project = project or QgsProject.instance()
    grouped = {}

    for layer in project.mapLayers().values():
        if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
            continue
        if layer.customProperty(GENERATED_LABEL_PROPERTY) == "1":
            continue

        code = _bdot_code(layer) or _bdot_code_from_known_title(layer.name())
        if not code:
            continue

        title = _layer_title(layer.name(), code)
        key = f"{code}|{_normal_key(title)}"
        if key not in grouped:
            grouped[key] = LayerType(key, title, code, [])
        grouped[key].layers.append(layer)

    return sorted(grouped.values(), key=lambda item: (item.code, item.title.lower()))


def _code_label(code, layer_types):
    titles = sorted({
        _friendly_title(layer_type.title)
        for layer_type in layer_types
        if layer_type.code == code
    })
    if not titles:
        return code

    preview = ", ".join(titles[:4])
    if len(titles) > 4:
        preview += f", +{len(titles) - 4}"
    return f"{code} ({preview})"


def _friendly_title(title):
    title = re.sub(r"\s*\(poziom[^)]*\)", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def load_merged_gpkg_to_group(output_path, layer_types, project=None, group_name=None):
    """Load merged GPKG layers into one ordered project group."""
    project = project or QgsProject.instance()
    root = project.layerTreeRoot()
    group_name = group_name or f"BDOT10k merge - {os.path.basename(output_path)}"

    old_group = root.findGroup(group_name)
    if old_group is not None:
        root.removeChildNode(old_group)
    group = root.insertGroup(0, group_name)

    loaded = 0
    items = []
    for layer_type in layer_types:
        layer_name = _safe_gpkg_layer_name(layer_type)
        level_label, z_min, z_max = _bdot_level(layer_type.title)
        items.append((z_min if z_min is not None else -999, z_max if z_max is not None else -999, layer_name))

    # Insert ascending at index 0 so higher BDOT z-levels end up at the top.
    for _z_min, _z_max, layer_name in sorted(items):
        layer = QgsVectorLayer(f"{output_path}|layername={layer_name}", layer_name, "ogr")
        if not layer.isValid():
            continue
        if hasattr(layer, "loadDefaultStyle"):
            layer.loadDefaultStyle()
        project.addMapLayer(layer, False)
        group.insertLayer(0, layer)
        loaded += 1

    return loaded


def copy_layer_style_to_layers(source_layer, target_layers):
    """Copy renderer/labeling/style from one layer to many project layers."""
    with tempfile.NamedTemporaryFile(suffix=".qml", delete=False) as tmp:
        style_path = tmp.name

    changed = 0
    try:
        source_layer.saveNamedStyle(style_path)
        for target in target_layers:
            if not isinstance(target, QgsVectorLayer) or not target.isValid():
                continue
            target.loadNamedStyle(style_path)
            target.triggerRepaint()
            changed += 1
    finally:
        try:
            os.remove(style_path)
        except OSError:
            pass

    return changed


def _collect_layers_by_code(layer_types):
    by_code = {}
    seen = set()
    for layer_type in layer_types:
        for layer in layer_type.layers:
            if layer.id() in seen:
                continue
            seen.add(layer.id())
            by_code.setdefault(layer_type.code, []).append(layer)
    for layers in by_code.values():
        layers.sort(key=lambda layer: layer.name().lower())
    return by_code


def set_layer_tree_visibility(project, layer, visible):
    """Set visibility for every layer tree node pointing to *layer*."""
    changed = 0
    for node in project.layerTreeRoot().findLayers():
        if node.layerId() != layer.id():
            continue
        node.setItemVisibilityChecked(visible)
        changed += 1
    return changed


def choose_style_sources_for_layer_types(layer_types, parent=None):
    """Return selected style source layer for each layer type, or None on cancel."""
    style_sources = {}
    for layer_type in layer_types:
        source = _choose_style_source_for_layer_type(layer_type, parent)
        if source is None:
            return None
        style_sources[layer_type.key] = source
    return style_sources


def merge_layer_types_to_gpkg(
    layer_types,
    output_path,
    project=None,
    only_visible=False,
    style_sources=None,
):
    """Merge selected BDOT layer types into one GeoPackage.

    Each logical type is written as a separate layer inside the GeoPackage.
    """
    import processing

    project = project or QgsProject.instance()
    transform_context = project.transformContext()
    if not isinstance(transform_context, QgsCoordinateTransformContext):
        transform_context = QgsCoordinateTransformContext()

    first_write = True
    written = 0
    for layer_type in layer_types:
        layers = list(layer_type.layers)
        if only_visible:
            layers = [layer for layer in layers if _is_layer_visible(project, layer)]
        if not layers:
            continue
        layers_for_merge = [
            _layer_with_bdot_metadata(layer, layer_type)
            for layer in layers
        ]

        result = processing.run(
            "native:mergevectorlayers",
            {
                "LAYERS": layers_for_merge,
                "CRS": layers[0].crs(),
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
        )
        layer_name = _safe_gpkg_layer_name(layer_type)
        merged = _processing_output_layer(result["OUTPUT"], layer_name)
        style_source = (style_sources or {}).get(layer_type.key, layers[0])
        _write_layer_to_gpkg(
            merged,
            output_path,
            layer_name,
            transform_context,
            first_write,
            style_source=style_source,
        )
        first_write = False
        written += 1

    return written


def _layer_with_bdot_metadata(layer, layer_type):
    """Return a memory copy of *layer* with explicit BDOT metadata fields."""
    fields = layer.fields()
    metadata_names = {
        "bdot_kod",
        "bdot_typ",
        "bdot_poziom",
        "bdot_z_min",
        "bdot_z_max",
        "bdot_zrodlo",
    }
    original_fields = [
        field for field in fields
        if field.name().lower() not in metadata_names
    ]

    geom_name = QgsWkbTypes.displayString(layer.wkbType())
    crs_authid = layer.crs().authid()
    uri = f"{geom_name}?crs={crs_authid}" if crs_authid else geom_name
    memory_layer = QgsVectorLayer(uri, layer.name(), "memory")
    provider = memory_layer.dataProvider()

    provider.addAttributes(original_fields)
    provider.addAttributes([
        QgsField("bdot_kod", QVariant.String),
        QgsField("bdot_typ", QVariant.String),
        QgsField("bdot_poziom", QVariant.String),
        QgsField("bdot_z_min", QVariant.Int),
        QgsField("bdot_z_max", QVariant.Int),
        QgsField("bdot_zrodlo", QVariant.String),
    ])
    memory_layer.updateFields()

    level_label, z_min, z_max = _bdot_level(layer_type.title)
    metadata = [
        layer_type.code,
        layer_type.title,
        level_label,
        z_min,
        z_max,
        layer.name(),
    ]

    original_indexes = [fields.indexOf(field.name()) for field in original_fields]
    features = []
    for source_feature in layer.getFeatures():
        feature = QgsFeature(memory_layer.fields())
        feature.setGeometry(source_feature.geometry())
        attrs = [
            source_feature.attribute(index)
            for index in original_indexes
        ]
        feature.setAttributes(attrs + metadata)
        features.append(feature)

    provider.addFeatures(features)
    memory_layer.updateExtents()
    return memory_layer


def _bdot_level(title):
    match = re.search(r"poziom\s+([0-9]+(?:\s*(?:-|i)\s*[0-9]+)?)", title, re.I)
    if not match:
        return "", None, None

    label = re.sub(r"\s+", " ", match.group(1)).strip()
    numbers = [int(value) for value in re.findall(r"\d+", label)]
    if not numbers:
        return label, None, None
    return label, min(numbers), max(numbers)


def _choose_style_source_for_layer_type(layer_type, parent=None):
    style_groups = _group_layers_by_style(layer_type.layers)
    if len(style_groups) <= 1:
        return layer_type.layers[0] if layer_type.layers else None

    candidates = [layers[0] for layers in style_groups.values()]
    labels = [
        f"{idx + 1}. {layers[0].name()} ({len(layers)} warstw)"
        for idx, layers in enumerate(style_groups.values())
    ]

    selected, ok = QInputDialog.getItem(
        parent,
        "Rozne style BDOT10k",
        (
            f"Warstwy typu:\n{layer_type.title} [{layer_type.code}]\n\n"
            "maja rozne style. Wybierz styl do zapisania w warstwie wynikowej:"
        ),
        labels,
        0,
        False,
    )
    if not ok or not selected:
        return None

    return candidates[labels.index(selected)]


def _group_layers_by_style(layers):
    groups = {}
    for layer in layers:
        signature = _style_signature(layer)
        groups.setdefault(signature, []).append(layer)
    return groups


def _style_signature(layer):
    with tempfile.NamedTemporaryFile(suffix=".qml", delete=False) as tmp:
        style_path = tmp.name

    try:
        layer.saveNamedStyle(style_path)
        with open(style_path, "rb") as handle:
            raw = handle.read()
        normalized = _normalize_qml_style(raw)
        return hashlib.sha256(normalized).hexdigest()
    except Exception:
        fallback = f"{layer.renderer().__class__.__name__}|{bool(layer.labeling())}"
        return hashlib.sha256(fallback.encode("utf-8")).hexdigest()
    finally:
        try:
            os.remove(style_path)
        except OSError:
            pass


def _normalize_qml_style(raw):
    """Hash only visual style sections, ignoring datasource/form metadata."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return raw

    parts = []
    wanted_tags = {
        "renderer-v2",
        "labeling",
        "blendMode",
        "featureBlendMode",
        "layerOpacity",
        "SingleCategoryDiagramRenderer",
        "DiagramLayerSettings",
    }
    for element in root:
        if element.tag in wanted_tags:
            _sort_xml_attributes(element)
            parts.append(ET.tostring(element, encoding="utf-8"))
    return b"\n".join(parts) if parts else raw


def _sort_xml_attributes(element):
    if element.attrib:
        items = sorted(element.attrib.items())
        element.attrib.clear()
        element.attrib.update(dict(items))
    for child in element:
        _sort_xml_attributes(child)


def _processing_output_layer(output, layer_name):
    if isinstance(output, QgsVectorLayer):
        return output

    layer = QgsVectorLayer(str(output), layer_name, "ogr")
    if layer.isValid():
        return layer

    layer = QgsVectorLayer(str(output), layer_name, "memory")
    if layer.isValid():
        return layer

    raise RuntimeError(f"Nie mozna odczytac wyniku merge dla {layer_name}.")


def _write_layer_to_gpkg(
    layer,
    output_path,
    layer_name,
    transform_context,
    first_write,
    style_source=None,
):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    if first_write or not os.path.exists(output_path):
        options.actionOnExistingFile = _writer_action("CreateOrOverwriteFile", 0)
    else:
        options.actionOnExistingFile = _writer_action("CreateOrOverwriteLayer", 1)

    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        output_path,
        transform_context,
        options,
    )

    error_code = result[0] if isinstance(result, tuple) else result
    if error_code != QgsVectorFileWriter.NoError:
        message = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
        raise RuntimeError(f"Nie mozna zapisac warstwy {layer_name}: {message}")

    if style_source is not None:
        _copy_style_to_gpkg_layer(style_source, output_path, layer_name)


def _copy_style_to_gpkg_layer(style_source, output_path, layer_name):
    with tempfile.NamedTemporaryFile(suffix=".qml", delete=False) as tmp:
        style_path = tmp.name

    try:
        style_source.saveNamedStyle(style_path)
        target = QgsVectorLayer(f"{output_path}|layername={layer_name}", layer_name, "ogr")
        if not target.isValid():
            return

        target.loadNamedStyle(style_path)
        if hasattr(target, "saveStyleToDatabase"):
            target.saveStyleToDatabase(
                "default",
                "Copied by QGIS Plugin Helper",
                True,
                "",
            )
    finally:
        try:
            os.remove(style_path)
        except OSError:
            pass


def _writer_action(name, default):
    return getattr(QgsVectorFileWriter, name, default)


def _visible_layer_count(layers, project):
    return sum(1 for layer in layers if _is_layer_visible(project, layer))


def _is_layer_visible(project, layer):
    for node in project.layerTreeRoot().findLayers():
        if node.layerId() == layer.id() and node.isVisible():
            return True
    return False


def _bdot_code(layer):
    haystack = f"{layer.name()} {layer.source()}"
    match = BDOT_CODE_RE.search(haystack)
    return match.group(0).upper() if match else None


def _bdot_code_from_known_title(name):
    known_titles = _known_titles_to_code()
    title = _ascii_key(_layer_title(name, ""))
    code = known_titles.get(title)
    if code:
        return code

    for known_title, known_code in known_titles.items():
        if known_title and known_title in title:
            return known_code
    return None


def _known_titles_to_code():
    global KNOWN_TITLES_TO_CODE
    if KNOWN_TITLES_TO_CODE is None:
        KNOWN_TITLES_TO_CODE = {
            _ascii_key(display_suffix): source_code
            for source_code, display_suffix, _qml, _group, _xml, _shp in LAYER_DEFS
        }
    return KNOWN_TITLES_TO_CODE


def _layer_title(name, code):
    title = name.rsplit("__", 1)[-1]
    title = re.sub(r"^BDOT10k\s+napisy\s+-\s+topo\s+lata\s+90\s+-\s+", "", title, flags=re.I)
    title = re.sub(r"^BDOT10k\s+etykiety\s+-\s+", "", title, flags=re.I)
    title = re.sub(r"^PL\.PZGiK\.[^_]+__", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    return title or code


def _normal_key(value):
    value = _ascii_lower(value)
    value = re.sub(r"[^a-z0-9_() -]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _ascii_key(value):
    return _normal_key(value).lower()


def _safe_gpkg_layer_name(layer_type):
    name = f"{layer_type.code}_{_normal_key(layer_type.title)}"
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:55] or layer_type.code


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
