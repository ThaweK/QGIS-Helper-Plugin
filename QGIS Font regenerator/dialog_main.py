"""
Main dialog for the Font Regenerator plugin.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QComboBox, QProgressBar,
    QGroupBox, QMessageBox, QHeaderView, QCheckBox, QSplitter,
    QTextEdit, QWidget,
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QFont, QColor, QFontDatabase

from .font_scanner import scan_project, ScanResult
from .font_replacer import replace_fonts
from .font_database import (
    classify_font, get_available_safe_fonts, is_font_available,
    CROSS_PLATFORM_SAFE_FONTS,
)


STATUS_COLORS = {
    "macos": QColor(255, 149, 0),      # orange
    "windows": QColor(0, 120, 215),     # blue
    "linux": QColor(233, 84, 32),       # ubuntu orange
    "safe": QColor(76, 175, 80),        # green
    "unknown": QColor(158, 158, 158),   # gray
    "missing": QColor(244, 67, 54),     # red
}

STATUS_LABELS = {
    "macos": "macOS only",
    "windows": "Windows only",
    "linux": "Linux specific",
    "safe": "Cross-platform",
    "unknown": "Unknown",
    "missing": "Not installed",
}


class FontRegeneratorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Font Regenerator")
        self.setMinimumSize(QSize(800, 600))
        self.scan_result = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Scan section
        scan_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Project")
        self.scan_btn.clicked.connect(self._on_scan)
        scan_layout.addWidget(self.scan_btn)
        self.status_label = QLabel("Click 'Scan Project' to find all font usages.")
        scan_layout.addWidget(self.status_label, 1)
        layout.addLayout(scan_layout)

        # Splitter for tree + warnings
        splitter = QSplitter(Qt.Vertical)

        # Results tree
        tree_group = QGroupBox("Font Usages")
        tree_layout = QVBoxLayout(tree_group)

        # Select/deselect controls
        select_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All Non-Safe")
        self.select_all_btn.clicked.connect(self._select_all_non_safe)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.deselect_all_btn)
        select_layout.addStretch()
        tree_layout.addLayout(select_layout)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Font / Location", "Status", "Count"])
        self.tree.setColumnCount(3)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.setRootIsDecorated(True)
        tree_layout.addWidget(self.tree)

        splitter.addWidget(tree_group)

        # Warnings
        self.warnings_group = QGroupBox("Warnings")
        warnings_layout = QVBoxLayout(self.warnings_group)
        self.warnings_text = QTextEdit()
        self.warnings_text.setReadOnly(True)
        self.warnings_text.setMaximumHeight(120)
        warnings_layout.addWidget(self.warnings_text)
        self.warnings_group.setVisible(False)
        splitter.addWidget(self.warnings_group)

        layout.addWidget(splitter, 1)

        # Replacement section
        replace_group = QGroupBox("Replace Selected Fonts With")
        replace_layout = QHBoxLayout(replace_group)

        replace_layout.addWidget(QLabel("Target font:"))
        self.font_combo = QComboBox()
        self._populate_font_combo()
        self.font_combo.setMinimumWidth(200)
        replace_layout.addWidget(self.font_combo, 1)

        self.replace_btn = QPushButton("Replace Selected")
        self.replace_btn.setEnabled(False)
        self.replace_btn.clicked.connect(self._on_replace)
        replace_layout.addWidget(self.replace_btn)

        layout.addWidget(replace_group)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _populate_font_combo(self):
        """Populate the font combo with available cross-platform fonts."""
        db = QFontDatabase()
        system_families = set(db.families())
        added = set()

        # Add available safe fonts first
        for font_name in CROSS_PLATFORM_SAFE_FONTS:
            if font_name in system_families:
                self.font_combo.addItem(font_name)
                added.add(font_name)

        # Add separator and all system fonts
        if added:
            self.font_combo.insertSeparator(self.font_combo.count())

        for family in sorted(system_families):
            if family not in added and not family.startswith("."):
                self.font_combo.addItem(family)

    def _on_scan(self):
        """Run the font scan."""
        self.scan_btn.setEnabled(False)
        self.status_label.setText("Scanning...")
        self.tree.clear()

        try:
            self.scan_result = scan_project()
            self._display_results()
        except Exception as e:
            QMessageBox.critical(self, "Scan Error", f"Error during scan:\n{e}")
        finally:
            self.scan_btn.setEnabled(True)

    def _display_results(self):
        """Display scan results in the tree widget."""
        if not self.scan_result:
            return

        fonts_by_family = self.scan_result.fonts_by_family()
        total_fonts = len(fonts_by_family)
        total_usages = len(self.scan_result.usages)

        self.status_label.setText(
            f"Found {total_fonts} unique font(s) across {total_usages} usage(s)."
        )

        for family in sorted(fonts_by_family.keys()):
            usages = fonts_by_family[family]
            classification = classify_font(family)

            # Override classification if font is not installed
            if not is_font_available(family):
                effective_status = "missing"
            else:
                effective_status = classification

            # Font family top-level item
            item = QTreeWidgetItem()
            item.setText(0, family)
            item.setText(1, STATUS_LABELS.get(effective_status, effective_status))
            item.setText(2, str(len(usages)))
            item.setForeground(1, STATUS_COLORS.get(effective_status, QColor(0, 0, 0)))

            # Make checkable
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # Auto-check non-safe fonts
            if effective_status not in ("safe",):
                item.setCheckState(0, Qt.Checked)
            else:
                item.setCheckState(0, Qt.Unchecked)

            # Store font family for replacement
            item.setData(0, Qt.UserRole, family)

            # Add child items for each usage location
            for usage in usages:
                child = QTreeWidgetItem()
                child.setText(0, usage.location_display)
                item.addChild(child)

            self.tree.addTopLevelItem(item)

        self.tree.expandAll()
        self.replace_btn.setEnabled(total_fonts > 0)

        # Show warnings
        if self.scan_result.warnings:
            self.warnings_group.setVisible(True)
            self.warnings_text.setPlainText("\n".join(self.scan_result.warnings))
        else:
            self.warnings_group.setVisible(False)

    def _select_all_non_safe(self):
        """Select all fonts that are not cross-platform safe."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            family = item.data(0, Qt.UserRole)
            classification = classify_font(family)
            if classification != "safe":
                item.setCheckState(0, Qt.Checked)

    def _deselect_all(self):
        """Deselect all fonts."""
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)

    def _get_selected_fonts(self):
        """Get list of checked font families."""
        selected = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                family = item.data(0, Qt.UserRole)
                if family:
                    selected.append(family)
        return selected

    def _on_replace(self):
        """Replace selected fonts with the chosen target font."""
        selected = self._get_selected_fonts()
        if not selected:
            QMessageBox.information(self, "Nothing Selected", "No fonts selected for replacement.")
            return

        target_font = self.font_combo.currentText()
        if not target_font:
            QMessageBox.warning(self, "No Target", "Please select a target font.")
            return

        # Confirm
        msg = (
            f"Replace {len(selected)} font(s) with '{target_font}'?\n\n"
            f"Fonts to replace:\n"
            + "\n".join(f"  - {f}" for f in selected)
            + "\n\nThis action cannot be undone. Save your project first!"
        )
        reply = QMessageBox.question(
            self, "Confirm Replacement", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Build replacement map
        replacements = {family: target_font for family in selected}

        self.replace_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate

        try:
            result = replace_fonts(replacements)
            self.progress.setVisible(False)

            msg = f"Done! Made {result.replacements_made} replacement(s)."
            if result.errors:
                msg += f"\n\n{len(result.errors)} error(s):\n" + "\n".join(result.errors)
                QMessageBox.warning(self, "Replacement Complete", msg)
            else:
                QMessageBox.information(self, "Replacement Complete", msg)

            # Re-scan to show updated state
            self._on_scan()

        except Exception as e:
            self.progress.setVisible(False)
            QMessageBox.critical(self, "Replacement Error", f"Error during replacement:\n{e}")
        finally:
            self.replace_btn.setEnabled(True)
