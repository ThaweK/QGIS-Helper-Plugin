"""Download dialog for CAA-PL Obstacle Explorer."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QCheckBox,
    QTreeWidget,
    QTreeWidgetItem,
    QProgressBar,
    QTextEdit,
    QHeaderView,
    QAbstractItemView,
)


class ExplorerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CAA-PL Obstacle Explorer")
        self.setMinimumSize(700, 550)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── Options ──
        opt_group = QGroupBox("Opcje / Options")
        opt_layout = QVBoxLayout(opt_group)

        self.chk_bbox = QCheckBox(
            "Filtruj do zasięgu mapy / Filter to current map extent"
        )
        self.chk_bbox.setChecked(False)
        opt_layout.addWidget(self.chk_bbox)

        self.chk_load = QCheckBox(
            "Wczytaj do QGIS / Load into QGIS"
        )
        self.chk_load.setChecked(True)
        opt_layout.addWidget(self.chk_load)

        layout.addWidget(opt_group)

        # ── Discover button ──
        btn_row = QHBoxLayout()
        self.btn_discover = QPushButton("Odkryj warstwy / Discover Layers")
        self.btn_discover.setMinimumHeight(32)
        btn_row.addWidget(self.btn_discover)
        layout.addLayout(btn_row)

        # ── Layer tree ──
        layer_group = QGroupBox("Warstwy / Layers")
        layer_layout = QVBoxLayout(layer_group)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Warstwa / Layer", "Typ geometrii / Geometry", "Obiekty / Features", "Mozliwosc zapytania / Queryable"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layer_layout.addWidget(self.tree)

        sel_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Zaznacz wszystkie / Select All")
        self.btn_deselect_all = QPushButton("Odznacz wszystkie / Deselect All")
        sel_row.addWidget(self.btn_select_all)
        sel_row.addWidget(self.btn_deselect_all)
        sel_row.addStretch()
        layer_layout.addLayout(sel_row)

        layout.addWidget(layer_group)

        # ── Download button ──
        self.btn_download = QPushButton("Pobierz zaznaczone / Download Selected")
        self.btn_download.setMinimumHeight(36)
        self.btn_download.setEnabled(False)
        layout.addWidget(self.btn_download)

        # ── Progress ──
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_status = QLabel("Gotowy / Ready")
        layout.addWidget(self.lbl_status)

        # ── Log ──
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        self.log.setVisible(False)
        layout.addWidget(self.log)

        # ── Wire selection buttons ──
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect_all.clicked.connect(self._deselect_all)

    def _select_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Checked)

    def _deselect_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)

    def populate_layers(self, layer_infos):
        """
        Populate tree with inspected layer metadata.
        layer_infos: list of dicts from explorer.inspect_layer().
        """
        self.tree.clear()
        for info in layer_infos:
            if info is None:
                continue
            item = QTreeWidgetItem()
            item.setText(0, info.get("name", "Unknown"))
            item.setText(1, (info.get("geometryType") or "N/A").replace("esriGeometry", ""))
            count = info.get("featureCount", "?")
            item.setText(2, str(count))
            item.setText(3, "Yes" if info.get("queryable") else "No")
            item.setCheckState(0, Qt.Checked if info.get("queryable") else Qt.Unchecked)
            item.setData(0, Qt.UserRole, info)
            if not info.get("queryable"):
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(item)

        self.btn_download.setEnabled(self.tree.topLevelItemCount() > 0)

    def get_checked_layers(self):
        """Return list of layer info dicts for checked items."""
        results = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                info = item.data(0, Qt.UserRole)
                if info:
                    results.append(info)
        return results

    def set_busy(self, busy):
        self.btn_discover.setEnabled(not busy)
        self.btn_download.setEnabled(not busy)
        self.progress.setVisible(busy)
        self.log.setVisible(busy)
        if busy:
            self.progress.setRange(0, 0)  # indeterminate

    def log_message(self, msg):
        self.log.append(msg)
        self.lbl_status.setText(msg)
