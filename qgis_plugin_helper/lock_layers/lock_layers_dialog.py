"""Dialog for locking layers on a Print Layout map item."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QCheckBox,
    QLabel,
    QAbstractItemView,
)
from qgis.core import QgsProject


class LockLayersDialog(QDialog):
    """Dialog to lock/unlock layers on a QgsLayoutItemMap."""

    def __init__(self, map_item, parent=None):
        super().__init__(parent)
        self.map_item = map_item
        self.setWindowTitle(
            "Zablokuj warstwy / Lock Layers"
        )
        self.setMinimumSize(450, 400)
        self._build_ui()
        self._populate_layers()
        self._update_mode()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Mode selection ──
        mode_group = QGroupBox("Tryb / Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_group = QButtonGroup(self)
        self.radio_visible = QRadioButton(
            "Zablokuj aktualnie widoczne warstwy / Lock currently visible layers"
        )
        self.radio_manual = QRadioButton(
            "Wybierz warstwy ręcznie / Select layers manually"
        )
        self.radio_visible.setChecked(True)
        self.mode_group.addButton(self.radio_visible)
        self.mode_group.addButton(self.radio_manual)
        mode_layout.addWidget(self.radio_visible)
        mode_layout.addWidget(self.radio_manual)
        layout.addWidget(mode_group)

        # ── Layer list ──
        list_group = QGroupBox("Warstwy / Layers")
        list_layout = QVBoxLayout(list_group)

        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QAbstractItemView.MultiSelection)
        list_layout.addWidget(self.layer_list)

        sel_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Zaznacz wszystkie / Select All")
        self.btn_deselect_all = QPushButton("Odznacz wszystkie / Deselect All")
        sel_row.addWidget(self.btn_select_all)
        sel_row.addWidget(self.btn_deselect_all)
        sel_row.addStretch()
        list_layout.addLayout(sel_row)

        layout.addWidget(list_group)

        # ── Unlock option ──
        self.chk_unlock = QCheckBox(
            "Odblokuj warstwy (usuń blokadę) / Unlock layers (remove lock)"
        )
        layout.addWidget(self.chk_unlock)

        # ── Status label ──
        self.lbl_status = QLabel()
        self._update_status_label()
        layout.addWidget(self.lbl_status)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Zastosuj / Apply")
        self.btn_apply.setMinimumHeight(34)
        self.btn_close = QPushButton("Zamknij / Close")
        btn_row.addStretch()
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        # ── Signals ──
        self.radio_visible.toggled.connect(self._update_mode)
        self.radio_manual.toggled.connect(self._update_mode)
        self.chk_unlock.toggled.connect(self._on_unlock_toggled)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all.clicked.connect(self._deselect_all)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_close.clicked.connect(self.close)

    def _populate_layers(self):
        """Fill the layer list from the project layer tree order."""
        self.layer_list.clear()
        root = QgsProject.instance().layerTreeRoot()
        visible_ids = set()

        for node in root.findLayers():
            if node.isVisible():
                visible_ids.add(node.layerId())

        for node in root.findLayers():
            layer = node.layer()
            if layer is None:
                continue
            item = QListWidgetItem(layer.name())
            item.setData(Qt.UserRole, layer.id())
            self.layer_list.addItem(item)
            if layer.id() in visible_ids:
                item.setSelected(True)

    def _update_mode(self):
        """Enable/disable layer list based on selected mode."""
        manual = self.radio_manual.isChecked()
        self.layer_list.setEnabled(manual)
        self.btn_select_all.setEnabled(manual)
        self.btn_deselect_all.setEnabled(manual)

    def _on_unlock_toggled(self, checked):
        """Disable mode/layer controls when unlock is checked."""
        enabled = not checked
        self.radio_visible.setEnabled(enabled)
        self.radio_manual.setEnabled(enabled)
        self.layer_list.setEnabled(enabled and self.radio_manual.isChecked())
        self.btn_select_all.setEnabled(enabled and self.radio_manual.isChecked())
        self.btn_deselect_all.setEnabled(enabled and self.radio_manual.isChecked())

    def _update_status_label(self):
        locked = self.map_item.keepLayerSet()
        if locked:
            count = len(self.map_item.layers())
            self.lbl_status.setText(
                f"Status: zablokowane ({count} warstw) / locked ({count} layers)"
            )
        else:
            self.lbl_status.setText(
                "Status: odblokowane / unlocked"
            )

    def _select_all(self):
        self.layer_list.selectAll()

    def _deselect_all(self):
        self.layer_list.clearSelection()

    def _get_selected_layers(self):
        """Return list of QgsMapLayer for selected items."""
        project = QgsProject.instance()
        layers = []
        for item in self.layer_list.selectedItems():
            layer_id = item.data(Qt.UserRole)
            layer = project.mapLayer(layer_id)
            if layer:
                layers.append(layer)
        return layers

    def _get_visible_layers(self):
        """Return list of QgsMapLayer for currently visible layers."""
        root = QgsProject.instance().layerTreeRoot()
        layers = []
        for node in root.findLayers():
            if node.isVisible() and node.layer():
                layers.append(node.layer())
        return layers

    def _apply(self):
        """Apply lock/unlock to the map item."""
        if self.chk_unlock.isChecked():
            self.map_item.setKeepLayerSet(False)
            self.map_item.refresh()
            self._update_status_label()
            return

        if self.radio_visible.isChecked():
            layers = self._get_visible_layers()
        else:
            layers = self._get_selected_layers()

        self.map_item.setKeepLayerSet(True)
        self.map_item.setLayers(layers)
        self.map_item.refresh()
        self._update_status_label()
