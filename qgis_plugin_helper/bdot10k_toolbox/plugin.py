"""Main plugin class for BDOT10k Toolbox — unified download & import."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QInputDialog, QLineEdit, QMessageBox

from .ui_dialog import DownloadDialog
from .downloader import Downloader
from .loader import load_bdot10k_folder
from .style_fixer import fix_all_layers
from .teryt_registry import get_powiat_name
from .topo_90s_labels import (
    apply_topo_90s_labels_in_place,
    apply_topo_90s_labels_to_project,
)
from .layer_manager import BdotLayerManagerDialog
from .osm_labels import DEFAULT_OVERPASS_ENDPOINT, download_osm_labels_for_canvas


class BDOT10kToolbox:
    def __init__(self, iface, toolbar=None):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "QGIS Plugin Helper"
        self._shared_toolbar = toolbar
        self.toolbar = None
        self.dlg = None
        self.layer_manager_dlg = None
        self.downloader = None

    def initGui(self):
        if self._shared_toolbar is None:
            self.toolbar = self.iface.addToolBar("BDOT10k Toolbox")
            self.toolbar.setObjectName("BDOT10kToolbox")
        else:
            self.toolbar = self._shared_toolbar

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        # Unified BDOT10k action
        action_main = QAction(
            icon, "BDOT10k — Pobierz i importuj / Download & Import",
            self.iface.mainWindow()
        )
        action_main.triggered.connect(self.show_dialog)
        self.iface.addPluginToMenu(self.menu, action_main)
        self.toolbar.addAction(action_main)
        self.actions.append(action_main)

        # Fix styles action
        action_fix = QAction(
            icon,
            "Fix BDOT10k styles (KOD10K → x_kodKarto10k)",
            self.iface.mainWindow(),
        )
        action_fix.triggered.connect(self.run_style_fix)
        self.iface.addPluginToMenu(self.menu, action_fix)
        self.actions.append(action_fix)

        action_topo_labels = QAction(
            icon,
            "BDOT10k etykiety — zastosuj do obecnych warstw",
            self.iface.mainWindow(),
        )
        action_topo_labels.triggered.connect(self.run_topo_90s_labels_in_place)
        self.iface.addPluginToMenu(self.menu, action_topo_labels)
        self.actions.append(action_topo_labels)

        action_topo_overlay = QAction(
            icon,
            "BDOT10k etykiety — utworz kopie label-only",
            self.iface.mainWindow(),
        )
        action_topo_overlay.triggered.connect(self.run_topo_90s_label_overlay)
        self.iface.addPluginToMenu(self.menu, action_topo_overlay)
        self.actions.append(action_topo_overlay)

        action_osm_labels = QAction(
            icon,
            "OSM etykiety — pobierz dla aktualnego BBOX",
            self.iface.mainWindow(),
        )
        action_osm_labels.triggered.connect(self.run_osm_bbox_labels)
        self.iface.addPluginToMenu(self.menu, action_osm_labels)
        self.actions.append(action_osm_labels)

        action_layer_manager = QAction(
            icon,
            "BDOT10k — wspolne warstwy / merge powiatow",
            self.iface.mainWindow(),
        )
        action_layer_manager.triggered.connect(self.show_layer_manager)
        self.iface.addPluginToMenu(self.menu, action_layer_manager)
        self.actions.append(action_layer_manager)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        if self._shared_toolbar is None and self.toolbar:
            del self.toolbar
        self.layer_manager_dlg = None

    def show_dialog(self):
        if self.dlg is None:
            self.dlg = DownloadDialog(self.iface.mainWindow())
            self.dlg.btn_download.clicked.connect(self._start_download)
            self.dlg.btn_cancel.clicked.connect(self._cancel_download)
            self.dlg.btn_import.clicked.connect(self._start_import)
        self.dlg.show()
        self.dlg.raise_()

    def show_layer_manager(self):
        self.layer_manager_dlg = BdotLayerManagerDialog(
            self.iface,
            self.iface.mainWindow(),
        )
        self.layer_manager_dlg.show()
        self.layer_manager_dlg.raise_()

    # ── Download flow ─────────────────────────────────────────────────────

    def _start_download(self):
        dlg = self.dlg
        teryts = dlg.get_selected_teryts()
        if not teryts:
            QMessageBox.warning(
                dlg, "BDOT10k",
                "Wybierz co najmniej jeden powiat.\n"
                "Select at least one powiat.",
            )
            return

        dest = dlg.edit_dest.text().strip()
        if not dest or not os.path.isdir(dest):
            QMessageBox.warning(
                dlg, "BDOT10k",
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

        self.downloader.download(
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
                    dlg.lbl_status.setText(
                        f"Wczytywanie / Loading {name}..."
                    )
                    load_bdot10k_folder(
                        r.path, apply_styles=apply_styles,
                    )

        dlg.lbl_status.setText("Gotowy / Ready")
        dlg.show_summary(results)

    # ── Import flow ───────────────────────────────────────────────────────

    def _start_import(self):
        dlg = self.dlg
        folder = dlg.edit_import_folder.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(
                dlg, "BDOT10k",
                "Podaj prawidłowy folder z danymi BDOT10k.\n"
                "Provide a valid folder with BDOT10k data.",
            )
            return

        apply_styles = dlg.chk_import_style.isChecked()

        dlg.set_downloading(True)
        dlg.lbl_status.setText("Importowanie / Importing...")

        from .loader import find_bdot10k_data_dirs
        data_dirs = find_bdot10k_data_dirs(folder)

        if not data_dirs:
            dlg.set_downloading(False)
            QMessageBox.warning(
                dlg, "BDOT10k",
                "Nie znaleziono danych BDOT10k w wybranym folderze.\n"
                "No BDOT10k data found in the selected folder.",
            )
            return

        dlg.progress_total.setMaximum(len(data_dirs))
        dlg.progress_total.setValue(0)

        layers = load_bdot10k_folder(folder, apply_styles=apply_styles)

        dlg.progress_total.setValue(len(data_dirs))
        dlg.set_downloading(False)
        dlg.lbl_status.setText("Gotowy / Ready")

        QMessageBox.information(
            dlg, "BDOT10k",
            f"Zaimportowano {len(layers)} warstw z {len(data_dirs)} "
            f"zbiorów danych.\n"
            f"Imported {len(layers)} layers from {len(data_dirs)} datasets.",
        )

    # ── Style fix ─────────────────────────────────────────────────────────

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

    # ── BDOT10k label styling ────────────────────────────────────────────

    def run_topo_90s_labels_in_place(self):
        result = apply_topo_90s_labels_in_place(self.iface)
        changed = result["changed"]
        skipped = len(result["skipped"])
        if changed:
            self.iface.messageBar().pushSuccess(
                "BDOT10k",
                f"Wystylizowano etykiety BDOT10k na {changed} "
                f"obecnych warstwach. Pominieto: {skipped}.",
            )
        else:
            self.iface.messageBar().pushWarning(
                "BDOT10k",
                "Nie znaleziono obecnych warstw BDOT10k z pasujacymi polami.",
            )

    def run_topo_90s_label_overlay(self):
        result = apply_topo_90s_labels_to_project(self.iface)
        created = result["created"]
        removed = result["removed"]
        skipped = len(result["skipped"])
        if created:
            self.iface.messageBar().pushSuccess(
                "BDOT10k",
                f"Utworzono {created} warstw label-only BDOT10k. "
                f"Usunieto poprzednie: {removed}. Pominieto: {skipped}.",
            )
        else:
            self.iface.messageBar().pushWarning(
                "BDOT10k",
                "Nie znaleziono warstw BDOT10k do utworzenia etykiet.",
            )

    def run_osm_bbox_labels(self):
        endpoint, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "OSM etykiety",
            "Overpass API URL (dla OSM lub kompatybilnego zrodla):",
            QLineEdit.Normal,
            DEFAULT_OVERPASS_ENDPOINT,
        )
        if not ok:
            return

        endpoint = endpoint.strip() or DEFAULT_OVERPASS_ENDPOINT
        try:
            result = download_osm_labels_for_canvas(self.iface, endpoint=endpoint)
        except Exception as exc:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "OSM etykiety",
                f"Nie udalo sie pobrac etykiet OSM dla aktualnego BBOX.\n\n{exc}",
            )
            return

        self.iface.messageBar().pushSuccess(
            "OSM etykiety",
            f"Dodano {result['created']} warstw label-only. "
            f"Miejscowosci: {result['places']}, tarcze drog: {result['road_shields']}. "
            f"Usunieto poprzednie: {result['removed']}.",
        )
