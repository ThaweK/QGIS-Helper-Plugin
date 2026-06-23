"""Temporary drafting helpers for geometry construction in QGIS."""

import math
import os
from dataclasses import dataclass
from itertools import combinations

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QBrush, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF
from qgis.PyQt.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsRectangle,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsMapTool, QgsRubberBand


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    label_en: str
    label_pl: str
    description_en: str
    description_pl: str


class ToolIllustrator:
    """Creates small schema images that explain each helper tool."""

    WIDTH = 430
    HEIGHT = 230
    MARGIN = 20
    SCENE_BOTTOM = 185

    TOOL_TEMPLATE = {
        "all_vertices_to_points": "vertices",
        "line_endpoints": "endpoints",
        "line_midpoints": "line_midpoint",
        "segment_midpoints": "segment_midpoints",
        "extend_line_both": "extend",
        "extend_line_start": "extend",
        "extend_line_end": "extend",
        "perpendicular_at_midpoint": "perpendicular",
        "perpendicular_at_start": "perpendicular",
        "perpendicular_at_end": "perpendicular",
        "parallel_offset_left": "parallel",
        "parallel_offset_right": "parallel",
        "line_intersections": "intersection",
        "shortest_connector_two_lines": "shortest",
        "project_vertices_to_baseline": "projection",
        "polygon_centroids": "poly_centroid",
        "polygon_bbox_centers": "bbox_center",
        "polygon_bbox_crosshairs": "bbox_cross",
        "polygon_bbox_diagonals": "bbox_diag",
        "polygon_edge_midpoints": "poly_edge_mid",
        "midpoint_two_points": "mid_two",
        "perpendicular_bisector_two_points": "perp_bisector",
        "extended_baseline_two_points": "baseline_two",
        "angle_bisector_three_points": "angle_bisector",
        "circle_center_three_points": "circumcenter",
        "circle_three_points": "circle_three",
        "circle_diameter_two_points": "circle_diameter",
    }

    @classmethod
    def render(cls, tool_id, caption):
        pixmap = QPixmap(cls.WIDTH, cls.HEIGHT)
        pixmap.fill(QColor(249, 251, 253))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        cls._draw_background(painter)

        template = cls.TOOL_TEMPLATE.get(tool_id, "generic")
        draw_fn = getattr(cls, f"_draw_{template}", cls._draw_generic)
        draw_fn(painter, tool_id)

        painter.fillRect(0, cls.SCENE_BOTTOM, cls.WIDTH, cls.HEIGHT - cls.SCENE_BOTTOM, QColor(239, 245, 250))
        painter.setPen(QColor(25, 35, 45))
        caption_font = QFont()
        caption_font.setPointSize(9)
        caption_font.setBold(True)
        painter.setFont(caption_font)
        painter.drawText(
            QRectF(10, cls.SCENE_BOTTOM + 8, cls.WIDTH - 20, cls.HEIGHT - cls.SCENE_BOTTOM - 12),
            Qt.AlignLeft | Qt.AlignVCenter,
            caption,
        )
        painter.end()
        return pixmap

    @classmethod
    def _draw_background(cls, painter):
        area = QRectF(cls.MARGIN, cls.MARGIN, cls.WIDTH - 2 * cls.MARGIN, cls.SCENE_BOTTOM - cls.MARGIN - 6)
        painter.setPen(QPen(QColor(222, 228, 236), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawRoundedRect(area, 8, 8)

        grid_pen = QPen(QColor(236, 241, 246), 1)
        painter.setPen(grid_pen)
        for i in range(1, 6):
            y = cls.MARGIN + i * ((cls.SCENE_BOTTOM - cls.MARGIN - 6) / 6.0)
            painter.drawLine(QPointF(cls.MARGIN + 6, y), QPointF(cls.WIDTH - cls.MARGIN - 6, y))
        for i in range(1, 10):
            x = cls.MARGIN + i * ((cls.WIDTH - 2 * cls.MARGIN) / 10.0)
            painter.drawLine(QPointF(x, cls.MARGIN + 6), QPointF(x, cls.SCENE_BOTTOM - 6))

    @classmethod
    def _pt(cls, x, y):
        width = cls.WIDTH - 2 * cls.MARGIN
        height = cls.SCENE_BOTTOM - cls.MARGIN - 6
        return QPointF(cls.MARGIN + x * width, cls.MARGIN + y * height)

    @staticmethod
    def _base_pen():
        return QPen(QColor(44, 84, 130), 2)

    @staticmethod
    def _helper_pen():
        return QPen(QColor(230, 57, 70), 2, Qt.DashLine)

    @staticmethod
    def _mark_pen():
        return QPen(QColor(14, 164, 120), 2)

    @classmethod
    def _draw_point(cls, painter, point, radius=4, color=QColor(14, 164, 120)):
        painter.setPen(QPen(color, 1.2))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(point, radius, radius)

    @classmethod
    def _draw_polyline(cls, painter, points, pen):
        painter.setPen(pen)
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

    @classmethod
    def _draw_generic(cls, painter, _tool_id):
        painter.setPen(QPen(QColor(80, 95, 110), 2))
        painter.drawText(
            QRectF(cls.MARGIN + 16, cls.MARGIN + 20, cls.WIDTH - 2 * cls.MARGIN - 32, 50),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Geometry helper schema",
        )

    @classmethod
    def _draw_vertices(cls, painter, _tool_id):
        pts = [cls._pt(0.10, 0.70), cls._pt(0.28, 0.40), cls._pt(0.50, 0.58), cls._pt(0.72, 0.28), cls._pt(0.88, 0.60)]
        cls._draw_polyline(painter, pts, cls._base_pen())
        for p in pts:
            cls._draw_point(painter, p)

    @classmethod
    def _draw_endpoints(cls, painter, _tool_id):
        p1 = cls._pt(0.12, 0.72)
        p2 = cls._pt(0.88, 0.28)
        cls._draw_polyline(painter, [p1, p2], cls._base_pen())
        cls._draw_point(painter, p1, color=QColor(230, 57, 70))
        cls._draw_point(painter, p2, color=QColor(230, 57, 70))

    @classmethod
    def _draw_line_midpoint(cls, painter, _tool_id):
        p1 = cls._pt(0.14, 0.72)
        p2 = cls._pt(0.88, 0.32)
        cls._draw_polyline(painter, [p1, p2], cls._base_pen())
        mid = cls._pt(0.51, 0.52)
        cls._draw_point(painter, mid)

    @classmethod
    def _draw_segment_midpoints(cls, painter, _tool_id):
        pts = [cls._pt(0.08, 0.75), cls._pt(0.30, 0.45), cls._pt(0.52, 0.64), cls._pt(0.76, 0.30), cls._pt(0.92, 0.56)]
        cls._draw_polyline(painter, pts, cls._base_pen())
        for i in range(len(pts) - 1):
            m = QPointF((pts[i].x() + pts[i + 1].x()) / 2.0, (pts[i].y() + pts[i + 1].y()) / 2.0)
            cls._draw_point(painter, m)

    @classmethod
    def _draw_extend(cls, painter, tool_id):
        core_start = cls._pt(0.25, 0.62)
        core_end = cls._pt(0.75, 0.38)
        cls._draw_polyline(painter, [core_start, core_end], cls._base_pen())

        full_start = cls._pt(0.10, 0.72)
        full_end = cls._pt(0.90, 0.28)
        if tool_id in {"extend_line_both", "extend_line_start"}:
            cls._draw_polyline(painter, [full_start, core_start], cls._helper_pen())
        if tool_id in {"extend_line_both", "extend_line_end"}:
            cls._draw_polyline(painter, [core_end, full_end], cls._helper_pen())

    @classmethod
    def _draw_perpendicular(cls, painter, tool_id):
        a = cls._pt(0.16, 0.68)
        b = cls._pt(0.86, 0.34)
        cls._draw_polyline(painter, [a, b], cls._base_pen())

        if tool_id == "perpendicular_at_start":
            anchor = a
        elif tool_id == "perpendicular_at_end":
            anchor = b
        else:
            anchor = cls._pt(0.51, 0.51)
        p1 = QPointF(anchor.x() - 36, anchor.y() - 24)
        p2 = QPointF(anchor.x() + 36, anchor.y() + 24)
        cls._draw_polyline(painter, [p1, p2], cls._helper_pen())
        cls._draw_point(painter, anchor)

    @classmethod
    def _draw_parallel(cls, painter, tool_id):
        base_a = cls._pt(0.12, 0.68)
        base_b = cls._pt(0.88, 0.38)
        cls._draw_polyline(painter, [base_a, base_b], cls._base_pen())
        delta = -28 if tool_id == "parallel_offset_left" else 28
        off_a = QPointF(base_a.x(), base_a.y() + delta)
        off_b = QPointF(base_b.x(), base_b.y() + delta)
        cls._draw_polyline(painter, [off_a, off_b], cls._helper_pen())

    @classmethod
    def _draw_intersection(cls, painter, _tool_id):
        l1a = cls._pt(0.15, 0.73)
        l1b = cls._pt(0.86, 0.30)
        l2a = cls._pt(0.18, 0.28)
        l2b = cls._pt(0.84, 0.76)
        cls._draw_polyline(painter, [l1a, l1b], cls._base_pen())
        cls._draw_polyline(painter, [l2a, l2b], cls._helper_pen())
        cls._draw_point(painter, cls._pt(0.50, 0.51))

    @classmethod
    def _draw_shortest(cls, painter, _tool_id):
        l1a = cls._pt(0.16, 0.32)
        l1b = cls._pt(0.44, 0.60)
        l2a = cls._pt(0.66, 0.34)
        l2b = cls._pt(0.90, 0.66)
        cls._draw_polyline(painter, [l1a, l1b], cls._base_pen())
        cls._draw_polyline(painter, [l2a, l2b], cls._base_pen())
        cls._draw_polyline(painter, [cls._pt(0.44, 0.60), cls._pt(0.66, 0.34)], cls._helper_pen())

    @classmethod
    def _draw_projection(cls, painter, _tool_id):
        base_a = cls._pt(0.10, 0.70)
        base_b = cls._pt(0.90, 0.70)
        cls._draw_polyline(painter, [base_a, base_b], cls._base_pen())
        p1 = cls._pt(0.30, 0.35)
        p2 = cls._pt(0.58, 0.45)
        cls._draw_point(painter, p1, color=QColor(44, 84, 130))
        cls._draw_point(painter, p2, color=QColor(44, 84, 130))
        cls._draw_polyline(painter, [p1, cls._pt(0.30, 0.70)], cls._helper_pen())
        cls._draw_polyline(painter, [p2, cls._pt(0.58, 0.70)], cls._helper_pen())
        cls._draw_point(painter, cls._pt(0.30, 0.70))
        cls._draw_point(painter, cls._pt(0.58, 0.70))

    @classmethod
    def _draw_polygon(cls, painter):
        poly = QPolygonF([cls._pt(0.20, 0.70), cls._pt(0.30, 0.34), cls._pt(0.58, 0.26), cls._pt(0.80, 0.52), cls._pt(0.66, 0.78), cls._pt(0.32, 0.82)])
        painter.setPen(cls._base_pen())
        painter.setBrush(QBrush(QColor(44, 84, 130, 22)))
        painter.drawPolygon(poly)
        return poly

    @classmethod
    def _draw_poly_centroid(cls, painter, _tool_id):
        cls._draw_polygon(painter)
        cls._draw_point(painter, cls._pt(0.50, 0.56))

    @classmethod
    def _draw_bbox_center(cls, painter, _tool_id):
        cls._draw_polygon(painter)
        painter.setPen(cls._helper_pen())
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(cls._pt(0.20, 0.30), cls._pt(0.80, 0.82))
        painter.drawRect(rect)
        cls._draw_point(painter, cls._pt(0.50, 0.56))

    @classmethod
    def _draw_bbox_cross(cls, painter, _tool_id):
        painter.setPen(cls._base_pen())
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(cls._pt(0.24, 0.28), cls._pt(0.80, 0.82))
        painter.drawRect(rect)
        cls._draw_polyline(painter, [cls._pt(0.52, 0.28), cls._pt(0.52, 0.82)], cls._helper_pen())
        cls._draw_polyline(painter, [cls._pt(0.24, 0.55), cls._pt(0.80, 0.55)], cls._helper_pen())
        cls._draw_point(painter, cls._pt(0.52, 0.55))

    @classmethod
    def _draw_bbox_diag(cls, painter, _tool_id):
        painter.setPen(cls._base_pen())
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(cls._pt(0.24, 0.28), cls._pt(0.80, 0.82))
        painter.drawRect(rect)
        cls._draw_polyline(painter, [cls._pt(0.24, 0.28), cls._pt(0.80, 0.82)], cls._helper_pen())
        cls._draw_polyline(painter, [cls._pt(0.24, 0.82), cls._pt(0.80, 0.28)], cls._helper_pen())

    @classmethod
    def _draw_poly_edge_mid(cls, painter, _tool_id):
        poly = cls._draw_polygon(painter)
        for i in range(poly.count()):
            p1 = poly[i]
            p2 = poly[(i + 1) % poly.count()]
            midpoint = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
            cls._draw_point(painter, midpoint)

    @classmethod
    def _draw_mid_two(cls, painter, _tool_id):
        p1 = cls._pt(0.24, 0.68)
        p2 = cls._pt(0.78, 0.38)
        cls._draw_polyline(painter, [p1, p2], cls._base_pen())
        cls._draw_point(painter, p1, color=QColor(44, 84, 130))
        cls._draw_point(painter, p2, color=QColor(44, 84, 130))
        cls._draw_point(painter, cls._pt(0.51, 0.53))

    @classmethod
    def _draw_perp_bisector(cls, painter, _tool_id):
        p1 = cls._pt(0.24, 0.68)
        p2 = cls._pt(0.78, 0.38)
        cls._draw_polyline(painter, [p1, p2], cls._base_pen())
        center = cls._pt(0.51, 0.53)
        cls._draw_polyline(painter, [QPointF(center.x() - 40, center.y() - 28), QPointF(center.x() + 40, center.y() + 28)], cls._helper_pen())
        cls._draw_point(painter, center)

    @classmethod
    def _draw_baseline_two(cls, painter, _tool_id):
        core_a = cls._pt(0.30, 0.64)
        core_b = cls._pt(0.70, 0.40)
        full_a = cls._pt(0.14, 0.74)
        full_b = cls._pt(0.86, 0.30)
        cls._draw_polyline(painter, [core_a, core_b], cls._base_pen())
        cls._draw_polyline(painter, [full_a, core_a], cls._helper_pen())
        cls._draw_polyline(painter, [core_b, full_b], cls._helper_pen())
        cls._draw_point(painter, core_a, color=QColor(44, 84, 130))
        cls._draw_point(painter, core_b, color=QColor(44, 84, 130))

    @classmethod
    def _draw_angle_bisector(cls, painter, _tool_id):
        vertex = cls._pt(0.34, 0.66)
        p1 = cls._pt(0.76, 0.62)
        p2 = cls._pt(0.66, 0.26)
        cls._draw_polyline(painter, [vertex, p1], cls._base_pen())
        cls._draw_polyline(painter, [vertex, p2], cls._base_pen())
        bis_end = cls._pt(0.78, 0.44)
        cls._draw_polyline(painter, [vertex, bis_end], cls._helper_pen())
        cls._draw_point(painter, vertex)

    @classmethod
    def _draw_circumcenter(cls, painter, _tool_id):
        a = cls._pt(0.26, 0.70)
        b = cls._pt(0.48, 0.28)
        c = cls._pt(0.78, 0.66)
        cls._draw_polyline(painter, [a, b, c, a], cls._base_pen())
        cls._draw_point(painter, cls._pt(0.52, 0.54))

    @classmethod
    def _draw_circle_three(cls, painter, _tool_id):
        center = cls._pt(0.52, 0.54)
        radius = 52
        painter.setPen(cls._helper_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)
        pts = [cls._pt(0.52, 0.29), cls._pt(0.72, 0.66), cls._pt(0.34, 0.66)]
        for pt in pts:
            cls._draw_point(painter, pt, color=QColor(44, 84, 130))

    @classmethod
    def _draw_circle_diameter(cls, painter, _tool_id):
        center = cls._pt(0.52, 0.54)
        radius = 54
        painter.setPen(cls._base_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, radius, radius)
        a = QPointF(center.x() - radius, center.y())
        b = QPointF(center.x() + radius, center.y())
        cls._draw_polyline(painter, [a, b], cls._helper_pen())
        cls._draw_point(painter, a, color=QColor(44, 84, 130))
        cls._draw_point(painter, b, color=QColor(44, 84, 130))


class FeaturePickerMapTool(QgsMapTool):
    """Pick features from active layer by clicking on the map."""

    def __init__(self, iface, picked_callback, finished_callback):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self._picked_callback = picked_callback
        self._finished_callback = finished_callback

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            if self._finished_callback:
                self._finished_callback()
            return

        if event.button() != Qt.LeftButton:
            return

        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            if self._picked_callback:
                self._picked_callback(None, "Active layer must be a vector layer.")
            return

        clicked_map_point = self.toMapCoordinates(event.pos())
        feature = self._find_nearest_feature(layer, clicked_map_point)
        if feature is None:
            if self._picked_callback:
                self._picked_callback(None, "No feature found at clicked position.")
            return

        additive = bool(event.modifiers() & Qt.ShiftModifier)
        if not additive:
            layer.removeSelection()
        layer.select(feature.id())

        if self._picked_callback:
            self._picked_callback(feature.id(), None)

    def _find_nearest_feature(self, layer, map_point):
        tol_map = self.canvas.mapUnitsPerPixel() * 10.0

        try:
            map_min = QgsPointXY(map_point.x() - tol_map, map_point.y() - tol_map)
            map_max = QgsPointXY(map_point.x() + tol_map, map_point.y() + tol_map)
            layer_min = self.toLayerCoordinates(layer, map_min)
            layer_max = self.toLayerCoordinates(layer, map_max)
            layer_click = self.toLayerCoordinates(layer, map_point)
        except Exception:
            return None

        rect = QgsRectangle(
            min(layer_min.x(), layer_max.x()),
            min(layer_min.y(), layer_max.y()),
            max(layer_min.x(), layer_max.x()),
            max(layer_min.y(), layer_max.y()),
        )

        req = QgsFeatureRequest().setFilterRect(rect)
        click_geom = QgsGeometry.fromPointXY(QgsPointXY(layer_click.x(), layer_click.y()))

        nearest = None
        nearest_dist = None
        for feature in layer.getFeatures(req):
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            dist = geom.distance(click_geom)
            if nearest_dist is None or dist < nearest_dist:
                nearest = feature
                nearest_dist = dist

        return nearest


class PreviewManager:
    """Displays temporary preview geometries with rubber bands."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._bands = []

    def clear(self):
        for band in self._bands:
            try:
                self.canvas.scene().removeItem(band)
            except Exception:
                pass
        self._bands = []

    def show_geometries(self, geometries):
        self.clear()

        for geom in geometries:
            if geom is None or geom.isEmpty():
                continue
            gtype = QgsWkbTypes.geometryType(geom.wkbType())
            band = QgsRubberBand(self.canvas, gtype)
            band.setToGeometry(geom, None)

            if gtype == QgsWkbTypes.PointGeometry:
                band.setColor(QColor(10, 215, 95, 240))
                band.setWidth(2)
                band.setIcon(QgsRubberBand.ICON_CROSS)
                band.setIconSize(8)
            elif gtype == QgsWkbTypes.LineGeometry:
                band.setColor(QColor(10, 215, 95, 220))
                band.setWidth(2)
            elif gtype == QgsWkbTypes.PolygonGeometry:
                band.setColor(QColor(10, 215, 95, 220))
                if hasattr(band, "setFillColor"):
                    band.setFillColor(QColor(10, 215, 95, 45))
                band.setWidth(1)

            band.show()
            self._bands.append(band)


class DraftingHelpersDialog(QDialog):
    """UI for selecting and generating temporary helper geometries."""

    def __init__(self, tool_specs, parent=None):
        super().__init__(parent)
        self._tool_specs = list(tool_specs)
        self._tool_specs_by_id = {spec.tool_id: spec for spec in self._tool_specs}
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("Temporary Drafting Helpers")
        self.setMinimumWidth(760)

        root = QVBoxLayout()

        intro = QLabel(
            "Select helper tool, choose parameters, then run on selected features in active layer. "
            "Use Names language to switch English/Polish tool names."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()

        self.language_combo = QComboBox()
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Polski", "pl")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        form.addRow("Names language:", self.language_combo)

        self.tool_combo = QComboBox()
        self.tool_combo.currentIndexChanged.connect(self._update_description)
        form.addRow("Helper tool:", self.tool_combo)

        self.extension_spin = QDoubleSpinBox()
        self.extension_spin.setRange(0.01, 1000000.0)
        self.extension_spin.setDecimals(3)
        self.extension_spin.setValue(25.0)
        self.extension_spin.setSuffix(" map units")
        form.addRow("Extension length:", self.extension_spin)
        self.extend_segments_checkbox = QCheckBox("Extend each segment in multiline/polyline")
        self.extend_segments_checkbox.setChecked(False)
        form.addRow("", self.extend_segments_checkbox)

        self.guide_spin = QDoubleSpinBox()
        self.guide_spin.setRange(0.01, 1000000.0)
        self.guide_spin.setDecimals(3)
        self.guide_spin.setValue(40.0)
        self.guide_spin.setSuffix(" map units")
        form.addRow("Guide length:", self.guide_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(0.01, 1000000.0)
        self.offset_spin.setDecimals(3)
        self.offset_spin.setValue(10.0)
        self.offset_spin.setSuffix(" map units")
        form.addRow("Offset distance:", self.offset_spin)

        self.circle_segments_spin = QSpinBox()
        self.circle_segments_spin.setRange(16, 720)
        self.circle_segments_spin.setValue(72)
        form.addRow("Circle segments:", self.circle_segments_spin)

        root.addLayout(form)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #444;")
        root.addWidget(self.description_label)

        self.illustration_label = QLabel()
        self.illustration_label.setFixedSize(ToolIllustrator.WIDTH, ToolIllustrator.HEIGHT)
        self.illustration_label.setAlignment(Qt.AlignCenter)
        self.illustration_label.setStyleSheet("border: 1px solid #ccd6e2; border-radius: 4px; background: #f9fbfd;")
        root.addWidget(self.illustration_label, alignment=Qt.AlignHCenter)

        self.auto_preview_checkbox = QCheckBox("Auto preview on parameter/selection change")
        self.auto_preview_checkbox.setChecked(True)
        root.addWidget(self.auto_preview_checkbox)

        self.pick_help_label = QLabel(
            "Pick on Map: left click to select feature, Shift+click to add, right click to finish pick mode."
        )
        self.pick_help_label.setWordWrap(True)
        self.pick_help_label.setStyleSheet("color: #666;")
        root.addWidget(self.pick_help_label)

        buttons = QHBoxLayout()
        self.pick_button = QPushButton("Pick on Map")
        self.preview_button = QPushButton("Preview")
        self.clear_preview_button = QPushButton("Clear Preview")
        self.run_button = QPushButton("Create Helpers")
        self.clear_button = QPushButton("Clear All Helpers")
        self.close_button = QPushButton("Close")

        buttons.addWidget(self.pick_button)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.clear_preview_button)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        root.addLayout(buttons)

        self.close_button.clicked.connect(self.close)

        self.setLayout(root)
        self._update_extension_mode_label()
        self._populate_tool_combo()
        self._update_description()

    def _update_description(self):
        tool_id = self.selected_tool_id()
        spec = self._tool_specs_by_id.get(tool_id)
        if spec:
            label = self._label_for_spec(spec)
            description = self._description_for_spec(spec)
            self.description_label.setText(description)
            self.illustration_label.setPixmap(ToolIllustrator.render(tool_id, label))
        else:
            self.description_label.setText("")
            self.illustration_label.clear()

    def selected_tool_id(self):
        return self.tool_combo.currentData()

    def selected_tool_label(self):
        spec = self._tool_specs_by_id.get(self.selected_tool_id())
        if spec is None:
            return self.selected_tool_id()
        return self._label_for_spec(spec)

    def parameters(self):
        return {
            "extension": float(self.extension_spin.value()),
            "guide": float(self.guide_spin.value()),
            "offset": float(self.offset_spin.value()),
            "circle_segments": int(self.circle_segments_spin.value()),
            "extend_each_segment_multiline": bool(self.extend_segments_checkbox.isChecked()),
        }

    def current_language(self):
        return self.language_combo.currentData()

    def _on_language_changed(self):
        current_tool_id = self.selected_tool_id()
        self._populate_tool_combo(selected_tool_id=current_tool_id)
        self._update_extension_mode_label()
        self._update_description()

    def _populate_tool_combo(self, selected_tool_id=None):
        self.tool_combo.blockSignals(True)
        self.tool_combo.clear()
        for spec in self._tool_specs:
            self.tool_combo.addItem(self._label_for_spec(spec), spec.tool_id)

        if selected_tool_id:
            idx = self.tool_combo.findData(selected_tool_id)
            if idx >= 0:
                self.tool_combo.setCurrentIndex(idx)
        self.tool_combo.blockSignals(False)

    def _label_for_spec(self, spec):
        return spec.label_pl if self.current_language() == "pl" else spec.label_en

    def _description_for_spec(self, spec):
        return spec.description_pl if self.current_language() == "pl" else spec.description_en

    def _update_extension_mode_label(self):
        if self.current_language() == "pl":
            self.extend_segments_checkbox.setText("Dla multiline/polyline: wydluz kazdy segment osobno")
        else:
            self.extend_segments_checkbox.setText("Extend each segment in multiline/polyline")

    def auto_preview_enabled(self):
        return self.auto_preview_checkbox.isChecked()


class HelperLayerManager:
    """Manages temporary helper layers grouped under one project group."""

    GROUP_NAME = "QPH Temporary Helpers"
    PROPERTY_KEY = "qph_temp_helper"
    PROPERTY_KIND = "qph_temp_helper_kind"

    LAYER_CONFIG = {
        "point": {
            "name": "QPH Helpers - Points",
            "uri": "Point",
            "symbol": QgsMarkerSymbol.createSimple(
                {
                    "name": "cross",
                    "color": "235,0,0",
                    "size": "2.5",
                    "outline_color": "235,0,0",
                }
            ),
        },
        "line": {
            "name": "QPH Helpers - Lines",
            "uri": "LineString",
            "symbol": QgsLineSymbol.createSimple(
                {
                    "line_color": "235,0,0",
                    "line_width": "0.7",
                    "line_style": "dash",
                }
            ),
        },
        "polygon": {
            "name": "QPH Helpers - Polygons",
            "uri": "Polygon",
            "symbol": QgsFillSymbol.createSimple(
                {
                    "color": "235,0,0,35",
                    "outline_color": "235,0,0",
                    "outline_style": "dash",
                    "outline_width": "0.5",
                }
            ),
        },
    }

    def add_geometries(self, tool_label, geometries, crs_authid):
        buckets = {"point": [], "line": [], "polygon": []}

        for geom in geometries:
            if geom is None or geom.isEmpty():
                continue

            gtype = QgsWkbTypes.geometryType(geom.wkbType())
            if gtype == QgsWkbTypes.PointGeometry:
                buckets["point"].append(geom)
            elif gtype == QgsWkbTypes.LineGeometry:
                buckets["line"].append(geom)
            elif gtype == QgsWkbTypes.PolygonGeometry:
                buckets["polygon"].append(geom)

        added = 0
        for kind, geoms in buckets.items():
            if not geoms:
                continue

            layer = self._ensure_layer(kind, crs_authid)
            features = []
            for geom in geoms:
                feat = QgsFeature(layer.fields())
                feat.setAttribute("tool", tool_label)
                feat.setGeometry(geom)
                features.append(feat)

            if features:
                layer.dataProvider().addFeatures(features)
                layer.updateExtents()
                layer.triggerRepaint()
                added += len(features)

        return added

    def clear(self):
        project = QgsProject.instance()
        to_remove = [
            layer.id()
            for layer in project.mapLayers().values()
            if bool(layer.customProperty(self.PROPERTY_KEY, False))
        ]

        for layer_id in to_remove:
            project.removeMapLayer(layer_id)

        group = project.layerTreeRoot().findGroup(self.GROUP_NAME)
        if group is not None and not group.children():
            project.layerTreeRoot().removeChildNode(group)

        return len(to_remove)

    def _ensure_layer(self, kind, crs_authid):
        existing = self._find_layer(kind)
        if existing is not None:
            return existing

        cfg = self.LAYER_CONFIG[kind]
        uri = f"{cfg['uri']}?crs={crs_authid}"
        layer = QgsVectorLayer(uri, cfg["name"], "memory")
        provider = layer.dataProvider()
        provider.addAttributes([QgsField("tool", QVariant.String)])
        layer.updateFields()

        renderer = layer.renderer()
        if renderer:
            renderer.setSymbol(cfg["symbol"])

        layer.setCustomProperty(self.PROPERTY_KEY, True)
        layer.setCustomProperty(self.PROPERTY_KIND, kind)

        project = QgsProject.instance()
        group = project.layerTreeRoot().findGroup(self.GROUP_NAME)
        if group is None:
            group = project.layerTreeRoot().insertGroup(0, self.GROUP_NAME)

        project.addMapLayer(layer, False)
        group.insertLayer(0, layer)
        return layer

    def _find_layer(self, kind):
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            if not bool(layer.customProperty(self.PROPERTY_KEY, False)):
                continue
            if layer.customProperty(self.PROPERTY_KIND, "") == kind:
                return layer
        return None


class DraftingHelpersPlugin:
    """Temporary geometric helper tools for fast drafting workflows."""

    TOOL_SPECS = [
        ToolSpec(
            "all_vertices_to_points",
            "01. All Vertices to Points",
            "01. Wszystkie wierzcholki na punkty",
            "Creates temporary points for every vertex of selected features.",
            "Tworzy tymczasowe punkty dla kazdego wierzcholka zaznaczonych obiektow.",
        ),
        ToolSpec(
            "line_endpoints",
            "02. Line Endpoints",
            "02. Konce linii",
            "Creates start and end points for each selected line part.",
            "Tworzy punkt poczatkowy i koncowy dla kazdej zaznaczonej czesci linii.",
        ),
        ToolSpec(
            "line_midpoints",
            "03. Line Midpoints",
            "03. Srodki linii",
            "Creates one midpoint for each selected line part.",
            "Tworzy jeden punkt srodkowy dla kazdej zaznaczonej czesci linii.",
        ),
        ToolSpec(
            "segment_midpoints",
            "04. Segment Midpoints",
            "04. Srodki segmentow",
            "Creates a midpoint for every segment of selected lines or polygon rings.",
            "Tworzy punkt srodkowy dla kazdego segmentu zaznaczonych linii lub pierscieni poligonow.",
        ),
        ToolSpec(
            "extend_line_both",
            "05. Extend Lines (Both Ends)",
            "05. Wydluz linie (oba konce)",
            "Extends each selected line at both ends by Extension length.",
            "Wydluza kazda zaznaczona linie na obu koncach o wartosc Wydluzenie.",
        ),
        ToolSpec(
            "extend_line_start",
            "06. Extend Lines (Start)",
            "06. Wydluz linie (poczatek)",
            "Extends each selected line only at the start.",
            "Wydluza kazda zaznaczona linie tylko od poczatku.",
        ),
        ToolSpec(
            "extend_line_end",
            "07. Extend Lines (End)",
            "07. Wydluz linie (koniec)",
            "Extends each selected line only at the end.",
            "Wydluza kazda zaznaczona linie tylko od konca.",
        ),
        ToolSpec(
            "perpendicular_at_midpoint",
            "08. Perpendicular at Line Midpoint",
            "08. Prostopadla w srodku linii",
            "Creates perpendicular guide centered at each selected line midpoint.",
            "Tworzy linie pomocnicza prostopadla, wycentrowana w srodku zaznaczonej linii.",
        ),
        ToolSpec(
            "perpendicular_at_start",
            "09. Perpendicular at Line Start",
            "09. Prostopadla na poczatku linii",
            "Creates perpendicular guide at each selected line start.",
            "Tworzy linie pomocnicza prostopadla na poczatku kazdej zaznaczonej linii.",
        ),
        ToolSpec(
            "perpendicular_at_end",
            "10. Perpendicular at Line End",
            "10. Prostopadla na koncu linii",
            "Creates perpendicular guide at each selected line end.",
            "Tworzy linie pomocnicza prostopadla na koncu kazdej zaznaczonej linii.",
        ),
        ToolSpec(
            "parallel_offset_left",
            "11. Parallel Offset Left",
            "11. Rownolegle przesuniecie w lewo",
            "Creates left-side offset curves for selected lines (Offset distance).",
            "Tworzy krzywe przesuniete rownolegle po lewej stronie zaznaczonych linii (Przesuniecie).",
        ),
        ToolSpec(
            "parallel_offset_right",
            "12. Parallel Offset Right",
            "12. Rownolegle przesuniecie w prawo",
            "Creates right-side offset curves for selected lines (Offset distance).",
            "Tworzy krzywe przesuniete rownolegle po prawej stronie zaznaczonych linii (Przesuniecie).",
        ),
        ToolSpec(
            "line_intersections",
            "13. Line Intersections",
            "13. Przeciecia linii",
            "Finds intersection points for selected lines.",
            "Wyznacza punkty przeciec zaznaczonych linii.",
        ),
        ToolSpec(
            "shortest_connector_two_lines",
            "14. Shortest Connector (Two Lines)",
            "14. Najkrotszy lacznik (2 linie)",
            "Creates shortest connecting helper line between first two selected lines.",
            "Tworzy najkrotszy lacznik pomocniczy pomiedzy dwiema pierwszymi zaznaczonymi liniami.",
        ),
        ToolSpec(
            "project_vertices_to_baseline",
            "15. Project Vertices to Baseline",
            "15. Rzuty wierzcholkow na baze",
            "Projects vertices of selected lines (except first) onto first selected line.",
            "Rzutuje wierzcholki zaznaczonych linii (poza pierwsza) na pierwsza zaznaczona linie.",
        ),
        ToolSpec(
            "polygon_centroids",
            "16. Polygon Centroids",
            "16. Srodki ciezkosci poligonow",
            "Creates centroid points for selected polygons.",
            "Tworzy punkty srodkow ciezkosci zaznaczonych poligonow.",
        ),
        ToolSpec(
            "polygon_bbox_centers",
            "17. Polygon BBOX Centers",
            "17. Srodki BBOX poligonow",
            "Creates center points of bounding boxes for selected polygons.",
            "Tworzy punkty srodka obwiedni BBOX dla zaznaczonych poligonow.",
        ),
        ToolSpec(
            "polygon_bbox_crosshairs",
            "18. Polygon BBOX Crosshairs",
            "18. Krzyz BBOX poligonow",
            "Creates vertical and horizontal center guides for selected polygon bounding boxes.",
            "Tworzy pionowe i poziome linie pomocnicze przechodzace przez srodek BBOX poligonow.",
        ),
        ToolSpec(
            "polygon_bbox_diagonals",
            "19. Polygon BBOX Diagonals",
            "19. Przekatne BBOX poligonow",
            "Creates both bounding box diagonals for selected polygons.",
            "Tworzy obie przekatne obwiedni BBOX dla zaznaczonych poligonow.",
        ),
        ToolSpec(
            "polygon_edge_midpoints",
            "20. Polygon Edge Midpoints",
            "20. Srodki krawedzi poligonu",
            "Creates midpoint points for every polygon edge.",
            "Tworzy punkty srodkowe dla kazdej krawedzi poligonu.",
        ),
        ToolSpec(
            "midpoint_two_points",
            "21. Midpoint from Two Points",
            "21. Srodek z dwoch punktow",
            "Creates one midpoint from first two selected points.",
            "Tworzy jeden punkt srodkowy na podstawie dwoch pierwszych zaznaczonych punktow.",
        ),
        ToolSpec(
            "perpendicular_bisector_two_points",
            "22. Perpendicular Bisector (Two Points)",
            "22. Symetralna odcinka (2 punkty)",
            "Creates perpendicular bisector helper line from first two selected points.",
            "Tworzy pomocnicza symetralna odcinka wyznaczonego przez dwa pierwsze zaznaczone punkty.",
        ),
        ToolSpec(
            "extended_baseline_two_points",
            "23. Extended Baseline (Two Points)",
            "23. Wydluzona baza (2 punkty)",
            "Creates baseline through first two selected points and extends both ends.",
            "Tworzy baze przechodzaca przez dwa pierwsze punkty i wydluza ja na obu koncach.",
        ),
        ToolSpec(
            "angle_bisector_three_points",
            "24. Angle Bisector (Three Points)",
            "24. Dwusieczna kata (3 punkty)",
            "Creates angle bisector ray from first three selected points (vertex = 2nd point).",
            "Tworzy promien dwusiecznej kata z trzech pierwszych punktow (wierzcholek to 2. punkt).",
        ),
        ToolSpec(
            "circle_center_three_points",
            "25. Circle Center (Three Points)",
            "25. Srodek okregu (3 punkty)",
            "Computes circumcenter point from first three selected points.",
            "Wyznacza punkt srodka okregu przechodzacego przez trzy pierwsze zaznaczone punkty.",
        ),
        ToolSpec(
            "circle_three_points",
            "26. Circle Through Three Points",
            "26. Okreg przez 3 punkty",
            "Creates helper circle passing through first three selected points.",
            "Tworzy pomocniczy okrag przechodzacy przez trzy pierwsze zaznaczone punkty.",
        ),
        ToolSpec(
            "circle_diameter_two_points",
            "27. Circle from Diameter (Two Points)",
            "27. Okreg ze srednicy (2 punkty)",
            "Creates helper circle where first two selected points define diameter.",
            "Tworzy pomocniczy okrag, gdzie dwa pierwsze punkty wyznaczaja srednice.",
        ),
    ]

    def __init__(self, iface, toolbar=None):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = "QGIS Plugin Helper"
        self._shared_toolbar = toolbar
        self.toolbar = None
        self.actions = []
        self.dialog = None
        self.layer_manager = HelperLayerManager()
        self.preview_manager = PreviewManager(self.iface.mapCanvas())
        self._feature_picker_tool = None
        self._previous_map_tool = None
        self._selection_layer = None

        self._tool_handlers = {
            "all_vertices_to_points": self._tool_all_vertices_to_points,
            "line_endpoints": self._tool_line_endpoints,
            "line_midpoints": self._tool_line_midpoints,
            "segment_midpoints": self._tool_segment_midpoints,
            "extend_line_both": self._tool_extend_line_both,
            "extend_line_start": self._tool_extend_line_start,
            "extend_line_end": self._tool_extend_line_end,
            "perpendicular_at_midpoint": self._tool_perpendicular_at_midpoint,
            "perpendicular_at_start": self._tool_perpendicular_at_start,
            "perpendicular_at_end": self._tool_perpendicular_at_end,
            "parallel_offset_left": self._tool_parallel_offset_left,
            "parallel_offset_right": self._tool_parallel_offset_right,
            "line_intersections": self._tool_line_intersections,
            "shortest_connector_two_lines": self._tool_shortest_connector_two_lines,
            "project_vertices_to_baseline": self._tool_project_vertices_to_baseline,
            "polygon_centroids": self._tool_polygon_centroids,
            "polygon_bbox_centers": self._tool_polygon_bbox_centers,
            "polygon_bbox_crosshairs": self._tool_polygon_bbox_crosshairs,
            "polygon_bbox_diagonals": self._tool_polygon_bbox_diagonals,
            "polygon_edge_midpoints": self._tool_polygon_edge_midpoints,
            "midpoint_two_points": self._tool_midpoint_two_points,
            "perpendicular_bisector_two_points": self._tool_perpendicular_bisector_two_points,
            "extended_baseline_two_points": self._tool_extended_baseline_two_points,
            "angle_bisector_three_points": self._tool_angle_bisector_three_points,
            "circle_center_three_points": self._tool_circle_center_three_points,
            "circle_three_points": self._tool_circle_three_points,
            "circle_diameter_two_points": self._tool_circle_diameter_two_points,
        }

    def initGui(self):
        if self._shared_toolbar is None:
            self.toolbar = self.iface.addToolBar("Drafting Helpers")
            self.toolbar.setObjectName("DraftingHelpers")
        else:
            self.toolbar = self._shared_toolbar

        icon_path = os.path.join(self.plugin_dir, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        open_action = QAction(icon, "Temporary Drafting Helpers", self.iface.mainWindow())
        open_action.triggered.connect(self.show_dialog)
        self._register_action(open_action)

        clear_action = QAction(icon, "Clear Temporary Helpers", self.iface.mainWindow())
        clear_action.triggered.connect(self.clear_helpers)
        self._register_action(clear_action)

        self._connect_layer_signals(self.iface.activeLayer())
        try:
            self.iface.currentLayerChanged.connect(self._on_current_layer_changed)
        except Exception:
            pass

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        self._disconnect_layer_signals()
        try:
            self.iface.currentLayerChanged.disconnect(self._on_current_layer_changed)
        except TypeError:
            pass

        self._stop_pick_mode(silent=True)
        self.clear_preview(silent=True)

        if self._shared_toolbar is None and self.toolbar:
            del self.toolbar

        if self.dialog:
            self.dialog.close()
            self.dialog = None

    def show_dialog(self):
        if self.dialog is None:
            self.dialog = DraftingHelpersDialog(self.TOOL_SPECS, self.iface.mainWindow())
            self.dialog.run_button.clicked.connect(self.run_selected_tool)
            self.dialog.preview_button.clicked.connect(self.preview_selected_tool)
            self.dialog.pick_button.clicked.connect(self._start_pick_mode)
            self.dialog.clear_preview_button.clicked.connect(self.clear_preview)
            self.dialog.clear_button.clicked.connect(self.clear_helpers)
            self.dialog.finished.connect(self._on_dialog_closed)

            self.dialog.tool_combo.currentIndexChanged.connect(self._on_preview_inputs_changed)
            self.dialog.extension_spin.valueChanged.connect(self._on_preview_inputs_changed)
            self.dialog.extend_segments_checkbox.toggled.connect(self._on_preview_inputs_changed)
            self.dialog.guide_spin.valueChanged.connect(self._on_preview_inputs_changed)
            self.dialog.offset_spin.valueChanged.connect(self._on_preview_inputs_changed)
            self.dialog.circle_segments_spin.valueChanged.connect(self._on_preview_inputs_changed)
            self.dialog.auto_preview_checkbox.toggled.connect(self._on_preview_inputs_changed)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
        self._refresh_preview_if_needed(silent=True)

    def run_selected_tool(self):
        layer, tool_id, geometries, error = self._build_current_geometries()
        if error:
            self._warn(error)
            return

        added = self.layer_manager.add_geometries(
            self.dialog.selected_tool_label() if self.dialog else self._tool_label(tool_id),
            geometries,
            layer.crs().authid(),
        )

        if added == 0:
            self._warn("No helper geometry could be added.")
            return

        self.clear_preview(silent=True)
        self.iface.mapCanvas().refresh()
        self.iface.messageBar().pushSuccess(
            "Drafting Helpers",
            f"Added {added} temporary helper geometries.",
        )

    def preview_selected_tool(self, silent=False):
        _layer, _tool_id, geometries, error = self._build_current_geometries()
        if error:
            self.preview_manager.clear()
            if not silent:
                self.iface.messageBar().pushWarning("Drafting Helpers", error)
            return False

        self.preview_manager.show_geometries(geometries)
        self.iface.mapCanvas().refresh()
        if not silent:
            self.iface.messageBar().pushInfo(
                "Drafting Helpers",
                f"Previewing {len(geometries)} helper geometries.",
            )
        return True

    def clear_preview(self, silent=False):
        self.preview_manager.clear()
        self.iface.mapCanvas().refresh()
        if not silent:
            self.iface.messageBar().pushInfo("Drafting Helpers", "Preview cleared.")

    def clear_helpers(self):
        self.clear_preview(silent=True)
        removed = self.layer_manager.clear()
        self.iface.mapCanvas().refresh()
        self.iface.messageBar().pushInfo(
            "Drafting Helpers",
            f"Cleared {removed} temporary helper layer(s).",
        )

    def _start_pick_mode(self):
        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            self._warn("Active layer must be a vector layer before picking from map.")
            return

        if self._feature_picker_tool is None:
            self._feature_picker_tool = FeaturePickerMapTool(
                self.iface,
                self._on_feature_picked,
                self._stop_pick_mode,
            )

        canvas = self.iface.mapCanvas()
        if canvas.mapTool() != self._feature_picker_tool:
            self._previous_map_tool = canvas.mapTool()
            canvas.setMapTool(self._feature_picker_tool)

        self.iface.messageBar().pushInfo(
            "Drafting Helpers",
            "Pick mode active: left click pick, Shift+left add, right click finish.",
        )

    def _stop_pick_mode(self, silent=False):
        canvas = self.iface.mapCanvas()
        if self._feature_picker_tool and canvas.mapTool() == self._feature_picker_tool:
            if self._previous_map_tool is not None:
                canvas.setMapTool(self._previous_map_tool)
        self._previous_map_tool = None
        if not silent:
            self.iface.messageBar().pushInfo("Drafting Helpers", "Pick mode finished.")

    def _on_feature_picked(self, _feature_id, error):
        if error:
            self.iface.messageBar().pushWarning("Drafting Helpers", error)
            return

        layer = self.iface.activeLayer()
        selected_count = layer.selectedFeatureCount() if isinstance(layer, QgsVectorLayer) else 0
        self.iface.messageBar().pushInfo(
            "Drafting Helpers",
            f"Selected features: {selected_count}",
        )
        self._refresh_preview_if_needed(silent=True)

    def _on_dialog_closed(self, *_args):
        self._stop_pick_mode(silent=True)
        self.clear_preview(silent=True)

    def _on_current_layer_changed(self, layer):
        self._connect_layer_signals(layer)
        self._refresh_preview_if_needed(silent=True)

    def _connect_layer_signals(self, layer):
        self._disconnect_layer_signals()
        if isinstance(layer, QgsVectorLayer):
            try:
                layer.selectionChanged.connect(self._on_selection_changed)
                self._selection_layer = layer
            except Exception:
                self._selection_layer = None

    def _disconnect_layer_signals(self):
        if self._selection_layer is None:
            return
        try:
            self._selection_layer.selectionChanged.disconnect(self._on_selection_changed)
        except (RuntimeError, TypeError):
            pass
        self._selection_layer = None

    def _on_selection_changed(self, *_args):
        self._refresh_preview_if_needed(silent=True)

    def _on_preview_inputs_changed(self, *_args):
        self._refresh_preview_if_needed(silent=True)

    def _refresh_preview_if_needed(self, silent=True):
        if self.dialog is None or not self.dialog.isVisible():
            return
        if self.dialog.auto_preview_enabled():
            self.preview_selected_tool(silent=silent)

    def _build_current_geometries(self):
        if self.dialog is None:
            return None, None, [], "Dialog is not initialized."

        layer = self.iface.activeLayer()
        if not isinstance(layer, QgsVectorLayer):
            return None, None, [], "Active layer must be a vector layer with selected features."

        selected = list(layer.selectedFeatures())
        if not selected:
            return None, None, [], "Select at least one feature (or use Pick on Map)."

        tool_id = self.dialog.selected_tool_id()
        handler = self._tool_handlers.get(tool_id)
        if handler is None:
            return None, None, [], "Unknown helper tool."

        params = self.dialog.parameters()
        geometries, error = handler(selected, params)
        if error:
            return None, None, [], error
        if not geometries:
            return None, None, [], "No helper geometry was generated for the current selection."
        return layer, tool_id, geometries, None

    def _register_action(self, action):
        self.iface.addPluginToMenu(self.menu, action)
        self.toolbar.addAction(action)
        self.actions.append(action)

    def _warn(self, message):
        QMessageBox.warning(self.iface.mainWindow(), "Drafting Helpers", message)

    def _tool_label(self, tool_id):
        spec = next((x for x in self.TOOL_SPECS if x.tool_id == tool_id), None)
        if spec is None:
            return tool_id
        if self.dialog and self.dialog.current_language() == "pl":
            return spec.label_pl
        return spec.label_en

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_all_vertices_to_points(self, selected, _params):
        geoms = []
        for feature in selected:
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            for v in geom.vertices():
                geoms.append(QgsGeometry.fromPointXY(QgsPointXY(v.x(), v.y())))

        if not geoms:
            return [], "No vertices found in selection."
        return geoms, None

    def _tool_line_endpoints(self, selected, _params):
        parts = self._selected_line_parts(selected)
        if not parts:
            return [], "Select line features for this tool."

        geoms = []
        for part in parts:
            geoms.append(QgsGeometry.fromPointXY(part[0]))
            geoms.append(QgsGeometry.fromPointXY(part[-1]))
        return geoms, None

    def _tool_line_midpoints(self, selected, _params):
        parts = self._selected_line_parts(selected)
        if not parts:
            return [], "Select line features for this tool."

        geoms = []
        for part in parts:
            total = self._polyline_length(part)
            if total <= 0:
                continue
            mid, _, _ = self._point_and_segment_at_distance(part, total / 2.0)
            geoms.append(QgsGeometry.fromPointXY(mid))

        if not geoms:
            return [], "Could not compute line midpoints from selected features."
        return geoms, None

    def _tool_segment_midpoints(self, selected, _params):
        geoms = []

        line_parts = self._selected_line_parts(selected)
        for part in line_parts:
            for p1, p2 in self._segments(part):
                geoms.append(QgsGeometry.fromPointXY(self._midpoint(p1, p2)))

        polygon_rings = self._selected_polygon_rings(selected)
        for ring in polygon_rings:
            for p1, p2 in self._segments(self._closed_ring(ring)):
                geoms.append(QgsGeometry.fromPointXY(self._midpoint(p1, p2)))

        if not geoms:
            return [], "Select lines or polygons for this tool."
        return geoms, None

    def _tool_extend_line_both(self, selected, params):
        return self._extend_lines(
            selected,
            params["extension"],
            params["extension"],
            params.get("extend_each_segment_multiline", False),
        )

    def _tool_extend_line_start(self, selected, params):
        return self._extend_lines(
            selected,
            params["extension"],
            0.0,
            params.get("extend_each_segment_multiline", False),
        )

    def _tool_extend_line_end(self, selected, params):
        return self._extend_lines(
            selected,
            0.0,
            params["extension"],
            params.get("extend_each_segment_multiline", False),
        )

    def _tool_perpendicular_at_midpoint(self, selected, params):
        return self._perpendicular_helpers(selected, "mid", params["guide"])

    def _tool_perpendicular_at_start(self, selected, params):
        return self._perpendicular_helpers(selected, "start", params["guide"])

    def _tool_perpendicular_at_end(self, selected, params):
        return self._perpendicular_helpers(selected, "end", params["guide"])

    def _tool_parallel_offset_left(self, selected, params):
        return self._parallel_offsets(selected, abs(params["offset"]))

    def _tool_parallel_offset_right(self, selected, params):
        return self._parallel_offsets(selected, -abs(params["offset"]))

    def _tool_line_intersections(self, selected, _params):
        line_geoms = self._selected_line_geometries(selected)
        if len(line_geoms) < 2:
            return [], "Select at least two line features for intersection helpers."

        geoms = []
        seen = set()

        for g1, g2 in combinations(line_geoms, 2):
            inter = g1.intersection(g2)
            if inter is None or inter.isEmpty():
                continue

            points = self._geometry_points(inter)
            for pt in points:
                key = (round(pt.x(), 6), round(pt.y(), 6))
                if key in seen:
                    continue
                seen.add(key)
                geoms.append(QgsGeometry.fromPointXY(pt))

        if not geoms:
            return [], "No intersections found between selected lines."
        return geoms, None

    def _tool_shortest_connector_two_lines(self, selected, _params):
        line_geoms = self._selected_line_geometries(selected)
        if len(line_geoms) < 2:
            return [], "Select at least two line features."

        g1 = line_geoms[0]
        g2 = line_geoms[1]

        connector = None
        try:
            connector = g1.shortestLine(g2)
        except Exception:
            connector = None

        if connector is None or connector.isEmpty():
            p1g = g1.nearestPoint(g2)
            p2g = g2.nearestPoint(g1)
            p1 = self._geometry_first_point(p1g)
            p2 = self._geometry_first_point(p2g)
            if p1 is None or p2 is None:
                return [], "Could not compute shortest connector between the first two lines."
            connector = QgsGeometry.fromPolylineXY([p1, p2])

        return [connector], None

    def _tool_project_vertices_to_baseline(self, selected, _params):
        line_geoms = self._selected_line_geometries(selected)
        if len(line_geoms) < 2:
            return [], "Select at least two line features (first one is baseline)."

        baseline = line_geoms[0]
        geoms = []

        for geom in line_geoms[1:]:
            for v in geom.vertices():
                src = QgsPointXY(v.x(), v.y())
                nearest_geom = baseline.nearestPoint(QgsGeometry.fromPointXY(src))
                nearest = self._geometry_first_point(nearest_geom)
                if nearest is None:
                    continue

                geoms.append(QgsGeometry.fromPointXY(nearest))
                if self._point_distance(src, nearest) > 0.0:
                    geoms.append(QgsGeometry.fromPolylineXY([src, nearest]))

        if not geoms:
            return [], "Could not project vertices to baseline."
        return geoms, None

    def _tool_polygon_centroids(self, selected, _params):
        polygons = self._selected_polygon_geometries(selected)
        if not polygons:
            return [], "Select polygon features for centroid helpers."

        geoms = []
        for geom in polygons:
            c = geom.centroid()
            if c and not c.isEmpty():
                geoms.append(c)

        if not geoms:
            return [], "Could not compute centroids from selection."
        return geoms, None

    def _tool_polygon_bbox_centers(self, selected, _params):
        polygons = self._selected_polygon_geometries(selected)
        if not polygons:
            return [], "Select polygon features for BBOX center helpers."

        geoms = []
        for geom in polygons:
            bbox = geom.boundingBox()
            center = QgsPointXY(
                (bbox.xMinimum() + bbox.xMaximum()) / 2.0,
                (bbox.yMinimum() + bbox.yMaximum()) / 2.0,
            )
            geoms.append(QgsGeometry.fromPointXY(center))

        return geoms, None

    def _tool_polygon_bbox_crosshairs(self, selected, _params):
        polygons = self._selected_polygon_geometries(selected)
        if not polygons:
            return [], "Select polygon features for crosshair helpers."

        geoms = []
        for geom in polygons:
            bbox = geom.boundingBox()
            cx = (bbox.xMinimum() + bbox.xMaximum()) / 2.0
            cy = (bbox.yMinimum() + bbox.yMaximum()) / 2.0

            h_line = QgsGeometry.fromPolylineXY(
                [QgsPointXY(bbox.xMinimum(), cy), QgsPointXY(bbox.xMaximum(), cy)]
            )
            v_line = QgsGeometry.fromPolylineXY(
                [QgsPointXY(cx, bbox.yMinimum()), QgsPointXY(cx, bbox.yMaximum())]
            )
            geoms.extend([h_line, v_line])

        return geoms, None

    def _tool_polygon_bbox_diagonals(self, selected, _params):
        polygons = self._selected_polygon_geometries(selected)
        if not polygons:
            return [], "Select polygon features for diagonal helpers."

        geoms = []
        for geom in polygons:
            bbox = geom.boundingBox()
            d1 = QgsGeometry.fromPolylineXY(
                [
                    QgsPointXY(bbox.xMinimum(), bbox.yMinimum()),
                    QgsPointXY(bbox.xMaximum(), bbox.yMaximum()),
                ]
            )
            d2 = QgsGeometry.fromPolylineXY(
                [
                    QgsPointXY(bbox.xMinimum(), bbox.yMaximum()),
                    QgsPointXY(bbox.xMaximum(), bbox.yMinimum()),
                ]
            )
            geoms.extend([d1, d2])

        return geoms, None

    def _tool_polygon_edge_midpoints(self, selected, _params):
        rings = self._selected_polygon_rings(selected)
        if not rings:
            return [], "Select polygon features for edge midpoint helpers."

        geoms = []
        for ring in rings:
            for p1, p2 in self._segments(self._closed_ring(ring)):
                geoms.append(QgsGeometry.fromPointXY(self._midpoint(p1, p2)))

        return geoms, None

    def _tool_midpoint_two_points(self, selected, _params):
        points = self._selected_points(selected)
        if len(points) < 2:
            return [], "Select at least two point features."

        mid = self._midpoint(points[0], points[1])
        return [QgsGeometry.fromPointXY(mid)], None

    def _tool_perpendicular_bisector_two_points(self, selected, params):
        points = self._selected_points(selected)
        if len(points) < 2:
            return [], "Select at least two point features."

        p1 = points[0]
        p2 = points[1]
        direction = self._unit_vector(p2.x() - p1.x(), p2.y() - p1.y())
        if direction is None:
            return [], "Two distinct points are required for a bisector."

        perp = (-direction[1], direction[0])
        center = self._midpoint(p1, p2)
        guide = self._line_from_center(center, perp, params["guide"])
        return [guide], None

    def _tool_extended_baseline_two_points(self, selected, params):
        points = self._selected_points(selected)
        if len(points) < 2:
            return [], "Select at least two point features."

        p1 = points[0]
        p2 = points[1]
        direction = self._unit_vector(p2.x() - p1.x(), p2.y() - p1.y())
        if direction is None:
            return [], "Two distinct points are required to build a baseline."

        ext = params["extension"]
        start = QgsPointXY(p1.x() - direction[0] * ext, p1.y() - direction[1] * ext)
        end = QgsPointXY(p2.x() + direction[0] * ext, p2.y() + direction[1] * ext)
        return [QgsGeometry.fromPolylineXY([start, end])], None

    def _tool_angle_bisector_three_points(self, selected, params):
        points = self._selected_points(selected)
        if len(points) < 3:
            return [], "Select at least three point features."

        a = points[0]
        b = points[1]
        c = points[2]

        u = self._unit_vector(a.x() - b.x(), a.y() - b.y())
        v = self._unit_vector(c.x() - b.x(), c.y() - b.y())
        if u is None or v is None:
            return [], "Angle bisector needs three distinct points."

        bis = self._unit_vector(u[0] + v[0], u[1] + v[1])
        if bis is None:
            return [], "Points form a straight angle; no unique bisector was found."

        tip = QgsPointXY(
            b.x() + bis[0] * params["guide"],
            b.y() + bis[1] * params["guide"],
        )
        return [QgsGeometry.fromPolylineXY([b, tip])], None

    def _tool_circle_center_three_points(self, selected, _params):
        points = self._selected_points(selected)
        if len(points) < 3:
            return [], "Select at least three point features."

        center, _radius = self._circumcenter(points[0], points[1], points[2])
        if center is None:
            return [], "Points are collinear; circle center cannot be computed."

        return [QgsGeometry.fromPointXY(center)], None

    def _tool_circle_three_points(self, selected, params):
        points = self._selected_points(selected)
        if len(points) < 3:
            return [], "Select at least three point features."

        center, radius = self._circumcenter(points[0], points[1], points[2])
        if center is None or radius <= 0.0:
            return [], "Points are collinear; circle cannot be computed."

        circle = self._circle_geometry(center, radius, params["circle_segments"])
        return [circle], None

    def _tool_circle_diameter_two_points(self, selected, params):
        points = self._selected_points(selected)
        if len(points) < 2:
            return [], "Select at least two point features."

        p1 = points[0]
        p2 = points[1]
        center = self._midpoint(p1, p2)
        radius = self._point_distance(p1, p2) / 2.0
        if radius <= 0.0:
            return [], "Two distinct points are required."

        circle = self._circle_geometry(center, radius, params["circle_segments"])
        return [circle], None

    # ------------------------------------------------------------------
    # Composite helpers
    # ------------------------------------------------------------------

    def _extend_lines(self, selected, start_extension, end_extension, per_segment=False):
        parts = self._selected_line_parts(selected)
        if not parts:
            return [], "Select line features for extension helpers."

        geoms = []
        for part in parts:
            if per_segment:
                for p1, p2 in self._segments(part):
                    if self._point_distance(p1, p2) <= 0.0:
                        continue
                    extended_seg = self._extend_polyline([p1, p2], start_extension, end_extension)
                    if len(extended_seg) >= 2:
                        geoms.append(QgsGeometry.fromPolylineXY(extended_seg))
            else:
                extended = self._extend_polyline(part, start_extension, end_extension)
                if len(extended) >= 2:
                    geoms.append(QgsGeometry.fromPolylineXY(extended))

        if not geoms:
            return [], "No valid lines were found to extend."
        return geoms, None

    def _perpendicular_helpers(self, selected, location, guide_length):
        parts = self._selected_line_parts(selected)
        if not parts:
            return [], "Select line features for perpendicular helpers."

        geoms = []
        for part in parts:
            result = self._line_anchor_and_direction(part, location)
            if result is None:
                continue
            anchor, direction = result
            perp = (-direction[1], direction[0])
            geoms.append(self._line_from_center(anchor, perp, guide_length))

        if not geoms:
            return [], "Could not derive perpendicular helpers from selected lines."
        return geoms, None

    def _parallel_offsets(self, selected, distance):
        line_geoms = self._selected_line_geometries(selected)
        if not line_geoms:
            return [], "Select line features for offset helpers."

        geoms = []
        for geom in line_geoms:
            offset = None
            try:
                offset = geom.offsetCurve(distance)
            except Exception:
                offset = None

            if offset is None or offset.isEmpty():
                try:
                    offset = geom.offsetCurve(distance, 8)
                except Exception:
                    offset = None

            if offset is not None and not offset.isEmpty():
                geoms.append(offset)

        if not geoms:
            return [], "Could not create offset curves from selected lines."
        return geoms, None

    # ------------------------------------------------------------------
    # Geometry extraction
    # ------------------------------------------------------------------

    def _selected_points(self, selected):
        points = []
        for feature in selected:
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if geom.type() != QgsWkbTypes.PointGeometry:
                continue

            if geom.isMultipart():
                for p in geom.asMultiPoint():
                    points.append(QgsPointXY(p.x(), p.y()))
            else:
                p = geom.asPoint()
                points.append(QgsPointXY(p.x(), p.y()))
        return points

    def _selected_line_geometries(self, selected):
        geoms = []
        for feature in selected:
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if geom.type() == QgsWkbTypes.LineGeometry:
                geoms.append(geom)
        return geoms

    def _selected_line_parts(self, selected):
        parts = []
        for feature in selected:
            parts.extend(self._line_parts_from_geometry(feature.geometry()))
        return parts

    def _selected_polygon_geometries(self, selected):
        geoms = []
        for feature in selected:
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            if geom.type() == QgsWkbTypes.PolygonGeometry:
                geoms.append(geom)
        return geoms

    def _selected_polygon_rings(self, selected):
        rings = []
        for geom in self._selected_polygon_geometries(selected):
            if geom.isMultipart():
                for polygon in geom.asMultiPolygon():
                    for ring in polygon:
                        ring_pts = [QgsPointXY(p.x(), p.y()) for p in ring]
                        if len(ring_pts) >= 3:
                            rings.append(ring_pts)
            else:
                for ring in geom.asPolygon():
                    ring_pts = [QgsPointXY(p.x(), p.y()) for p in ring]
                    if len(ring_pts) >= 3:
                        rings.append(ring_pts)
        return rings

    def _line_parts_from_geometry(self, geom):
        if geom is None or geom.isEmpty():
            return []
        if geom.type() != QgsWkbTypes.LineGeometry:
            return []

        parts = []
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
            for line in lines:
                pts = [QgsPointXY(p.x(), p.y()) for p in line]
                if len(pts) >= 2:
                    parts.append(pts)
        else:
            line = geom.asPolyline()
            pts = [QgsPointXY(p.x(), p.y()) for p in line]
            if len(pts) >= 2:
                parts.append(pts)

        return parts

    def _geometry_points(self, geom):
        if geom is None or geom.isEmpty():
            return []

        gtype = QgsWkbTypes.geometryType(geom.wkbType())
        if gtype == QgsWkbTypes.PointGeometry:
            if geom.isMultipart():
                return [QgsPointXY(p.x(), p.y()) for p in geom.asMultiPoint()]
            p = geom.asPoint()
            return [QgsPointXY(p.x(), p.y())]

        return [QgsPointXY(v.x(), v.y()) for v in geom.vertices()]

    def _geometry_first_point(self, geom):
        points = self._geometry_points(geom)
        return points[0] if points else None

    # ------------------------------------------------------------------
    # Numeric helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _point_distance(p1, p2):
        return math.hypot(p2.x() - p1.x(), p2.y() - p1.y())

    @staticmethod
    def _midpoint(p1, p2):
        return QgsPointXY((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)

    @staticmethod
    def _unit_vector(dx, dy):
        length = math.hypot(dx, dy)
        if length == 0.0:
            return None
        return (dx / length, dy / length)

    @staticmethod
    def _segments(points):
        for idx in range(len(points) - 1):
            yield points[idx], points[idx + 1]

    @staticmethod
    def _closed_ring(points):
        if not points:
            return points
        first = points[0]
        last = points[-1]
        if first.x() == last.x() and first.y() == last.y():
            return points
        return points + [first]

    def _polyline_length(self, points):
        total = 0.0
        for p1, p2 in self._segments(points):
            total += self._point_distance(p1, p2)
        return total

    def _point_and_segment_at_distance(self, points, target_dist):
        if len(points) < 2:
            return points[0], points[0], points[0]

        if target_dist <= 0.0:
            return points[0], points[0], points[1]

        total = self._polyline_length(points)
        if target_dist >= total:
            return points[-1], points[-2], points[-1]

        walked = 0.0
        for p1, p2 in self._segments(points):
            seg_len = self._point_distance(p1, p2)
            if seg_len <= 0.0:
                continue

            if walked + seg_len >= target_dist:
                ratio = (target_dist - walked) / seg_len
                x = p1.x() + (p2.x() - p1.x()) * ratio
                y = p1.y() + (p2.y() - p1.y()) * ratio
                return QgsPointXY(x, y), p1, p2
            walked += seg_len

        return points[-1], points[-2], points[-1]

    def _line_anchor_and_direction(self, points, location):
        if len(points) < 2:
            return None

        if location == "start":
            anchor = points[0]
            seg_p1 = points[0]
            seg_p2 = points[1]
        elif location == "end":
            anchor = points[-1]
            seg_p1 = points[-2]
            seg_p2 = points[-1]
        else:
            total = self._polyline_length(points)
            if total <= 0.0:
                return None
            anchor, seg_p1, seg_p2 = self._point_and_segment_at_distance(points, total / 2.0)

        direction = self._unit_vector(seg_p2.x() - seg_p1.x(), seg_p2.y() - seg_p1.y())
        if direction is None:
            return None

        return anchor, direction

    def _extend_polyline(self, points, start_extension, end_extension):
        if len(points) < 2:
            return points

        start_vec = self._unit_vector(
            points[0].x() - points[1].x(),
            points[0].y() - points[1].y(),
        )
        end_vec = self._unit_vector(
            points[-1].x() - points[-2].x(),
            points[-1].y() - points[-2].y(),
        )

        if start_vec is None or end_vec is None:
            return points

        start = QgsPointXY(
            points[0].x() + start_vec[0] * start_extension,
            points[0].y() + start_vec[1] * start_extension,
        )
        end = QgsPointXY(
            points[-1].x() + end_vec[0] * end_extension,
            points[-1].y() + end_vec[1] * end_extension,
        )

        if len(points) == 2:
            return [start, end]

        return [start] + points[1:-1] + [end]

    @staticmethod
    def _line_from_center(center, direction, length):
        half = length / 2.0
        p1 = QgsPointXY(center.x() - direction[0] * half, center.y() - direction[1] * half)
        p2 = QgsPointXY(center.x() + direction[0] * half, center.y() + direction[1] * half)
        return QgsGeometry.fromPolylineXY([p1, p2])

    def _circumcenter(self, a, b, c):
        x1, y1 = a.x(), a.y()
        x2, y2 = b.x(), b.y()
        x3, y3 = c.x(), c.y()

        d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        if abs(d) < 1e-12:
            return None, 0.0

        ux = (
            (x1 * x1 + y1 * y1) * (y2 - y3)
            + (x2 * x2 + y2 * y2) * (y3 - y1)
            + (x3 * x3 + y3 * y3) * (y1 - y2)
        ) / d

        uy = (
            (x1 * x1 + y1 * y1) * (x3 - x2)
            + (x2 * x2 + y2 * y2) * (x1 - x3)
            + (x3 * x3 + y3 * y3) * (x2 - x1)
        ) / d

        center = QgsPointXY(ux, uy)
        radius = self._point_distance(center, a)
        return center, radius

    @staticmethod
    def _circle_geometry(center, radius, segments):
        points = []
        for i in range(segments):
            angle = (2.0 * math.pi * i) / segments
            points.append(
                QgsPointXY(
                    center.x() + math.cos(angle) * radius,
                    center.y() + math.sin(angle) * radius,
                )
            )

        points.append(points[0])
        return QgsGeometry.fromPolygonXY([points])
