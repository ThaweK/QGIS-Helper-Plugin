"""Unified QGIS Plugin Helper — single entry point for all helper tools."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu


class QgisPluginHelper:
    """Wraps all sub-plugins under one toolbar and one menu."""

    MENU = "QGIS Plugin Helper"

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self._sub_plugins = []
        self._designer_menus = {}  # designer -> QMenu

    def initGui(self):
        self.toolbar = self.iface.addToolBar(self.MENU)
        self.toolbar.setObjectName("QgisPluginHelper")

        # ── Instantiate sub-plugins with shared toolbar ──
        self._init_caa()
        self._init_bdot10k_toolbox()
        self._init_wms_downloader()
        self._init_font_regenerator()
        self._init_lock_layers()
        self._init_drafting_helpers()

        # Init each sub-plugin
        for sp in self._sub_plugins:
            sp.initGui()

        # ── Hook into Print Layout designers ──
        self.iface.layoutDesignerOpened.connect(self._on_designer_opened)
        self.iface.layoutDesignerWillBeClosed.connect(self._on_designer_closing)

        # Add menu to any already-open designers
        for designer in self.iface.openLayoutDesigners():
            self._on_designer_opened(designer)

    def unload(self):
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

    # ── Print Layout designer menu ────────────────────────────────────────

    def _on_designer_opened(self, designer):
        """Add the plugin menu to a newly opened Layout Designer."""
        if designer in self._designer_menus:
            return

        menu = QMenu(self.MENU, designer.window().menuBar())

        # Mirror the same actions from the main menu
        for sp in self._sub_plugins:
            actions = getattr(sp, 'actions', [])
            action = getattr(sp, 'action', None)
            if actions:
                for a in actions:
                    menu.addAction(a)
            elif action:
                menu.addAction(action)

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
