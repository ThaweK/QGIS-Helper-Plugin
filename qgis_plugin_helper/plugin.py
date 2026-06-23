"""Unified QGIS Plugin Helper — single entry point for all helper tools."""

import json
import math
import os

from qgis.PyQt.QtCore import QDate, QDateTime, QTime
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QApplication, QMenu, QMessageBox
from qgis.core import (
    NULL,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)


class QgisPluginHelper:
    """Wraps all sub-plugins under one toolbar and one menu."""

    MENU = "QGIS Plugin Helper"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self._sub_plugins = []
        self._designer_menus = {}  # designer -> QMenu
        self._plugin_submenus = []
        self._copy_geojson_action = None

    def initGui(self):
        self.toolbar = self.iface.addToolBar(self.MENU)
        self.toolbar.setObjectName("QgisPluginHelper")
        self._init_copy_geojson_action()

        # ── Instantiate sub-plugins with shared toolbar ──
        self._init_caa()
        self._init_bdot10k_toolbox()
        self._init_wms_downloader()
        self._init_font_regenerator()
        self._init_lock_layers()
        self._init_layout_grid_helper()
        self._init_drafting_helpers()

        # Init each sub-plugin
        for sp in self._sub_plugins:
            sp.initGui()

        self._rebuild_plugin_menu()

        # ── Hook into Print Layout designers ──
        self.iface.layoutDesignerOpened.connect(self._on_designer_opened)
        self.iface.layoutDesignerWillBeClosed.connect(self._on_designer_closing)

        # Add menu to any already-open designers
        for designer in self.iface.openLayoutDesigners():
            self._on_designer_opened(designer)

    def unload(self):
        self._clear_plugin_submenus()
        self._unload_copy_geojson_action()

        for sp in self._sub_plugins:
            sp.unload()
        if self.toolbar:
            del self.toolbar
        self._sub_plugins = []

        try:
            self.iface.layoutDesignerOpened.disconnect(self._on_designer_opened)
            self.iface.layoutDesignerWillBeClosed.disconnect(self._on_designer_closing)
        except TypeError:
            pass

        # Remove menus from any open designers
        for designer, menu in list(self._designer_menus.items()):
            try:
                designer.window().menuBar().removeAction(menu.menuAction())
            except RuntimeError:
                pass
        self._designer_menus.clear()

    # ── Main QGIS plugin menu ────────────────────────────────────────────

    def _rebuild_plugin_menu(self):
        """Replace the flat plugin menu with task-oriented submenus."""
        self._clear_plugin_submenus()

        # Sub-plugins register their actions in a flat menu. Remove those
        # entries and re-add the same QAction objects under structured submenus.
        for action in self._all_actions():
            try:
                self.iface.removePluginMenu(self.MENU, action)
            except (RuntimeError, TypeError):
                pass

        for menu in self._build_menu_tree(self.iface.mainWindow()):
            self.iface.addPluginToMenu(self.MENU, menu.menuAction())
            self._plugin_submenus.append(menu)

    def _clear_plugin_submenus(self):
        for menu in self._plugin_submenus:
            try:
                self.iface.removePluginMenu(self.MENU, menu.menuAction())
            except (RuntimeError, TypeError):
                pass
        self._plugin_submenus = []

    def _all_actions(self):
        actions = []
        if self._copy_geojson_action:
            actions.append(self._copy_geojson_action)
        for sp in self._sub_plugins:
            sp_actions = getattr(sp, "actions", [])
            action = getattr(sp, "action", None)
            if sp_actions:
                actions.extend(sp_actions)
            elif action:
                actions.append(action)
        return actions

    def _build_menu_tree(self, parent):
        menus = []

        bdot = QMenu("BDOT10k", parent)
        bdot_import = bdot.addMenu("Pobieranie i import")
        bdot_styles = bdot.addMenu("Style i etykiety")
        bdot_layers = bdot.addMenu("Warstwy i merge")
        menus.append(bdot)

        data = QMenu("Dane zewnetrzne", parent)
        layout = QMenu("Layout / wydruk", parent)
        editing = QMenu("Rysowanie pomocnicze", parent)
        project = QMenu("Projekt i fonty", parent)
        aviation = QMenu("Lotnictwo / CAA", parent)

        has_data = has_layout = has_editing = has_project = has_aviation = False

        if self._copy_geojson_action:
            data.addAction(self._copy_geojson_action)
            has_data = True

        for sp in self._sub_plugins:
            class_name = sp.__class__.__name__
            actions = self._actions_for_plugin(sp)

            if class_name == "BDOT10kToolbox":
                for action in actions:
                    text = action.text()
                    if "OSM" in text:
                        data.addAction(action)
                        has_data = True
                    elif "Pobierz" in text or "Download" in text:
                        bdot_import.addAction(action)
                    elif "merge" in text.lower() or "wspolne warstwy" in text.lower():
                        bdot_layers.addAction(action)
                    else:
                        bdot_styles.addAction(action)
                continue

            if class_name == "WmsDownloaderPlugin":
                for action in actions:
                    data.addAction(action)
                    has_data = True
                continue

            if class_name in {"LockLayersPlugin", "LayoutGridHelperPlugin"}:
                for action in actions:
                    layout.addAction(action)
                    has_layout = True
                continue

            if class_name == "DraftingHelpersPlugin":
                for action in actions:
                    editing.addAction(action)
                    has_editing = True
                continue

            if class_name == "FontRegeneratorPlugin":
                for action in actions:
                    project.addAction(action)
                    has_project = True
                continue

            if class_name == "CAAObstacleExplorer":
                for action in actions:
                    aviation.addAction(action)
                    has_aviation = True
                continue

            for action in actions:
                project.addAction(action)
                has_project = True

        if has_data:
            menus.append(data)
        if has_layout:
            menus.append(layout)
        if has_editing:
            menus.append(editing)
        if has_project:
            menus.append(project)
        if has_aviation:
            menus.append(aviation)

        return menus

    def _actions_for_plugin(self, sp):
        actions = getattr(sp, "actions", [])
        action = getattr(sp, "action", None)
        if actions:
            return actions
        if action:
            return [action]
        return []

    # ── Clipboard GeoJSON export ─────────────────────────────────────────

    def _init_copy_geojson_action(self):
        action = QAction("Copy Selected Features as GeoJSON", self.iface.mainWindow())
        action.setStatusTip("Copy all selected vector features from the project as one GeoJSON FeatureCollection")
        action.triggered.connect(self._copy_selected_features_as_geojson)
        self._copy_geojson_action = action
        if self.toolbar:
            self.toolbar.addAction(action)

    def _unload_copy_geojson_action(self):
        if not self._copy_geojson_action:
            return
        try:
            self.iface.removePluginMenu(self.MENU, self._copy_geojson_action)
        except (RuntimeError, TypeError):
            pass
        if self.toolbar:
            self.toolbar.removeAction(self._copy_geojson_action)
        self._copy_geojson_action = None

    def _copy_selected_features_as_geojson(self):
        try:
            selected_layers = self._selected_vector_layers()
            if not selected_layers:
                self.iface.messageBar().pushWarning(
                    self.MENU,
                    "No selected vector features found.",
                )
                return

            crs_mode = self._ask_geojson_crs_mode()
            if crs_mode is None:
                return

            collection, feature_count, layer_count = self._selected_features_geojson(selected_layers, crs_mode)
            QApplication.clipboard().setText(
                json.dumps(collection, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            )
            self.iface.messageBar().pushSuccess(
                self.MENU,
                f"Copied {feature_count} selected feature(s) from {layer_count} layer(s) as GeoJSON.",
            )
        except Exception as error:
            self.iface.messageBar().pushWarning(
                self.MENU,
                f"Could not copy selected features as GeoJSON: {error}",
            )

    def _ask_geojson_crs_mode(self):
        dialog = QMessageBox(self.iface.mainWindow())
        dialog.setWindowTitle("Copy Selected Features as GeoJSON")
        dialog.setIcon(QMessageBox.Question)
        dialog.setText("Choose GeoJSON coordinates")
        dialog.setInformativeText(
            "Use EPSG:4326 for standard GeoJSON, or keep local layer coordinates with EPSG/WKT CRS metadata."
        )
        epsg4326_button = dialog.addButton("EPSG:4326", QMessageBox.AcceptRole)
        local_button = dialog.addButton("Local EPSG/WKT", QMessageBox.ActionRole)
        dialog.addButton(QMessageBox.Cancel)
        dialog.setDefaultButton(epsg4326_button)
        dialog.exec_()

        clicked = dialog.clickedButton()
        if clicked == epsg4326_button:
            return "epsg4326"
        if clicked == local_button:
            return "local"
        return None

    def _selected_vector_layers(self):
        return [
            layer
            for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer) and layer.selectedFeatureCount() > 0
        ]

    def _selected_features_geojson(self, selected_layers, crs_mode):
        project = QgsProject.instance()
        destination_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        features = []
        layer_count = 0

        for layer in selected_layers:
            transform = None
            if crs_mode == "epsg4326":
                transform = self._geojson_transform(layer, destination_crs, project)
            added_for_layer = 0
            crs_metadata = self._crs_metadata(layer.crs()) if crs_mode == "local" else None

            for feature in layer.selectedFeatures():
                features.append(self._feature_geojson(layer, feature, transform, crs_metadata))
                added_for_layer += 1

            if added_for_layer:
                layer_count += 1

        collection = {"type": "FeatureCollection", "features": features}
        if crs_mode == "local":
            self._add_local_crs_metadata(collection, selected_layers)

        return collection, len(features), layer_count

    def _geojson_transform(self, layer, destination_crs, project):
        source_crs = layer.crs()
        if not source_crs.isValid() or not destination_crs.isValid() or source_crs == destination_crs:
            return None
        return QgsCoordinateTransform(source_crs, destination_crs, project.transformContext())

    def _feature_geojson(self, layer, feature, transform, crs_metadata=None):
        geojson_feature = {
            "type": "Feature",
            "properties": self._feature_properties(layer, feature),
            "geometry": self._feature_geometry(feature, transform),
        }
        if crs_metadata:
            geojson_feature["source_crs"] = crs_metadata
        return geojson_feature

    def _add_local_crs_metadata(self, collection, selected_layers):
        crs_metadata = [self._crs_metadata(layer.crs()) for layer in selected_layers]
        unique_crs = {item["wkt"] for item in crs_metadata if item["wkt"]}
        if len(unique_crs) != 1:
            collection["crs_note"] = "Mixed source CRS values. See feature source_crs metadata."
            return

        metadata = crs_metadata[0]
        collection["crs"] = {
            "type": "name",
            "properties": {"name": metadata["authid"] or metadata["description"] or "local"},
        }
        collection["crs_wkt"] = metadata["wkt"]

    def _crs_metadata(self, crs):
        if not crs or not crs.isValid():
            return {"authid": "", "description": "", "wkt": ""}
        return {
            "authid": crs.authid(),
            "description": crs.description(),
            "wkt": crs.toWkt(),
        }

    def _feature_properties(self, layer, feature):
        properties = {}
        for index, field in enumerate(layer.fields()):
            properties[field.name()] = self._json_value(feature.attribute(index))
        return properties

    def _feature_geometry(self, feature, transform):
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            return None

        geometry = QgsGeometry(geometry)
        if transform:
            geometry.transform(transform)
        return json.loads(geometry.asJson(17))

    def _json_value(self, value):
        if value is None or value == NULL:
            return None
        if isinstance(value, QDateTime):
            return value.toString("yyyy-MM-ddTHH:mm:ss")
        if isinstance(value, QDate):
            return value.toString("yyyy-MM-dd")
        if isinstance(value, QTime):
            return value.toString("HH:mm:ss")
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return [self._json_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_value(item) for key, item in value.items()}
        if hasattr(value, "toString"):
            return value.toString()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    # ── Print Layout designer menu ────────────────────────────────────────

    def _on_designer_opened(self, designer):
        """Add the plugin menu to a newly opened Layout Designer."""
        if designer in self._designer_menus:
            return

        menu = QMenu(self.MENU, designer.window().menuBar())

        # Mirror the same task-oriented menu tree from the main plugin menu.
        for submenu in self._build_menu_tree(menu):
            menu.addMenu(submenu)

        designer.window().menuBar().addMenu(menu)
        self._designer_menus[designer] = menu

    def _on_designer_closing(self, designer):
        """Clean up when a Layout Designer is about to close."""
        menu = self._designer_menus.pop(designer, None)
        if menu:
            try:
                designer.window().menuBar().removeAction(menu.menuAction())
            except RuntimeError:
                pass

    # ── Sub-plugin factories ─────────────────────────────────────────────

    def _init_caa(self):
        try:
            from .caa_obstacle_explorer.plugin import CAAObstacleExplorer
            self._sub_plugins.append(CAAObstacleExplorer(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("CAA Obstacle Explorer", e)

    def _init_bdot10k_toolbox(self):
        try:
            from .bdot10k_toolbox.plugin import BDOT10kToolbox
            self._sub_plugins.append(BDOT10kToolbox(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("BDOT10k Toolbox", e)

    def _init_wms_downloader(self):
        try:
            from .wms_downloader.plugin import WmsDownloaderPlugin
            self._sub_plugins.append(WmsDownloaderPlugin(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("WMS/WMTS Downloader", e)

    def _init_font_regenerator(self):
        try:
            from .font_regenerator.font_regenerator import FontRegeneratorPlugin
            self._sub_plugins.append(FontRegeneratorPlugin(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("Font Regenerator", e)

    def _init_lock_layers(self):
        try:
            from .lock_layers.plugin import LockLayersPlugin
            self._sub_plugins.append(LockLayersPlugin(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("Lock Layers", e)

    def _init_layout_grid_helper(self):
        try:
            from .layout_grid_helper.plugin import LayoutGridHelperPlugin
            self._sub_plugins.append(LayoutGridHelperPlugin(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("Layout Grid Helper", e)

    def _init_drafting_helpers(self):
        try:
            from .drafting_helpers.plugin import DraftingHelpersPlugin
            self._sub_plugins.append(DraftingHelpersPlugin(self.iface, toolbar=self.toolbar))
        except Exception as e:
            self._log_error("Drafting Helpers", e)

    def _log_error(self, name, error):
        """Log sub-plugin load failure without breaking the whole plugin."""
        try:
            from qgis.core import QgsMessageLog, Qgis
            QgsMessageLog.logMessage(
                f"QGIS Plugin Helper: failed to load '{name}': {error}",
                "Plugins",
                Qgis.Warning,
            )
        except Exception:
            pass
