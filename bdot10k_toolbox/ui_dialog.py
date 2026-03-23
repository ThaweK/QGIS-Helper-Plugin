"""Download dialog UI for BDOT10k Toolbox."""

import os
import time

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
    QLineEdit, QPushButton, QFileDialog, QProgressBar,
    QCheckBox, QSpinBox, QGroupBox, QMessageBox,
    QAbstractItemView, QDialogButtonBox, QApplication,
)

from .teryt_registry import WOJEWODZTWA, POWIATY, get_display_name


class DownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BDOT10k Toolbox — Pobieranie / Download")
        self.setMinimumWidth(550)
        self.setMinimumHeight(650)
        self._download_start_time = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_elapsed)

        self._build_ui()
        self._connect_signals()
        self._populate_woj()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Województwo
        lbl_woj = QLabel("Województwo:")
        self.combo_woj = QComboBox()
        layout.addWidget(lbl_woj)
        layout.addWidget(self.combo_woj)

        # Powiat list
        lbl_pow = QLabel("Powiaty (multi-select / wielokrotny wybór):")
        self.list_powiaty = QListWidget()
        self.list_powiaty.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(lbl_pow)
        layout.addWidget(self.list_powiaty)

        # Select all / deselect
        btn_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Zaznacz wszystkie / Select all")
        self.btn_deselect = QPushButton("Odznacz / Deselect")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_deselect)
        layout.addLayout(btn_row)

        # Format
        fmt_group = QGroupBox("Format danych / Data format")
        fmt_layout = QHBoxLayout()
        self.fmt_group = QButtonGroup(self)
        self.radio_gml = QRadioButton("GML")
        self.radio_shp = QRadioButton("SHP")
        self.radio_gpkg = QRadioButton("GPKG")
        self.radio_gml.setChecked(True)
        self.fmt_group.addButton(self.radio_gml)
        self.fmt_group.addButton(self.radio_shp)
        self.fmt_group.addButton(self.radio_gpkg)
        fmt_layout.addWidget(self.radio_gml)
        fmt_layout.addWidget(self.radio_shp)
        fmt_layout.addWidget(self.radio_gpkg)
        fmt_group.setLayout(fmt_layout)
        layout.addWidget(fmt_group)

        # Destination
        dest_layout = QHBoxLayout()
        self.edit_dest = QLineEdit()
        self.edit_dest.setPlaceholderText(
            "Folder docelowy / Destination folder..."
        )
        self.btn_browse = QPushButton("...")
        self.btn_browse.setMaximumWidth(40)
        dest_layout.addWidget(self.edit_dest)
        dest_layout.addWidget(self.btn_browse)
        layout.addLayout(dest_layout)

        # Timeout
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Timeout (s):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(60, 7200)
        self.spin_timeout.setValue(600)
        timeout_layout.addWidget(self.spin_timeout)
        timeout_layout.addStretch()
        layout.addLayout(timeout_layout)

        # Options
        self.chk_extract = QCheckBox(
            "Rozpakuj ZIP / Extract ZIP"
        )
        self.chk_extract.setChecked(True)
        self.chk_load = QCheckBox(
            "Wczytaj do QGIS / Load into QGIS"
        )
        self.chk_load.setChecked(True)
        self.chk_style = QCheckBox(
            "Zastosuj styl topo / Apply topo styling"
        )
        self.chk_style.setChecked(True)
        layout.addWidget(self.chk_extract)
        layout.addWidget(self.chk_load)
        layout.addWidget(self.chk_style)

        # File progress
        layout.addWidget(QLabel("Postęp pliku / File progress:"))
        self.progress_file = QProgressBar()
        self.progress_file.setTextVisible(True)
        self.progress_file.setFormat("%v / %m B")
        layout.addWidget(self.progress_file)

        # Elapsed timer label
        self.lbl_elapsed = QLabel("")
        layout.addWidget(self.lbl_elapsed)

        # Total progress
        layout.addWidget(QLabel("Postęp ogólny / Total progress:"))
        self.progress_total = QProgressBar()
        self.progress_total.setTextVisible(True)
        layout.addWidget(self.progress_total)

        # Status
        self.lbl_status = QLabel("Gotowy / Ready")
        layout.addWidget(self.lbl_status)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_download = QPushButton("Pobierz / Download")
        self.btn_cancel = QPushButton("Anuluj / Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_close = QPushButton("Zamknij / Close")
        btn_layout.addWidget(self.btn_download)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        self.combo_woj.currentIndexChanged.connect(self._on_woj_changed)
        self.btn_browse.clicked.connect(self._browse_folder)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_deselect.clicked.connect(self._deselect_all)
        self.btn_close.clicked.connect(self.close)
        self.chk_load.toggled.connect(
            lambda checked: self.chk_style.setEnabled(checked)
        )

    def _populate_woj(self):
        self.combo_woj.blockSignals(True)
        self.combo_woj.clear()
        self.combo_woj.addItem("— Wybierz województwo / Select voivodeship —", "")
        for code in sorted(WOJEWODZTWA.keys()):
            name = WOJEWODZTWA[code]
            self.combo_woj.addItem(f"{name} ({code})", code)
        self.combo_woj.blockSignals(False)

    def _on_woj_changed(self, index):
        self.list_powiaty.clear()
        woj_code = self.combo_woj.currentData()
        if not woj_code or woj_code not in POWIATY:
            return
        for teryt, name in POWIATY[woj_code]:
            item = QListWidgetItem(get_display_name(teryt, name))
            item.setData(Qt.UserRole, teryt)
            self.list_powiaty.addItem(item)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Wybierz folder / Select folder"
        )
        if folder:
            self.edit_dest.setText(folder)

    def _select_all(self):
        self.list_powiaty.selectAll()

    def _deselect_all(self):
        self.list_powiaty.clearSelection()

    def get_selected_teryts(self):
        return [
            item.data(Qt.UserRole)
            for item in self.list_powiaty.selectedItems()
        ]

    def get_format(self):
        if self.radio_shp.isChecked():
            return "SHP"
        if self.radio_gpkg.isChecked():
            return "GPKG"
        return "GML"

    def set_downloading(self, active):
        self.btn_download.setEnabled(not active)
        self.btn_cancel.setEnabled(active)
        self.combo_woj.setEnabled(not active)
        self.list_powiaty.setEnabled(not active)
        if active:
            self._download_start_time = time.time()
            self._timer.start(1000)
        else:
            self._timer.stop()
            self._download_start_time = None

    def update_file_progress(self, received, total):
        if total > 0:
            self.progress_file.setMaximum(total)
            self.progress_file.setValue(received)
            mb_recv = received / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            pct = int(received * 100 / total)
            self.progress_file.setFormat(
                f"{mb_recv:.1f} / {mb_total:.1f} MB ({pct}%)"
            )
        else:
            self.progress_file.setMaximum(0)
            self.progress_file.setValue(0)
            if received > 0:
                mb = received / (1024 * 1024)
                self.progress_file.setFormat(f"{mb:.1f} MB...")

    def update_total_progress(self, current, total, ok, fail):
        self.progress_total.setMaximum(total)
        self.progress_total.setValue(current)
        self.progress_total.setFormat(
            f"{current} / {total} packages (ok: {ok}  fail: {fail})"
        )

    def _update_elapsed(self):
        if self._download_start_time:
            elapsed = int(time.time() - self._download_start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.lbl_elapsed.setText(f"Czas / Elapsed: {mins}:{secs:02d}")

    def show_summary(self, results):
        ok = [r for r in results if r.success]
        fail = [r for r in results if not r.success]

        msg = f"Pobrano / Downloaded: {len(ok)}\n"
        msg += f"Błędy / Errors: {len(fail)}\n\n"

        if ok:
            msg += "Sukces / Success:\n"
            for r in ok:
                size_mb = r.size / (1024 * 1024) if r.size else 0
                msg += f"  {r.name} ({r.teryt}) — {size_mb:.1f} MB\n"

        if fail:
            msg += "\nBłędy / Failures:\n"
            for r in fail:
                msg += f"  {r.name} ({r.teryt}): {r.error}\n"

        QMessageBox.information(self, "BDOT10k — Podsumowanie / Summary", msg)
