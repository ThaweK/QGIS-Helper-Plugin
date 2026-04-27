"""Main plugin class for Lock Layers."""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsLayoutItemMap

from .lock_layers_dialog import LockLayersDialog


class LockLayersPlugin:
    def __init__(self, iface, toolbar=None):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "QGIS Plugin Helper"
        self._shared_toolbar = toolbar
        self.toolbar = None
        self.dlg = None

    def initGui(self):
        if self._shared_toolbar is None:
            self.toolbar = self.iface.addToolBar("Lock Layers")
            self.toolbar.setObjectName("LockLayers")
        else:
            self.toolbar = self._shared_toolbar

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        action = QAction(
            icon,
            "Zablokuj warstwy / Lock Layers",
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
        if self._shared_toolbar is None and self.toolbar:
            del self.toolbar
        self.dlg = None

    def show_dialog(self):
        """Open the Lock Layers dialog for the selected map item."""
        map_item = self._get_selected_map_item()
        if map_item is None:
            return

        # Always create a fresh dialog for the current map item
        self.dlg = LockLayersDialog(map_item, self.iface.mainWindow())
        self.dlg.show()
        self.dlg.raise_()

    def _get_selected_map_item(self):
        """Find a selected QgsLayoutItemMap in an open Layout Designer.

        Shows a warning and returns None if no designer is open or no
        map item is selected.
        """
        designers = self.iface.openLayoutDesigners()
        if not designers:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Lock Layers",
                "Brak otwartego projektanta wydruku.\n"
                "No Print Layout designer is open.",
            )
            return None

        # Check each open designer for a selected map item
        for designer in designers:
            layout = designer.layout()
            for item in layout.selectedLayoutItems():
                if isinstance(item, QgsLayoutItemMap):
                    return item

        QMessageBox.warning(
            self.iface.mainWindow(),
            "Lock Layers",
            "Zaznacz element mapy w projektancie wydruku.\n"
            "Select a map item in the Print Layout designer.",
        )
        return None
