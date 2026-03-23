"""
Main plugin class for Font Regenerator.
"""

import os

from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon


class FontRegeneratorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(icon, "Font Regenerator", self.iface.mainWindow())
        self.action.setStatusTip("Scan and replace OS-specific fonts in the project")
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("Font Regenerator", self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("Font Regenerator", self.action)
            self.iface.removeToolBarIcon(self.action)

        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def run(self):
        from .dialog_main import FontRegeneratorDialog

        if self.dialog is None:
            self.dialog = FontRegeneratorDialog(self.iface.mainWindow())

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
