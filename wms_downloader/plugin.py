"""
WMS/WMTS Layer Downloader Plugin
Allows selecting a WMS/WMTS layer, drawing a bounding box on the canvas,
choosing a zoom/resolution level, and saving the result as a GeoTIFF.
"""

import os
import math
import tempfile

from qgis.PyQt.QtCore import Qt, QRectF
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QSpinBox, QDoubleSpinBox, QLabel, QPushButton,
    QFileDialog, QMessageBox, QGroupBox, QProgressBar, QLineEdit,
    QApplication
)
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsRectangle, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsRasterFileWriter, QgsRasterPipe,
    QgsRasterProjector, QgsRasterBandStats, Qgis,
    QgsMapLayerType, QgsProviderRegistry
)
from qgis.gui import QgsMapToolEmitPoint, QgsRubberBand
from qgis.core import QgsWkbTypes, QgsPointXY

import processing


class BboxMapTool(QgsMapToolEmitPoint):
    """Map tool for drawing a bounding box rectangle on the canvas."""

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.canvas = canvas
        self.callback = callback
        self.rubber_band = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(QColor(255, 0, 0, 100))
        self.rubber_band.setStrokeColor(QColor(255, 0, 0, 200))
        self.rubber_band.setWidth(2)
        self.start_point = None
        self.end_point = None
        self.is_drawing = False

    def canvasPressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = self.toMapCoordinates(event.pos())
            self.end_point = self.start_point
            self.is_drawing = True
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)

    def canvasMoveEvent(self, event):
        if not self.is_drawing:
            return
        self.end_point = self.toMapCoordinates(event.pos())
        self._update_rubber_band()

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.end_point = self.toMapCoordinates(event.pos())
            self._update_rubber_band()
            if self.start_point and self.end_point:
                rect = QgsRectangle(self.start_point, self.end_point)
                if rect.width() > 0 and rect.height() > 0:
                    self.callback(rect)

    def _update_rubber_band(self):
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        if self.start_point and self.end_point:
            p1 = self.start_point
            p2 = QgsPointXY(self.end_point.x(), self.start_point.y())
            p3 = self.end_point
            p4 = QgsPointXY(self.start_point.x(), self.end_point.y())
            self.rubber_band.addPoint(p1, False)
            self.rubber_band.addPoint(p2, False)
            self.rubber_band.addPoint(p3, False)
            self.rubber_band.addPoint(p4, True)
            self.rubber_band.show()

    def reset(self):
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.start_point = None
        self.end_point = None

    def deactivate(self):
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        super().deactivate()


