"""Dialog for configuring a smart Print Layout map grid."""

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


class SmartGridDialog(QDialog):
    """Collect settings for automatic layout grid generation."""

    def __init__(self, map_item, map_info, selected_count=1, layout_count=1, parent=None):
        super().__init__(parent)
        self.map_item = map_item
        self.selected_count = selected_count
        self.layout_count = layout_count
        self.setWindowTitle("Automatyczna siatka ukladu / Smart Layout Grid")
        self.setMinimumWidth(560)
        self._build_ui(map_info)
        self._connect_signals()
        self._update_enabled()

    def _build_ui(self, map_info):
        root = QVBoxLayout(self)

        info = QLabel(map_info)
        info.setWordWrap(True)
        root.addWidget(info)

        scope_group = QGroupBox("Zakres / Scope")
        scope_form = QFormLayout(scope_group)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Tylko aktywny view", "current")
        if self.selected_count > 1:
            self.scope_combo.addItem(f"Wszystkie zaznaczone view ({self.selected_count})", "selected")
        if self.layout_count > 1:
            self.scope_combo.addItem(f"Wszystkie view w layoucie ({self.layout_count})", "layout")
        scope_form.addRow("Ustaw siatke dla:", self.scope_combo)
        root.addWidget(scope_group)

        target_group = QGroupBox("Uklad wspolrzednych / Coordinate system")
        target_form = QFormLayout(target_group)

        self.crs_mode_combo = QComboBox()
        self.crs_mode_combo.addItem("Lokalny CRS mapy / Local map CRS", "local")
        self.crs_mode_combo.addItem("WGS84 (EPSG:4326)", "wgs84")
        self.crs_mode_combo.addItem("Wlasny EPSG / Custom EPSG", "custom")
        target_form.addRow("CRS siatki:", self.crs_mode_combo)

        self.custom_epsg_edit = QLineEdit()
        self.custom_epsg_edit.setPlaceholderText("np. EPSG:2180")
        target_form.addRow("Wlasny CRS:", self.custom_epsg_edit)

        root.addWidget(target_group)

        interval_group = QGroupBox("Gestosc siatki / Grid density")
        interval_form = QFormLayout(interval_group)

        self.interval_mode_combo = QComboBox()
        self.interval_mode_combo.addItem("Auto: ladny odstep z rozmiaru mapy", "auto")
        self.interval_mode_combo.addItem("Po liczbie kresek w polu widzenia", "count")
        self.interval_mode_combo.addItem("Reczny odstep wspolrzednych", "manual")
        interval_form.addRow("Tryb:", self.interval_mode_combo)

        count_row = QHBoxLayout()
        self.target_x_spin = QSpinBox()
        self.target_x_spin.setRange(2, 50)
        self.target_x_spin.setValue(6)
        self.target_y_spin = QSpinBox()
        self.target_y_spin.setRange(2, 50)
        self.target_y_spin.setValue(6)
        count_row.addWidget(QLabel("X:"))
        count_row.addWidget(self.target_x_spin)
        count_row.addWidget(QLabel("Y:"))
        count_row.addWidget(self.target_y_spin)
        count_row.addStretch()
        interval_form.addRow("Liczba linii:", count_row)

        self.min_spacing_spin = QDoubleSpinBox()
        self.min_spacing_spin.setRange(8.0, 120.0)
        self.min_spacing_spin.setValue(30.0)
        self.min_spacing_spin.setSingleStep(2.0)
        self.min_spacing_spin.setSuffix(" mm")
        interval_form.addRow("Min. odstep na papierze:", self.min_spacing_spin)

        manual_row = QHBoxLayout()
        self.manual_x_spin = QDoubleSpinBox()
        self.manual_x_spin.setRange(0.000001, 1000000000.0)
        self.manual_x_spin.setDecimals(6)
        self.manual_x_spin.setValue(1000.0)
        self.manual_y_spin = QDoubleSpinBox()
        self.manual_y_spin.setRange(0.000001, 1000000000.0)
        self.manual_y_spin.setDecimals(6)
        self.manual_y_spin.setValue(1000.0)
        manual_row.addWidget(QLabel("X:"))
        manual_row.addWidget(self.manual_x_spin)
        manual_row.addWidget(QLabel("Y:"))
        manual_row.addWidget(self.manual_y_spin)
        interval_form.addRow("Reczny odstep:", manual_row)

        self.edge_mode_combo = QComboBox()
        self.edge_mode_combo.addItem("Bez wymuszania skrajnych kresek", "none")
        self.edge_mode_combo.addItem("Wymus pierwsza kreske od lewej/dolu", "first")
        self.edge_mode_combo.addItem("Wymus pierwsza i ostatnia na krawedziach", "both")
        interval_form.addRow("Skrajne kreski:", self.edge_mode_combo)

        root.addWidget(interval_group)

        style_group = QGroupBox("Wyglad / Appearance")
        style_form = QFormLayout(style_group)

        self.grid_style_combo = QComboBox()
        self.grid_style_combo.addItem("Krzyzyki wewnatrz mapy", "cross")
        self.grid_style_combo.addItem("Pelne linie", "solid")
        self.grid_style_combo.addItem("Tylko ramka i opisy", "frame_annotations")
        style_form.addRow("Styl siatki:", self.grid_style_combo)

        self.frame_style_combo = QComboBox()
        self.frame_style_combo.addItem("Ramka zebra", "zebra")
        self.frame_style_combo.addItem("Kreski na zewnatrz", "exterior_ticks")
        self.frame_style_combo.addItem("Prosta ramka", "line_border")
        self.frame_style_combo.addItem("Bez ramki", "none")
        style_form.addRow("Ramka:", self.frame_style_combo)

        self.annotation_format_combo = QComboBox()
        self.annotation_format_combo.addItem("Auto", "auto")
        self.annotation_format_combo.addItem("Dziesietnie", "decimal")
        self.annotation_format_combo.addItem("DMS", "dms")
        style_form.addRow("Format opisow:", self.annotation_format_combo)

        self.annotations_checkbox = QCheckBox("Pokaz opisy wspolrzednych przy ramce")
        self.annotations_checkbox.setChecked(True)
        style_form.addRow("", self.annotations_checkbox)

        self.replace_checkbox = QCheckBox("Aktualizuj istniejaca siatke helpera, jesli istnieje")
        self.replace_checkbox.setChecked(True)
        style_form.addRow("", self.replace_checkbox)

        root.addWidget(style_group)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)
        self._set_summary()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _connect_signals(self):
        self.scope_combo.currentIndexChanged.connect(self._set_summary)
        self.crs_mode_combo.currentIndexChanged.connect(self._update_enabled)
        self.crs_mode_combo.currentIndexChanged.connect(self._set_summary)
        self.interval_mode_combo.currentIndexChanged.connect(self._update_enabled)
        self.interval_mode_combo.currentIndexChanged.connect(self._set_summary)
        self.edge_mode_combo.currentIndexChanged.connect(self._set_summary)
        self.target_x_spin.valueChanged.connect(self._set_summary)
        self.target_y_spin.valueChanged.connect(self._set_summary)
        self.min_spacing_spin.valueChanged.connect(self._set_summary)
        self.manual_x_spin.valueChanged.connect(self._set_summary)
        self.manual_y_spin.valueChanged.connect(self._set_summary)

    def _update_enabled(self, *_args):
        crs_mode = self.crs_mode_combo.currentData()
        interval_mode = self.interval_mode_combo.currentData()
        self.custom_epsg_edit.setEnabled(crs_mode == "custom")
        self.target_x_spin.setEnabled(interval_mode == "count")
        self.target_y_spin.setEnabled(interval_mode == "count")
        self.min_spacing_spin.setEnabled(interval_mode == "auto")
        self.manual_x_spin.setEnabled(interval_mode == "manual")
        self.manual_y_spin.setEnabled(interval_mode == "manual")

        geographic = crs_mode == "wgs84"
        suffix = " deg" if geographic else " map units"
        self.manual_x_spin.setSuffix(suffix)
        self.manual_y_spin.setSuffix(suffix)
        if geographic and self.manual_x_spin.value() > 10:
            self.manual_x_spin.setValue(0.01)
            self.manual_y_spin.setValue(0.01)

    def _set_summary(self, *_args):
        mode = self.interval_mode_combo.currentData()
        edge = self.edge_mode_combo.currentData()
        scope = self.scope_combo.currentData()
        if mode == "auto":
            text = "Auto dobierze ladny odstep tak, zeby linie nie byly gesciej niz ustawiony dystans na papierze."
        elif mode == "count":
            text = "Tryb liczby linii celuje w podana liczbe kresek X/Y w aktualnym polu widzenia mapy."
        else:
            text = "Tryb reczny uzyje dokladnego odstepu wspolrzednych X/Y."
        if scope in ("selected", "layout"):
            text += " Kazdy view bedzie przeliczony osobno z wlasnego rozmiaru i zasiegu."
        if edge == "both":
            text += " Skrajne linie beda dopasowane do krawedzi mapy, wiec odstep moze nie byc okragly."
        elif edge == "first":
            text += " Pierwsza linia zostanie zakotwiczona na lewej/dolnej krawedzi mapy."
        self.summary_label.setText(text)

    def settings(self):
        return {
            "scope": self.scope_combo.currentData(),
            "crs_mode": self.crs_mode_combo.currentData(),
            "custom_epsg": self.custom_epsg_edit.text().strip(),
            "interval_mode": self.interval_mode_combo.currentData(),
            "target_x": self.target_x_spin.value(),
            "target_y": self.target_y_spin.value(),
            "min_spacing_mm": self.min_spacing_spin.value(),
            "manual_x": self.manual_x_spin.value(),
            "manual_y": self.manual_y_spin.value(),
            "edge_mode": self.edge_mode_combo.currentData(),
            "grid_style": self.grid_style_combo.currentData(),
            "frame_style": self.frame_style_combo.currentData(),
            "annotation_format": self.annotation_format_combo.currentData(),
            "annotations": self.annotations_checkbox.isChecked(),
            "replace_existing": self.replace_checkbox.isChecked(),
        }
