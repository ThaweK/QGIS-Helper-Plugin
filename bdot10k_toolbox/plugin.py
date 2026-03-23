"""Main plugin class for BDOT10k Toolbox."""

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

from .ui_dialog import DownloadDialog
from .downloader import Downloader
from .loader import load_bdot10k_folder
from .style_fixer import fix_all_layers
from .teryt_registry import get_powiat_name


class BDOT10kToolbox:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "BDOT10k Toolbox"
        self.toolbar = self.iface.addToolBar("BDOT10k Toolbox")
        self.toolbar.setObjectName("BDOT10kToolbox")
        self.dlg = None
        self.downloader = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        # Download action
        action_download = QAction(
            icon, "BDOT10k — Pobierz / Download", self.iface.mainWindow()
        )
        action_download.triggered.connect(self.show_download_dialog)
        self.iface.addPluginToMenu(self.menu, action_download)
        self.toolbar.addAction(action_download)
        self.actions.append(action_download)

        # Fix styles action
        action_fix = QAction(
            icon,
            "Fix BDOT10k styles (KOD10K → x_kodKarto10k)",
            self.iface.mainWindow(),
        )
        action_fix.triggered.connect(self.run_style_fix)
        self.iface.addPluginToMenu(self.menu, action_fix)
        self.actions.append(action_fix)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def show_download_dialog(self):
        if self.dlg is None:
            self.dlg = DownloadDialog(self.iface.mainWindow())
            self.dlg.btn_download.clicked.connect(self._start_download)
            self.dlg.btn_cancel.clicked.connect(self._cancel_download)
        self.dlg.show()
        self.dlg.raise_()

    def _start_download(self):
        dlg = self.dlg
        teryts = dlg.get_selected_teryts()
        if not teryts:
            QMessageBox.warning(
                dlg,
                "BDOT10k",
                "Wybierz co najmniej jeden powiat.\n"
                "Select at least one powiat.",
            )
            return

        dest = dlg.edit_dest.text().strip()
        if not dest or not os.path.isdir(dest):
            QMessageBox.warning(
                dlg,
                "BDOT10k",
                "Podaj prawidłowy folder docelowy.\n"
                "Provide a valid destination folder.",
            )
            return

        fmt = dlg.get_format()
        timeout = dlg.spin_timeout.value()
        extract = dlg.chk_extract.isChecked()

        dlg.set_downloading(True)
        dlg.lbl_status.setText("Rozpoczynam pobieranie / Starting download...")

        self.downloader = Downloader(self.dlg)
        self.downloader.progress_file.connect(dlg.update_file_progress)
        self.downloader.progress_total.connect(dlg.update_total_progress)
        self.downloader.status_changed.connect(dlg.lbl_status.setText)
        self.downloader.download_finished.connect(
            lambda results: self._on_download_finished(results)
        )

        # Run download (blocking but with processEvents for UI responsiveness)
        results = self.downloader.download(
            teryts, dest, fmt=fmt, timeout=timeout, extract=extract
        )

    def _cancel_download(self):
        if self.downloader:
            self.downloader.cancel()
            self.dlg.lbl_status.setText("Anulowanie / Cancelling...")

    def _on_download_finished(self, results):
        dlg = self.dlg
        dlg.set_downloading(False)
        dlg.lbl_status.setText("Zakończono / Finished")

        # Load into QGIS if requested
        if dlg.chk_load.isChecked():
            apply_styles = dlg.chk_style.isChecked()
            for r in results:
                if r.success and r.path and os.path.isdir(r.path):
                    name = get_powiat_name(r.teryt) or r.teryt
                    group_name = f"BDOT10k — {name} ({r.teryt})"
                    dlg.lbl_status.setText(
                        f"Wczytywanie / Loading {name}..."
                    )
                    load_bdot10k_folder(
                        r.path,
                        group_name=group_name,
                        apply_styles=apply_styles,
                    )

        dlg.lbl_status.setText("Gotowy / Ready")
        dlg.show_summary(results)

    def run_style_fix(self):
        count = fix_all_layers()
        if count > 0:
            self.iface.messageBar().pushSuccess(
                "BDOT10k",
                f"Naprawiono {count} warstw / Fixed {count} layers "
                f"(KOD10K → x_kodKarto10k)",
            )
        else:
            self.iface.messageBar().pushInfo(
                "BDOT10k",
                "Nie znaleziono warstw do naprawy / "
                "No layers needed fixing.",
            )
