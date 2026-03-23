"""Main plugin class for CAA-PL Obstacle Explorer."""

import json
import os
import tempfile

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsLayerTreeGroup,
    QgsCoordinateReferenceSystem,
)

from .dialog import ExplorerDialog
from . import explorer


class DiscoverWorker(QThread):
    """Background thread for layer discovery + inspection."""
    progress = pyqtSignal(str)
    finished_discovery = pyqtSignal(list)  # list of layer_info dicts

    def __init__(self, app_id):
        super().__init__()
        self.app_id = app_id

    def run(self):
        entries = explorer.discover_layers(
            app_id=self.app_id,
            progress_callback=lambda msg: self.progress.emit(msg),
        )

        layer_infos = []
        for i, entry in enumerate(entries):
            self.progress.emit(
                f"Inspekcja warstwy / Inspecting layer {i+1}/{len(entries)}: {entry['title']}..."
            )
            info = explorer.inspect_layer(entry["url"], progress_callback=lambda msg: self.progress.emit(msg))
            if info:
                layer_infos.append(info)

        self.finished_discovery.emit(layer_infos)


class DownloadWorker(QThread):
    """Background thread for downloading selected layers."""
    progress = pyqtSignal(str)
    layer_ready = pyqtSignal(str, str)  # (layer_name, geojson_path)
    finished_download = pyqtSignal()

    def __init__(self, layers, bbox=None):
        super().__init__()
        self.layers = layers
        self.bbox = bbox

    def run(self):
        for info in self.layers:
            name = info["name"]
            url = info["url"]
            self.progress.emit(f"Pobieranie / Downloading: {name}...")

            features = explorer.download_features(
                url,
                bbox=self.bbox,
                progress_callback=lambda msg: self.progress.emit(msg),
            )

            if features:
                geojson = explorer.esri_features_to_geojson(features)
                safe_name = name.replace(" ", "_").replace("/", "_")
                tmp_path = os.path.join(tempfile.gettempdir(), f"caa_{safe_name}.geojson")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(geojson, f, ensure_ascii=False)
                self.progress.emit(
                    f"Pobrano {len(features)} obiektow / Downloaded {len(features)} features: {name}"
                )
                self.layer_ready.emit(name, tmp_path)
            else:
                self.progress.emit(f"Brak obiektow / No features: {name}")

        self.finished_download.emit()


class CAAObstacleExplorer:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "CAA-PL Obstacle Explorer"
        self.toolbar = None
        self.dlg = None
        self._discover_worker = None
        self._download_worker = None
        self._pending_layers = []

    def initGui(self):
        self.toolbar = self.iface.addToolBar("CAA-PL Obstacle Explorer")
        self.toolbar.setObjectName("CAAObstacleExplorer")

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        action = QAction(
            icon,
            "CAA-PL Obstacle Explorer",
            self.iface.mainWindow(),
        )
        action.triggered.connect(self.show_dialog)
        self.iface.addPluginToMenu(self.menu, action)
        self.toolbar.addAction(action)
        self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        if self.toolbar:
            del self.toolbar

    def show_dialog(self):
        if self.dlg is None:
            self.dlg = ExplorerDialog(self.iface.mainWindow())
            self.dlg.btn_discover.clicked.connect(self._on_discover)
            self.dlg.btn_download.clicked.connect(self._on_download)
        self.dlg.show()
        self.dlg.raise_()

    # ── Discovery ─────────────────────────────────────────────────────────

    def _on_discover(self):
        self.dlg.set_busy(True)
        self.dlg.log_message("Rozpoczynam odkrywanie warstw / Starting layer discovery...")

        self._discover_worker = DiscoverWorker(explorer.APP_ID)
        self._discover_worker.progress.connect(self.dlg.log_message)
        self._discover_worker.finished_discovery.connect(self._on_discover_finished)
        self._discover_worker.start()

    def _on_discover_finished(self, layer_infos):
        self.dlg.populate_layers(layer_infos)
        self.dlg.set_busy(False)
        self.dlg.log_message(
            f"Odkrywanie zakonczone. Znaleziono {len(layer_infos)} warstw / "
            f"Discovery complete. Found {len(layer_infos)} layers."
        )
        self._discover_worker = None

    # ── Download ──────────────────────────────────────────────────────────

    def _on_download(self):
        checked = self.dlg.get_checked_layers()
        if not checked:
            self.dlg.log_message("Brak zaznaczonych warstw / No layers selected")
            return

        bbox = None
        if self.dlg.chk_bbox.isChecked():
            extent = self.iface.mapCanvas().extent()
            # Transform to WGS84 if needed
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            if canvas_crs.authid() != "EPSG:4326":
                from qgis.core import QgsCoordinateTransform
                transform = QgsCoordinateTransform(
                    canvas_crs,
                    QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance(),
                )
                extent = transform.transformBoundingBox(extent)
            bbox = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())

        self._pending_layers = []
        self.dlg.set_busy(True)
        self.dlg.progress.setRange(0, len(checked))
        self.dlg.progress.setValue(0)

        self._download_worker = DownloadWorker(checked, bbox=bbox)
        self._download_worker.progress.connect(self.dlg.log_message)
        self._download_worker.layer_ready.connect(self._on_layer_ready)
        self._download_worker.finished_download.connect(self._on_download_finished)
        self._download_worker.start()

    def _on_layer_ready(self, name, geojson_path):
        """Called from worker thread — queue layer for loading on main thread."""
        self._pending_layers.append((name, geojson_path))
        self.dlg.progress.setValue(len(self._pending_layers))

    def _on_download_finished(self):
        self._download_worker = None

        if self.dlg.chk_load.isChecked() and self._pending_layers:
            self._load_layers()

        self.dlg.set_busy(False)
        count = len(self._pending_layers)
        self.dlg.log_message(
            f"Pobieranie zakonczone. {count} warstw / Download complete. {count} layers."
        )
        self._pending_layers = []

    def _load_layers(self):
        """Load downloaded GeoJSON files into QGIS."""
        root = QgsProject.instance().layerTreeRoot()
        group = root.insertGroup(0, "CAA-PL Obstacles")

        for name, path in self._pending_layers:
            self.dlg.log_message(f"Wczytywanie / Loading: {name}...")
            vlayer = QgsVectorLayer(path, name, "ogr")
            if vlayer.isValid():
                QgsProject.instance().addMapLayer(vlayer, False)
                group.addLayer(vlayer)
            else:
                self.dlg.log_message(f"Blad wczytywania / Load error: {name}")

        self.iface.mapCanvas().refresh()