class WmsDownloaderDialog(QDialog):
    """Main dialog for WMS/WMTS download configuration."""

    # Approximate meters/pixel for standard web map zoom levels (at equator)
    ZOOM_RESOLUTIONS = {
        0: 156543.0,
        1: 78271.5,
        2: 39135.8,
        3: 19567.9,
        4: 9783.9,
        5: 4892.0,
        6: 2446.0,
        7: 1223.0,
        8: 611.5,
        9: 305.7,
        10: 152.9,
        11: 76.4,
        12: 38.2,
        13: 19.1,
        14: 9.55,
        15: 4.77,
        16: 2.39,
        17: 1.19,
        18: 0.60,
        19: 0.30,
        20: 0.15,
    }

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.bbox = None
        self.map_tool = None
        self.prev_map_tool = None
        self._setup_ui()
        self._populate_layers()

    def _setup_ui(self):
        self.setWindowTitle("WMS/WMTS Downloader")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        layout = QVBoxLayout()

        # --- Layer selection ---
        layer_group = QGroupBox("1. Select WMS/WMTS Layer")
        layer_layout = QFormLayout()
        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._on_layer_changed)
        layer_layout.addRow("Layer:", self.layer_combo)
        self.layer_info_label = QLabel("No layer selected")
        self.layer_info_label.setWordWrap(True)
        self.layer_info_label.setStyleSheet("color: #666; font-size: 11px;")
        layer_layout.addRow(self.layer_info_label)
        layer_group.setLayout(layer_layout)
        layout.addWidget(layer_group)

        # --- Bounding box ---
        bbox_group = QGroupBox("2. Define Bounding Box")
        bbox_layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        self.draw_bbox_btn = QPushButton("Draw BBOX on Map")
        self.draw_bbox_btn.setToolTip("Click and drag on the map canvas to define the area")
        self.draw_bbox_btn.clicked.connect(self._start_bbox_draw)
        btn_row.addWidget(self.draw_bbox_btn)

        self.use_canvas_btn = QPushButton("Use Current Extent")
        self.use_canvas_btn.setToolTip("Use the current map canvas extent as BBOX")
        self.use_canvas_btn.clicked.connect(self._use_canvas_extent)
        btn_row.addWidget(self.use_canvas_btn)
        bbox_layout.addLayout(btn_row)

        coords_form = QFormLayout()
        self.xmin_edit = QLineEdit()
        self.ymin_edit = QLineEdit()
        self.xmax_edit = QLineEdit()
        self.ymax_edit = QLineEdit()
        for edit in [self.xmin_edit, self.ymin_edit, self.xmax_edit, self.ymax_edit]:
            edit.setReadOnly(False)
            edit.setPlaceholderText("0.0")

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("X min:"))
        row1.addWidget(self.xmin_edit)
        row1.addWidget(QLabel("Y min:"))
        row1.addWidget(self.ymin_edit)
        bbox_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("X max:"))
        row2.addWidget(self.xmax_edit)
        row2.addWidget(QLabel("Y max:"))
        row2.addWidget(self.ymax_edit)
        bbox_layout.addLayout(row2)

        self.bbox_crs_label = QLabel("CRS: (map canvas CRS)")
        self.bbox_crs_label.setStyleSheet("color: #666; font-size: 11px;")
        bbox_layout.addWidget(self.bbox_crs_label)

        bbox_group.setLayout(bbox_layout)
        layout.addWidget(bbox_group)

        # --- Resolution / Zoom ---
        res_group = QGroupBox("3. Resolution / Zoom Level")
        res_layout = QFormLayout()

        self.zoom_combo = QComboBox()
        for z, res in sorted(self.ZOOM_RESOLUTIONS.items()):
            self.zoom_combo.addItem(f"Zoom {z}  (~{res:.1f} m/px)", z)
        self.zoom_combo.setCurrentIndex(14)  # Default zoom 14
        self.zoom_combo.currentIndexChanged.connect(self._update_pixel_estimate)
        res_layout.addRow("Zoom level:", self.zoom_combo)

        self.custom_res_spin = QDoubleSpinBox()
        self.custom_res_spin.setRange(0.01, 200000.0)
        self.custom_res_spin.setDecimals(2)
        self.custom_res_spin.setValue(9.55)
        self.custom_res_spin.setSuffix(" m/px")
        self.custom_res_spin.setToolTip("Override with a custom resolution in meters per pixel")
        self.custom_res_spin.valueChanged.connect(self._update_pixel_estimate)
        res_layout.addRow("Custom resolution:", self.custom_res_spin)

        self.pixel_estimate_label = QLabel("")
        self.pixel_estimate_label.setStyleSheet("color: #666; font-size: 11px;")
        res_layout.addRow("Estimated size:", self.pixel_estimate_label)

        res_group.setLayout(res_layout)
        layout.addWidget(res_group)

        # Sync zoom combo -> custom res
        self.zoom_combo.currentIndexChanged.connect(self._sync_zoom_to_custom)
        self._sync_zoom_to_custom()

        # --- Output ---
        out_group = QGroupBox("4. Output")
        out_layout = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output GeoTIFF path...")
        out_layout.addWidget(self.output_path_edit)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(self.browse_btn)
        out_group.setLayout(out_layout)
        layout.addWidget(out_group)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.download_btn = QPushButton("Download")
        self.download_btn.setDefault(True)
        self.download_btn.clicked.connect(self._do_download)
        btn_layout.addWidget(self.download_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _populate_layers(self):
        self.layer_combo.clear()
        project = QgsProject.instance()
        for layer_id, layer in project.mapLayers().items():
            if isinstance(layer, QgsRasterLayer):
                provider = layer.providerType()
                if provider in ('wms', 'wmts', 'arcgismapserver', 'arcgisfeatureserver', 'wcs'):
                    self.layer_combo.addItem(
                        f"{layer.name()} [{provider.upper()}]",
                        layer_id
                    )
        # Also add all raster layers as fallback
        for layer_id, layer in project.mapLayers().items():
            if isinstance(layer, QgsRasterLayer):
                provider = layer.providerType()
                if provider not in ('wms', 'wmts', 'arcgismapserver', 'arcgisfeatureserver', 'wcs'):
                    self.layer_combo.addItem(
                        f"{layer.name()} [{provider}]",
                        layer_id
                    )
        if self.layer_combo.count() == 0:
            self.layer_combo.addItem("No raster layers found", None)

        self._on_layer_changed()

    def _on_layer_changed(self):
        layer = self._get_selected_layer()
        if layer:
            crs = layer.crs().authid()
            extent = layer.extent()
            self.layer_info_label.setText(
                f"Provider: {layer.providerType()} | CRS: {crs} | "
                f"Extent: {extent.xMinimum():.2f}, {extent.yMinimum():.2f} → "
                f"{extent.xMaximum():.2f}, {extent.yMaximum():.2f}"
            )
        else:
            self.layer_info_label.setText("No layer selected")
        self._update_pixel_estimate()

    def _get_selected_layer(self):
        layer_id = self.layer_combo.currentData()
        if layer_id:
            return QgsProject.instance().mapLayer(layer_id)
        return None

    def _start_bbox_draw(self):
        """Activate the bbox drawing tool on the map canvas."""
        self.prev_map_tool = self.canvas.mapTool()
        self.map_tool = BboxMapTool(self.canvas, self._on_bbox_drawn)
        self.canvas.setMapTool(self.map_tool)
        self.status_label.setText("Draw a rectangle on the map (click & drag)...")
        self.status_label.setStyleSheet("font-weight: bold; color: #c00;")
        # Minimize dialog so user can see the map
        self.showMinimized()

    def _on_bbox_drawn(self, rect):
        """Callback when bbox is drawn on the map."""
        self.bbox = rect
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        self.xmin_edit.setText(f"{rect.xMinimum():.6f}")
        self.ymin_edit.setText(f"{rect.yMinimum():.6f}")
        self.xmax_edit.setText(f"{rect.xMaximum():.6f}")
        self.ymax_edit.setText(f"{rect.yMaximum():.6f}")
        self.bbox_crs_label.setText(f"CRS: {canvas_crs.authid()}")

        # Restore dialog
        self.showNormal()
        self.activateWindow()
        self.raise_()

        # Restore previous map tool
        if self.prev_map_tool:
            self.canvas.setMapTool(self.prev_map_tool)

        self.status_label.setText("Bounding box set.")
        self.status_label.setStyleSheet("font-weight: bold; color: #080;")
        self._update_pixel_estimate()

    def _use_canvas_extent(self):
        """Use current map canvas extent as bounding box."""
        extent = self.canvas.extent()
        self.bbox = extent
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        self.xmin_edit.setText(f"{extent.xMinimum():.6f}")
        self.ymin_edit.setText(f"{extent.yMinimum():.6f}")
        self.xmax_edit.setText(f"{extent.xMaximum():.6f}")
        self.ymax_edit.setText(f"{extent.yMaximum():.6f}")
        self.bbox_crs_label.setText(f"CRS: {canvas_crs.authid()}")
        self.status_label.setText("Using current canvas extent.")
        self.status_label.setStyleSheet("font-weight: bold; color: #080;")
        self._update_pixel_estimate()

    def _sync_zoom_to_custom(self):
        zoom = self.zoom_combo.currentData()
        if zoom is not None and zoom in self.ZOOM_RESOLUTIONS:
            self.custom_res_spin.blockSignals(True)
            self.custom_res_spin.setValue(self.ZOOM_RESOLUTIONS[zoom])
            self.custom_res_spin.blockSignals(False)

    def _update_pixel_estimate(self):
        """Estimate output image dimensions based on bbox and resolution."""
        bbox = self._read_bbox()
        if bbox is None or bbox.width() == 0 or bbox.height() == 0:
            self.pixel_estimate_label.setText("Set a bounding box first")
            return

        res = self.custom_res_spin.value()
        if res <= 0:
            return

        # For geographic CRS (degrees), approximate meters
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        if canvas_crs.isGeographic():
            # Rough conversion: 1 degree ~ 111,320 m at equator
            center_lat = (bbox.yMinimum() + bbox.yMaximum()) / 2.0
            m_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))
            m_per_deg_lat = 110540.0
            width_m = bbox.width() * m_per_deg_lon
            height_m = bbox.height() * m_per_deg_lat
        else:
            width_m = bbox.width()
            height_m = bbox.height()

        px_w = int(width_m / res)
        px_h = int(height_m / res)
        size_mb = (px_w * px_h * 3) / (1024 * 1024)  # RGB estimate

        self.pixel_estimate_label.setText(
            f"{px_w} × {px_h} px  (~{size_mb:.1f} MB uncompressed)"
        )

        if px_w * px_h > 100_000_000:
            self.pixel_estimate_label.setStyleSheet("color: #c00; font-size: 11px; font-weight: bold;")
        elif px_w * px_h > 25_000_000:
            self.pixel_estimate_label.setStyleSheet("color: #a80; font-size: 11px;")
        else:
            self.pixel_estimate_label.setStyleSheet("color: #666; font-size: 11px;")

    def _read_bbox(self):
        """Read bbox from the edit fields."""
        try:
            xmin = float(self.xmin_edit.text())
            ymin = float(self.ymin_edit.text())
            xmax = float(self.xmax_edit.text())
            ymax = float(self.ymax_edit.text())
            return QgsRectangle(xmin, ymin, xmax, ymax)
        except (ValueError, TypeError):
            return self.bbox

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save GeoTIFF", "", "GeoTIFF (*.tif *.tiff)"
        )
        if path:
            if not path.lower().endswith(('.tif', '.tiff')):
                path += '.tif'
            self.output_path_edit.setText(path)

    def _do_download(self):
        """Execute the download using gdal_translate via Processing."""
        layer = self._get_selected_layer()
        if not layer:
            QMessageBox.warning(self, "Error", "Please select a valid layer.")
            return

        bbox = self._read_bbox()
        if bbox is None or bbox.width() == 0 or bbox.height() == 0:
            QMessageBox.warning(self, "Error", "Please define a bounding box.")
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "Error", "Please select an output file path.")
            return

        res = self.custom_res_spin.value()

        # Determine target CRS and compute dimensions
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        layer_crs = layer.crs()

        # Transform bbox from canvas CRS to layer CRS if needed
        if canvas_crs != layer_crs:
            transform = QgsCoordinateTransform(
                canvas_crs, layer_crs, QgsProject.instance()
            )
            bbox_layer = transform.transformBoundingBox(bbox)
        else:
            bbox_layer = bbox

        # Calculate pixel dimensions
        if canvas_crs.isGeographic():
            center_lat = (bbox.yMinimum() + bbox.yMaximum()) / 2.0
            m_per_deg_lon = 111320.0 * math.cos(math.radians(center_lat))
            m_per_deg_lat = 110540.0
            width_m = bbox.width() * m_per_deg_lon
            height_m = bbox.height() * m_per_deg_lat
        else:
            width_m = bbox.width()
            height_m = bbox.height()

        px_w = max(1, int(width_m / res))
        px_h = max(1, int(height_m / res))

        # Safety check
        total_px = px_w * px_h
        if total_px > 200_000_000:
            reply = QMessageBox.question(
                self, "Large Image Warning",
                f"The output image will be {px_w}×{px_h} pixels "
                f"({total_px/1_000_000:.0f} Mpx). This may take a very long "
                f"time and use a lot of memory.\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.status_label.setText("Downloading... please wait.")
        self.status_label.setStyleSheet("font-weight: bold; color: #008;")
        self.download_btn.setEnabled(False)
        QApplication.processEvents()

        try:
            # Use QGIS raster pipe to write
            pipe = QgsRasterPipe()
            provider = layer.dataProvider().clone()

            if not pipe.set(provider):
                raise Exception("Failed to set raster provider in pipe.")

            # Add projector if CRS differs
            if canvas_crs != layer_crs:
                projector = QgsRasterProjector()
                projector.setCrs(layer_crs, canvas_crs)
                if not pipe.insert(pipe.size(), projector):
                    # Fallback: try without projector
                    pass

            writer = QgsRasterFileWriter(output_path)
            writer.setOutputFormat("GTiff")
            writer.setCreateOptions([
                "COMPRESS=DEFLATE",
                "TILED=YES",
                "BIGTIFF=IF_SAFER"
            ])

            error = writer.writeRaster(
                pipe,
                px_w,
                px_h,
                bbox_layer,
                layer_crs
            )

            if error != QgsRasterFileWriter.NoError:
                raise Exception(f"Raster write error (code {error}). "
                                "Trying fallback method with gdal_translate...")

            self._on_download_success(output_path, px_w, px_h)

        except Exception as e:
            # Fallback: try using Processing gdal_translate
            self.status_label.setText("Primary method failed, trying gdal_translate fallback...")
            QApplication.processEvents()
            try:
                self._download_via_gdal(layer, bbox, bbox_layer, canvas_crs,
                                        layer_crs, px_w, px_h, output_path)
            except Exception as e2:
                self.progress_bar.setVisible(False)
                self.download_btn.setEnabled(True)
                self.status_label.setText("Download failed.")
                self.status_label.setStyleSheet("font-weight: bold; color: #c00;")
                QMessageBox.critical(
                    self, "Download Failed",
                    f"Primary error: {e}\n\nFallback error: {e2}"
                )

    def _download_via_gdal(self, layer, bbox, bbox_layer, canvas_crs,
                           layer_crs, px_w, px_h, output_path):
        """Fallback download using Processing's gdal:translate."""
        params = {
            'INPUT': layer.source(),
            'TARGET_CRS': canvas_crs.authid(),
            'OUTSIZE_X': px_w,
            'OUTSIZE_Y': px_h,
            'PROJWIN': f"{bbox.xMinimum()},{bbox.xMaximum()},{bbox.yMinimum()},{bbox.yMaximum()}",
            'OUTPUT': output_path,
            'OPTIONS': 'COMPRESS=DEFLATE|TILED=YES',
            'DATA_TYPE': 0,  # Use input
        }
        try:
            result = processing.run("gdal:translate", params)
            self._on_download_success(output_path, px_w, px_h)
        except Exception:
            # Final fallback: Save As directly
            self._download_via_save_as(layer, bbox_layer, layer_crs,
                                       px_w, px_h, output_path)

    def _download_via_save_as(self, layer, bbox_layer, target_crs,
                              px_w, px_h, output_path):
        """Last-resort fallback using layer export."""
        pipe = QgsRasterPipe()
        if not pipe.set(layer.dataProvider().clone()):
            raise Exception("Cannot set raster data provider.")

        writer = QgsRasterFileWriter(output_path)
        writer.setOutputFormat("GTiff")

        error = writer.writeRaster(
            pipe, px_w, px_h, bbox_layer, target_crs
        )
        if error != QgsRasterFileWriter.NoError:
            raise Exception(f"All download methods failed. Error code: {error}")

        self._on_download_success(output_path, px_w, px_h)

    def _on_download_success(self, output_path, px_w, px_h):
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        self.status_label.setText(f"Saved: {os.path.basename(output_path)}")
        self.status_label.setStyleSheet("font-weight: bold; color: #080;")

        reply = QMessageBox.question(
            self, "Download Complete",
            f"GeoTIFF saved successfully!\n\n"
            f"File: {output_path}\n"
            f"Size: {px_w} × {px_h} px\n\n"
            f"Add to project?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            name = os.path.splitext(os.path.basename(output_path))[0]
            rlayer = QgsRasterLayer(output_path, name, "gdal")
            if rlayer.isValid():
                QgsProject.instance().addMapLayer(rlayer)
            else:
                QMessageBox.warning(self, "Warning",
                                    "File saved but could not be loaded as a layer.")

    def closeEvent(self, event):
        if self.map_tool:
            self.map_tool.reset()
        super().closeEvent(event)


class WmsDownloaderPlugin:
    """QGIS Plugin entry point."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        self.action = QAction("WMS/WMTS Downloader", self.iface.mainWindow())
        self.action.setToolTip("Download WMS/WMTS layers to local GeoTIFF")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu("WMS/WMTS Downloader", self.action)

    def unload(self):
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("WMS/WMTS Downloader", self.action)
        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def run(self):
        if self.dialog is None:
            self.dialog = WmsDownloaderDialog(self.iface, self.iface.mainWindow())
        else:
            self.dialog._populate_layers()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
