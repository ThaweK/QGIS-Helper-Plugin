"""Smart Print Layout grid helper plugin."""

import math
import os

from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog, QMessageBox
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsProject,
    QgsRectangle,
    QgsTextFormat,
)

from .dialog import SmartGridDialog


class LayoutGridHelperPlugin:
    """Create a readable coordinate grid for a selected layout map."""

    GRID_NAME = "QPH Smart Grid"

    LOCAL_STEPS = (1.0, 2.0, 2.5, 5.0, 10.0)
    GEOGRAPHIC_STEPS = (
        1.0 / 3600.0,
        2.0 / 3600.0,
        5.0 / 3600.0,
        10.0 / 3600.0,
        15.0 / 3600.0,
        30.0 / 3600.0,
        1.0 / 60.0,
        2.0 / 60.0,
        5.0 / 60.0,
        10.0 / 60.0,
        15.0 / 60.0,
        30.0 / 60.0,
        1.0,
        2.0,
        5.0,
        10.0,
        15.0,
        30.0,
        45.0,
    )

    def __init__(self, iface, toolbar=None):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "QGIS Plugin Helper"
        self._shared_toolbar = toolbar
        self.toolbar = None

    def initGui(self):
        if self._shared_toolbar is None:
            self.toolbar = self.iface.addToolBar("Layout Grid Helper")
            self.toolbar.setObjectName("LayoutGridHelper")
        else:
            self.toolbar = self._shared_toolbar

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        action = QAction(icon, "Automatyczna siatka ukladu / Smart Layout Grid", self.iface.mainWindow())
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

    def show_dialog(self):
        context = self._get_layout_context()
        if context is None:
            return

        dialog = SmartGridDialog(
            context["primary"],
            self._context_info_text(context),
            selected_count=len(context["selected_maps"]),
            layout_count=len(context["layout_maps"]),
            parent=self.iface.mainWindow(),
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        settings = dialog.settings()
        targets = self._target_maps(context, settings["scope"])
        if not targets:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Smart Layout Grid",
                "Nie znaleziono zadnych view do ustawienia siatki.",
            )
            return

        applied = []
        errors = []
        try:
            for target in targets:
                try:
                    plan = self._build_plan(target, settings)
                    grid_name = self._apply_grid(target, plan)
                    applied.append((target, plan, grid_name))
                except Exception as error:
                    errors.append(f"{self._map_label(target)}: {error}")
        finally:
            self._refresh_layout(context["layout"])

        if errors and not applied:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Smart Layout Grid",
                "Nie udalo sie ustawic siatki:\n" + "\n".join(errors),
            )
            return

        if errors:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Smart Layout Grid",
                "Czesc view ustawiono, ale czesc pominieto:\n" + "\n".join(errors),
            )

        self._show_success(applied)

    def _get_layout_context(self):
        designers = self.iface.openLayoutDesigners()
        if not designers:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Smart Layout Grid",
                "Brak otwartego projektanta wydruku.\nNo Print Layout designer is open.",
            )
            return None

        layouts_with_maps = []
        for designer in designers:
            layout = designer.layout()
            layout_maps = self._layout_maps(layout)
            if layout_maps:
                layouts_with_maps.append((designer, layout, layout_maps))

            selected_maps = [
                item for item in layout.selectedLayoutItems()
                if isinstance(item, QgsLayoutItemMap)
            ]
            if selected_maps:
                return {
                    "designer": designer,
                    "layout": layout,
                    "primary": selected_maps[0],
                    "selected_maps": selected_maps,
                    "layout_maps": layout_maps,
                }

        total_maps = sum(len(layout_maps) for _designer, _layout, layout_maps in layouts_with_maps)
        if total_maps == 1:
            designer, layout, layout_maps = layouts_with_maps[0]
            return {
                "designer": designer,
                "layout": layout,
                "primary": layout_maps[0],
                "selected_maps": [layout_maps[0]],
                "layout_maps": layout_maps,
            }

        QMessageBox.warning(
            self.iface.mainWindow(),
            "Smart Layout Grid",
            "Zaznacz dowolny view mapy w projektancie wydruku.\n"
            "Select any map view in the Print Layout designer.",
        )
        return None

    def _layout_maps(self, layout):
        return [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]

    def _target_maps(self, context, scope):
        if scope == "layout":
            return context["layout_maps"]
        if scope == "selected":
            return context["selected_maps"]
        return [context["primary"]]

    def _context_info_text(self, context):
        return (
            self._map_info_text(context["primary"])
            + f" Zaznaczone view: {len(context['selected_maps'])}; "
            + f"view w layoucie: {len(context['layout_maps'])}."
        )

    def _map_info_text(self, map_item):
        extent = map_item.extent()
        crs = self._map_crs(map_item)
        width_mm, height_mm = self._map_size_mm(map_item)
        page_width_mm, page_height_mm = self._page_size_mm(map_item)
        scale = self._map_scale(map_item)
        return (
            f"Strona: {page_width_mm:.1f} x {page_height_mm:.1f} mm, "
            f"mapa: {width_mm:.1f} x {height_mm:.1f} mm, skala 1:{scale:,.0f}, "
            f"CRS mapy: {crs.authid() or crs.description() or 'unknown'}, "
            f"zasieg: {extent.width():.3f} x {extent.height():.3f} jednostek mapy."
        )

    def _map_label(self, map_item):
        for attr in ("id", "displayName"):
            method = getattr(map_item, attr, None)
            if method:
                try:
                    label = method()
                    if label:
                        return label
                except Exception:
                    pass
        return "view"

    def _build_plan(self, map_item, settings):
        grid_crs = self._grid_crs(map_item, settings)
        extent = self._extent_in_grid_crs(map_item, grid_crs)
        width_mm, height_mm = self._map_size_mm(map_item)
        geographic = grid_crs.isGeographic()

        interval_x = self._interval_for_axis(
            extent.width(),
            width_mm,
            settings["interval_mode"],
            settings["target_x"],
            settings["manual_x"],
            settings["min_spacing_mm"],
            settings["edge_mode"],
            geographic,
        )
        interval_y = self._interval_for_axis(
            extent.height(),
            height_mm,
            settings["interval_mode"],
            settings["target_y"],
            settings["manual_y"],
            settings["min_spacing_mm"],
            settings["edge_mode"],
            geographic,
        )

        if interval_x <= 0 or interval_y <= 0:
            raise ValueError("Wyliczony odstep siatki jest niepoprawny.")

        return {
            "crs": grid_crs,
            "extent": extent,
            "interval_x": interval_x,
            "interval_y": interval_y,
            "offset_x": self._offset_for_axis(extent.xMinimum(), interval_x, settings["edge_mode"]),
            "offset_y": self._offset_for_axis(extent.yMinimum(), interval_y, settings["edge_mode"]),
            "settings": settings,
            "precision": self._annotation_precision(max(interval_x, interval_y), geographic),
            "geographic": geographic,
        }

    def _grid_crs(self, map_item, settings):
        mode = settings["crs_mode"]
        if mode == "wgs84":
            crs = QgsCoordinateReferenceSystem("EPSG:4326")
        elif mode == "custom":
            authid = settings["custom_epsg"].upper()
            if authid and not authid.startswith("EPSG:"):
                authid = f"EPSG:{authid}"
            crs = QgsCoordinateReferenceSystem(authid)
        else:
            crs = self._map_crs(map_item)

        if not crs.isValid():
            raise ValueError("Wybrany CRS siatki jest niepoprawny.")
        return crs

    def _map_crs(self, map_item):
        try:
            crs = map_item.crs()
            if crs and crs.isValid():
                return crs
        except Exception:
            pass
        return QgsProject.instance().crs()

    def _extent_in_grid_crs(self, map_item, grid_crs):
        extent = QgsRectangle(map_item.extent())
        source_crs = self._map_crs(map_item)
        if source_crs.isValid() and grid_crs.isValid() and source_crs != grid_crs:
            transform = QgsCoordinateTransform(source_crs, grid_crs, QgsProject.instance().transformContext())
            extent = transform.transformBoundingBox(extent)
        if extent.width() <= 0 or extent.height() <= 0:
            raise ValueError("Zasieg mapy jest pusty lub niepoprawny.")
        return extent

    def _map_size_mm(self, map_item):
        rect = map_item.rect()
        return max(1.0, rect.width()), max(1.0, rect.height())

    def _page_size_mm(self, map_item):
        try:
            page = map_item.layout().pageCollection().page(0)
            size = page.pageSize()
            return max(1.0, size.width()), max(1.0, size.height())
        except Exception:
            return 0.0, 0.0

    def _map_scale(self, map_item):
        try:
            return float(map_item.scale())
        except Exception:
            return 0.0

    def _interval_for_axis(self, span, size_mm, mode, target_count, manual_interval, min_spacing_mm, edge_mode, geographic):
        if span <= 0:
            return 0.0
        if mode == "manual":
            raw = manual_interval
            if edge_mode == "both":
                target_count = max(2, int(round(span / raw)) + 1)
                return span / (target_count - 1)
            return raw
        if mode == "count":
            raw = span / max(1, target_count - 1)
            return raw if edge_mode == "both" else self._nice_interval(raw, geographic)

        target_count = max(2, int(round(size_mm / max(1.0, min_spacing_mm))) + 1)
        raw = span / max(1, target_count - 1)
        return raw if edge_mode == "both" else self._nice_interval(raw, geographic)

    def _nice_interval(self, raw, geographic):
        if raw <= 0:
            return 0.0
        if geographic:
            for step in self.GEOGRAPHIC_STEPS:
                if raw <= step:
                    return step
            return self._nice_decimal_interval(raw)
        return self._nice_decimal_interval(raw)

    def _nice_decimal_interval(self, raw):
        exponent = math.floor(math.log10(raw))
        base = raw / (10.0 ** exponent)
        for step in self.LOCAL_STEPS:
            if base <= step:
                return step * (10.0 ** exponent)
        return 10.0 ** (exponent + 1)

    def _offset_for_axis(self, minimum, interval, edge_mode):
        if edge_mode in ("first", "both"):
            return minimum
        return 0.0

    def _annotation_precision(self, interval, geographic):
        if geographic:
            if interval >= 1:
                return 4
            return min(8, max(0, int(math.ceil(-math.log10(interval))) + 1))
        if interval >= 1:
            return 0
        return min(6, max(0, int(math.ceil(-math.log10(interval))) + 1))

    def _apply_grid(self, map_item, plan):
        settings = plan["settings"]
        grid = self._find_existing_grid(map_item) if settings["replace_existing"] else None
        if grid is None:
            grid = QgsLayoutItemMapGrid(self._unique_grid_name(map_item), map_item)
            map_item.grids().addGrid(grid)

        grid.setEnabled(True)
        grid.setCrs(plan["crs"])
        self._safe_call(grid, "setUnits", self._enum("MapGridUnit", "MapUnit"))
        grid.setIntervalX(plan["interval_x"])
        grid.setIntervalY(plan["interval_y"])
        grid.setOffsetX(plan["offset_x"])
        grid.setOffsetY(plan["offset_y"])

        self._apply_grid_style(grid, settings)
        self._apply_annotations(grid, plan)

        self._safe_call(grid, "refresh")
        self._safe_call(map_item, "updateBoundingRect")
        self._safe_call(map_item, "refresh")
        self._safe_call(map_item, "update")
        try:
            map_item.layout().refresh()
        except Exception:
            pass

        return grid.name()

    def _refresh_layout(self, layout):
        try:
            layout.refresh()
        except Exception:
            pass

    def _show_success(self, applied):
        if len(applied) == 1:
            _target, plan, grid_name = applied[0]
            self.iface.messageBar().pushSuccess(
                "Smart Layout Grid",
                (
                    f"Ustawiono '{grid_name}': X={self._fmt_interval(plan['interval_x'])}, "
                    f"Y={self._fmt_interval(plan['interval_y'])} ({plan['crs'].authid()})."
                ),
            )
            return

        crs_values = sorted({plan["crs"].authid() or plan["crs"].description() for _target, plan, _grid in applied})
        crs_text = ", ".join(crs_values) if len(crs_values) <= 2 else f"{len(crs_values)} CRS"
        self.iface.messageBar().pushSuccess(
            "Smart Layout Grid",
            f"Ustawiono siatke osobno dla {len(applied)} view ({crs_text}).",
        )

    def _apply_grid_style(self, grid, settings):
        style = {
            "cross": self._enum("MapGridStyle", "Cross"),
            "solid": self._enum("MapGridStyle", "Solid"),
            "frame_annotations": self._enum("MapGridStyle", "FrameAnnotationsOnly"),
        }.get(settings["grid_style"])
        if style is not None:
            grid.setStyle(style)

        frame_style = {
            "zebra": self._enum("MapGridFrameStyle", "Zebra"),
            "exterior_ticks": self._enum("MapGridFrameStyle", "ExteriorTicks"),
            "line_border": self._enum("MapGridFrameStyle", "LineBorder"),
            "none": self._enum("MapGridFrameStyle", "NoFrame"),
        }.get(settings["frame_style"])
        if frame_style is not None:
            grid.setFrameStyle(frame_style)

        self._safe_call(grid, "setGridLineColor", QColor(35, 45, 55, 120))
        self._safe_call(grid, "setGridLineWidth", 0.15)
        self._safe_call(grid, "setCrossLength", 2.5)
        self._safe_call(grid, "setFrameWidth", 2.0)
        self._safe_call(grid, "setFramePenSize", 0.2)
        self._safe_call(grid, "setFramePenColor", QColor(20, 25, 30))
        self._safe_call(grid, "setFrameFillColor1", QColor(255, 255, 255))
        self._safe_call(grid, "setFrameFillColor2", QColor(20, 25, 30))

        for flag_name in ("FrameLeft", "FrameRight", "FrameTop", "FrameBottom"):
            self._safe_call(grid, "setFrameSideFlag", self._enum("MapGridFrameSideFlag", flag_name), True)

    def _apply_annotations(self, grid, plan):
        settings = plan["settings"]
        grid.setAnnotationEnabled(settings["annotations"])
        self._safe_call(grid, "setAnnotationFrameDistance", 2.0)
        self._safe_call(grid, "setAnnotationPrecision", plan["precision"])

        fmt = QgsTextFormat()
        fmt.setSize(7)
        fmt.setColor(QColor(20, 25, 30))
        self._safe_call(grid, "setAnnotationTextFormat", fmt)

        annotation_format = self._annotation_format(settings["annotation_format"], plan["geographic"])
        if annotation_format is not None:
            self._safe_call(grid, "setAnnotationFormat", annotation_format)

        outside = self._enum("MapGridAnnotationPosition", "OutsideMapFrame")
        horizontal = self._enum("MapGridAnnotationDirection", "Horizontal")
        vertical = self._enum("MapGridAnnotationDirection", "Vertical")
        longitude = self._enum("MapGridComponentVisibility", "LongitudeOnly")
        latitude = self._enum("MapGridComponentVisibility", "LatitudeOnly")
        show_all = self._enum("MapGridComponentVisibility", "ShowAll")

        for side_name in ("Left", "Right", "Top", "Bottom"):
            side = self._enum("MapGridBorderSide", side_name)
            if side is None:
                continue
            self._safe_call(grid, "setAnnotationPosition", outside, side)
            if side_name in ("Left", "Right"):
                self._safe_call(grid, "setAnnotationDirection", vertical, side)
                self._safe_call(grid, "setAnnotationDisplay", latitude or show_all, side)
                self._safe_call(grid, "setFrameDivisions", latitude or show_all, side)
            else:
                self._safe_call(grid, "setAnnotationDirection", horizontal, side)
                self._safe_call(grid, "setAnnotationDisplay", longitude or show_all, side)
                self._safe_call(grid, "setFrameDivisions", longitude or show_all, side)

        margin = 0.0 if settings["edge_mode"] == "both" else 2.0
        self._safe_call(grid, "setRotatedAnnotationsEnabled", True)
        self._safe_call(grid, "setRotatedTicksEnabled", True)
        self._safe_call(grid, "setRotatedAnnotationsMarginToCorner", margin)
        self._safe_call(grid, "setRotatedTicksMarginToCorner", margin)

    def _annotation_format(self, requested, geographic):
        if requested == "dms" or (requested == "auto" and geographic):
            return self._enum("MapGridAnnotationFormat", "DegreeMinuteSecond")
        if requested == "decimal" or requested == "auto":
            return self._enum("MapGridAnnotationFormat", "Decimal")
        return None

    def _find_existing_grid(self, map_item):
        stack = map_item.grids()
        try:
            grids = stack.asList()
        except Exception:
            grids = [stack.grid(i) for i in range(stack.size())]
        for grid in grids:
            if grid and grid.name() == self.GRID_NAME:
                return grid
        return None

    def _unique_grid_name(self, map_item):
        existing = set()
        stack = map_item.grids()
        try:
            grids = stack.asList()
        except Exception:
            grids = [stack.grid(i) for i in range(stack.size())]
        for grid in grids:
            if grid:
                existing.add(grid.name())
        if self.GRID_NAME not in existing:
            return self.GRID_NAME
        index = 2
        while f"{self.GRID_NAME} {index}" in existing:
            index += 1
        return f"{self.GRID_NAME} {index}"

    def _enum(self, group_name, value_name):
        value = getattr(QgsLayoutItemMapGrid, value_name, None)
        if value is not None:
            return value
        enum_group = getattr(Qgis, group_name, None)
        if enum_group is not None:
            return getattr(enum_group, value_name, None)
        return None

    def _safe_call(self, obj, method_name, *args):
        method = getattr(obj, method_name, None)
        if method is None or any(arg is None for arg in args):
            return None
        try:
            return method(*args)
        except Exception:
            return None

    def _fmt_interval(self, value):
        if abs(value) >= 1:
            return f"{value:g}"
        return f"{value:.8f}".rstrip("0").rstrip(".")
