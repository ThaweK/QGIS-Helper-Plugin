"""
Core scanning logic - finds all font usages across a QGIS project.
"""

from dataclasses import dataclass, field
from typing import List, Dict

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsAnnotationLayer,
    QgsVectorLayerSimpleLabeling,
    QgsRuleBasedLabeling,
    QgsPalLayerSettings,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
    QgsLayoutItemMap,
    QgsLayoutTable,
    QgsTextAnnotation,
)

try:
    from qgis.core import QgsAnnotationPointTextItem, QgsAnnotationLineTextItem
    HAS_ANNOTATION_ITEMS = True
except ImportError:
    HAS_ANNOTATION_ITEMS = False

try:
    from qgis.core import Qgis
    LEGEND_COMPONENTS = [
        Qgis.LegendComponent.Title,
        Qgis.LegendComponent.Group,
        Qgis.LegendComponent.Subgroup,
        Qgis.LegendComponent.SymbolLabel,
    ]
except (ImportError, AttributeError):
    LEGEND_COMPONENTS = []


@dataclass
class FontUsage:
    """A single occurrence of a font in the project."""
    font_family: str
    source_type: str  # 'layer_label', 'rule_label', 'layout_label', 'layout_legend', etc.
    source_name: str  # layer name, layout name, etc.
    detail: str = ""  # rule description, component name, etc.

    @property
    def location_display(self):
        parts = [self.source_type, self.source_name]
        if self.detail:
            parts.append(self.detail)
        return " > ".join(parts)


@dataclass
class ScanResult:
    """Complete scan results."""
    usages: List[FontUsage] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def fonts_by_family(self) -> Dict[str, List[FontUsage]]:
        result = {}
        for usage in self.usages:
            result.setdefault(usage.font_family, []).append(usage)
        return result

    @property
    def unique_fonts(self):
        return set(u.font_family for u in self.usages)


def scan_project() -> ScanResult:
    """Scan the entire QGIS project for font usages."""
    result = ScanResult()
    project = QgsProject.instance()

    _scan_layers(project, result)
    _scan_layouts(project, result)
    _scan_annotations(project, result)

    return result


def _get_font_family(text_format):
    """Extract font family from a QgsTextFormat."""
    return text_format.font().family()


def _scan_layers(project, result):
    """Scan all vector layers for label fonts."""
    for layer_id, layer in project.mapLayers().items():
        if isinstance(layer, QgsVectorLayer) and layer.labeling():
            _scan_layer_labeling(layer, result)

        if HAS_ANNOTATION_ITEMS and isinstance(layer, QgsAnnotationLayer):
            _scan_annotation_layer(layer, result)


def _scan_layer_labeling(layer, result):
    """Scan a vector layer's labeling configuration."""
    labeling = layer.labeling()

    if isinstance(labeling, QgsVectorLayerSimpleLabeling):
        try:
            settings = labeling.settings()
            family = _get_font_family(settings.format())
            result.usages.append(FontUsage(
                font_family=family,
                source_type="Layer Label",
                source_name=layer.name(),
            ))
            _check_data_defined_font(settings, layer.name(), result)
        except Exception as e:
            result.warnings.append(f"Could not read labels for layer '{layer.name()}': {e}")

    elif isinstance(labeling, QgsRuleBasedLabeling):
        root = labeling.rootRule()
        if root:
            for rule in root.descendants():
                settings = rule.settings()
                if settings:
                    family = _get_font_family(settings.format())
                    desc = rule.description() or rule.filterExpression() or "(unnamed rule)"
                    result.usages.append(FontUsage(
                        font_family=family,
                        source_type="Rule-Based Label",
                        source_name=layer.name(),
                        detail=desc,
                    ))
                    _check_data_defined_font(settings, layer.name(), result)


def _check_data_defined_font(settings, layer_name, result):
    """Warn about data-defined font overrides that cannot be statically scanned."""
    try:
        prop = settings.dataDefinedProperties().property(QgsPalLayerSettings.Property.Family)
        if prop and prop.isActive():
            result.warnings.append(
                f"Layer '{layer_name}' has a data-defined font family override "
                f"(expression: {prop.expressionString() or 'field-based'}). "
                f"This cannot be replaced automatically."
            )
    except (AttributeError, TypeError):
        pass


def _scan_annotation_layer(layer, result):
    """Scan annotation layer items for fonts."""
    for item_id, item in layer.items().items():
        if isinstance(item, (QgsAnnotationPointTextItem, QgsAnnotationLineTextItem)):
            family = _get_font_family(item.format())
            result.usages.append(FontUsage(
                font_family=family,
                source_type="Annotation",
                source_name=layer.name(),
                detail=type(item).__name__,
            ))


def _scan_layouts(project, result):
    """Scan all print layouts for font usages."""
    layout_manager = project.layoutManager()
    if not layout_manager:
        return

    for layout in layout_manager.printLayouts():
        layout_name = layout.name() or "(unnamed layout)"
        for item in layout.items():
            _scan_layout_item(item, layout_name, result)


def _scan_layout_item(item, layout_name, result):
    """Scan a single layout item for fonts."""
    if isinstance(item, QgsLayoutItemLabel):
        _scan_layout_label(item, layout_name, result)
    elif isinstance(item, QgsLayoutItemLegend):
        _scan_layout_legend(item, layout_name, result)
    elif isinstance(item, QgsLayoutItemScaleBar):
        family = _get_font_family(item.textFormat())
        result.usages.append(FontUsage(
            font_family=family,
            source_type="Layout ScaleBar",
            source_name=layout_name,
        ))
    elif isinstance(item, QgsLayoutTable):
        _scan_layout_table(item, layout_name, result)
    elif isinstance(item, QgsLayoutItemMap):
        _scan_layout_map_grids(item, layout_name, result)


def _scan_layout_label(item, layout_name, result):
    """Scan a layout label for fonts."""
    try:
        family = _get_font_family(item.textFormat())
        mode = "HTML" if item.mode() == QgsLayoutItemLabel.ModeHtml else "Text"
        result.usages.append(FontUsage(
            font_family=family,
            source_type="Layout Label",
            source_name=layout_name,
            detail=f"({mode}) {item.id() or ''}".strip(),
        ))
        if mode == "HTML":
            result.warnings.append(
                f"Layout '{layout_name}' has an HTML label. Fonts in CSS/HTML "
                f"may not be fully replaced by this tool."
            )
    except Exception as e:
        result.warnings.append(f"Could not read label in layout '{layout_name}': {e}")


def _scan_layout_legend(item, layout_name, result):
    """Scan a layout legend for fonts in each component."""
    if not LEGEND_COMPONENTS:
        try:
            style = item.style(2)  # Title = 2 in older QGIS
            family = _get_font_family(style.textFormat())
            result.usages.append(FontUsage(
                font_family=family,
                source_type="Layout Legend",
                source_name=layout_name,
                detail="Title",
            ))
        except Exception:
            result.warnings.append(
                f"Could not read legend fonts in layout '{layout_name}' "
                f"(Qgis.LegendComponent not available)"
            )
        return

    component_names = {
        Qgis.LegendComponent.Title: "Title",
        Qgis.LegendComponent.Group: "Group",
        Qgis.LegendComponent.Subgroup: "Subgroup",
        Qgis.LegendComponent.SymbolLabel: "Symbol Label",
    }
    for component in LEGEND_COMPONENTS:
        try:
            style = item.style(component)
            family = _get_font_family(style.textFormat())
            result.usages.append(FontUsage(
                font_family=family,
                source_type="Layout Legend",
                source_name=layout_name,
                detail=component_names.get(component, str(component)),
            ))
        except Exception:
            pass


def _scan_layout_table(item, layout_name, result):
    """Scan a layout table for header and content fonts."""
    try:
        header_family = _get_font_family(item.headerTextFormat())
        result.usages.append(FontUsage(
            font_family=header_family,
            source_type="Layout Table",
            source_name=layout_name,
            detail="Header",
        ))
    except Exception:
        pass

    try:
        content_family = _get_font_family(item.contentTextFormat())
        result.usages.append(FontUsage(
            font_family=content_family,
            source_type="Layout Table",
            source_name=layout_name,
            detail="Content",
        ))
    except Exception:
        pass


def _scan_layout_map_grids(item, layout_name, result):
    """Scan map grid annotations for fonts."""
    grids = item.grids()
    for i in range(grids.size()):
        grid = grids.grid(i)
        if grid:
            try:
                family = _get_font_family(grid.annotationTextFormat())
                result.usages.append(FontUsage(
                    font_family=family,
                    source_type="Layout Map Grid",
                    source_name=layout_name,
                    detail=f"Grid {i}",
                ))
            except Exception:
                pass


def _scan_annotations(project, result):
    """Scan legacy text annotations."""
    try:
        annotation_manager = project.annotationManager()
        for annotation in annotation_manager.annotations():
            if isinstance(annotation, QgsTextAnnotation):
                doc = annotation.document()
                if doc:
                    _scan_text_document(doc, result)
    except Exception as e:
        result.warnings.append(f"Could not scan legacy annotations: {e}")


def _scan_text_document(doc, result):
    """Extract fonts from a QTextDocument (legacy annotations)."""
    block = doc.begin()
    seen_fonts = set()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                family = fragment.charFormat().font().family()
                if family and family not in seen_fonts:
                    seen_fonts.add(family)
                    result.usages.append(FontUsage(
                        font_family=family,
                        source_type="Text Annotation",
                        source_name="Legacy Annotation",
                    ))
            it += 1
        block = block.next()
