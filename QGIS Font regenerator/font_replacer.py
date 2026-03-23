"""
Core replacement logic - applies font substitutions across a QGIS project.
"""

from typing import Dict, List
from dataclasses import dataclass, field

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsAnnotationLayer,
    QgsVectorLayerSimpleLabeling,
    QgsRuleBasedLabeling,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
    QgsLayoutItemMap,
    QgsLayoutTable,
    QgsTextAnnotation,
    QgsTextFormat,
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
class ReplaceResult:
    """Results of a replacement operation."""
    replacements_made: int = 0
    errors: List[str] = field(default_factory=list)


def _replace_font_in_format(text_format, old_family, new_family):
    """Replace font family in a QgsTextFormat. Returns modified format and whether changed."""
    if text_format.font().family() == old_family:
        font = text_format.font()
        font.setFamily(new_family)
        text_format.setFont(font)
        return text_format, True
    return text_format, False


def replace_fonts(replacements: Dict[str, str]) -> ReplaceResult:
    """Replace fonts across the entire project.

    Args:
        replacements: Dict mapping old font family -> new font family
    """
    result = ReplaceResult()
    project = QgsProject.instance()

    _replace_in_layers(project, replacements, result)
    _replace_in_layouts(project, replacements, result)
    _replace_in_annotations(project, replacements, result)

    return result


def _replace_in_layers(project, replacements, result):
    """Replace fonts in all vector layer labels and annotation layers."""
    for layer_id, layer in project.mapLayers().items():
        if isinstance(layer, QgsVectorLayer) and layer.labeling():
            _replace_in_layer_labeling(layer, replacements, result)

        if HAS_ANNOTATION_ITEMS and isinstance(layer, QgsAnnotationLayer):
            _replace_in_annotation_layer(layer, replacements, result)


def _replace_in_layer_labeling(layer, replacements, result):
    """Replace fonts in a vector layer's labeling."""
    labeling = layer.labeling()
    changed = False

    if isinstance(labeling, QgsVectorLayerSimpleLabeling):
        try:
            settings = labeling.settings()
            fmt = settings.format()
            old_family = fmt.font().family()
            if old_family in replacements:
                fmt, was_changed = _replace_font_in_format(fmt, old_family, replacements[old_family])
                if was_changed:
                    settings.setFormat(fmt)
                    labeling.setSettings(settings)
                    changed = True
                    result.replacements_made += 1
        except Exception as e:
            result.errors.append(f"Error replacing font in layer '{layer.name()}': {e}")

    elif isinstance(labeling, QgsRuleBasedLabeling):
        root = labeling.rootRule()
        if root:
            for rule in root.descendants():
                settings = rule.settings()
                if settings:
                    fmt = settings.format()
                    old_family = fmt.font().family()
                    if old_family in replacements:
                        fmt, was_changed = _replace_font_in_format(
                            fmt, old_family, replacements[old_family]
                        )
                        if was_changed:
                            settings.setFormat(fmt)
                            rule.setSettings(settings)
                            changed = True
                            result.replacements_made += 1

    if changed:
        layer.setLabeling(labeling.clone())
        layer.triggerRepaint()


def _replace_in_annotation_layer(layer, replacements, result):
    """Replace fonts in annotation layer items."""
    for item_id, item in layer.items().items():
        if isinstance(item, (QgsAnnotationPointTextItem, QgsAnnotationLineTextItem)):
            fmt = item.format()
            old_family = fmt.font().family()
            if old_family in replacements:
                fmt, was_changed = _replace_font_in_format(fmt, old_family, replacements[old_family])
                if was_changed:
                    item.setFormat(fmt)
                    result.replacements_made += 1


def _replace_in_layouts(project, replacements, result):
    """Replace fonts in all print layouts."""
    layout_manager = project.layoutManager()
    if not layout_manager:
        return

    for layout in layout_manager.printLayouts():
        layout_name = layout.name() or "(unnamed layout)"
        for item in layout.items():
            _replace_in_layout_item(item, layout_name, replacements, result)
        layout.refresh()


def _replace_in_layout_item(item, layout_name, replacements, result):
    """Replace fonts in a single layout item."""
    try:
        if isinstance(item, QgsLayoutItemLabel):
            _replace_in_layout_label(item, replacements, result)
        elif isinstance(item, QgsLayoutItemLegend):
            _replace_in_layout_legend(item, replacements, result)
        elif isinstance(item, QgsLayoutItemScaleBar):
            _replace_in_scalebar(item, replacements, result)
        elif isinstance(item, QgsLayoutTable):
            _replace_in_table(item, replacements, result)
        elif isinstance(item, QgsLayoutItemMap):
            _replace_in_map_grids(item, replacements, result)
    except Exception as e:
        result.errors.append(f"Error in layout '{layout_name}': {e}")


def _replace_in_layout_label(item, replacements, result):
    """Replace font in a layout label."""
    fmt = item.textFormat()
    old_family = fmt.font().family()
    if old_family in replacements:
        fmt, was_changed = _replace_font_in_format(fmt, old_family, replacements[old_family])
        if was_changed:
            item.setTextFormat(fmt)
            result.replacements_made += 1


def _replace_in_layout_legend(item, replacements, result):
    """Replace fonts in all legend components."""
    components = LEGEND_COMPONENTS if LEGEND_COMPONENTS else []
    for component in components:
        try:
            style = item.style(component)
            fmt = style.textFormat()
            old_family = fmt.font().family()
            if old_family in replacements:
                fmt, was_changed = _replace_font_in_format(
                    fmt, old_family, replacements[old_family]
                )
                if was_changed:
                    style.setTextFormat(fmt)
                    item.setStyle(component, style)
                    result.replacements_made += 1
        except Exception:
            pass


def _replace_in_scalebar(item, replacements, result):
    """Replace font in a scale bar."""
    fmt = item.textFormat()
    old_family = fmt.font().family()
    if old_family in replacements:
        fmt, was_changed = _replace_font_in_format(fmt, old_family, replacements[old_family])
        if was_changed:
            item.setTextFormat(fmt)
            result.replacements_made += 1


def _replace_in_table(item, replacements, result):
    """Replace fonts in table header and content."""
    for getter, setter in [
        (item.headerTextFormat, item.setHeaderTextFormat),
        (item.contentTextFormat, item.setContentTextFormat),
    ]:
        try:
            fmt = getter()
            old_family = fmt.font().family()
            if old_family in replacements:
                fmt, was_changed = _replace_font_in_format(
                    fmt, old_family, replacements[old_family]
                )
                if was_changed:
                    setter(fmt)
                    result.replacements_made += 1
        except Exception:
            pass


def _replace_in_map_grids(item, replacements, result):
    """Replace fonts in map grid annotations."""
    grids = item.grids()
    for i in range(grids.size()):
        grid = grids.grid(i)
        if grid:
            try:
                fmt = grid.annotationTextFormat()
                old_family = fmt.font().family()
                if old_family in replacements:
                    fmt, was_changed = _replace_font_in_format(
                        fmt, old_family, replacements[old_family]
                    )
                    if was_changed:
                        grid.setAnnotationTextFormat(fmt)
                        result.replacements_made += 1
            except Exception:
                pass


def _replace_in_annotations(project, replacements, result):
    """Replace fonts in legacy text annotations."""
    try:
        annotation_manager = project.annotationManager()
        for annotation in annotation_manager.annotations():
            if isinstance(annotation, QgsTextAnnotation):
                doc = annotation.document()
                if doc:
                    _replace_in_text_document(doc, replacements, result)
    except Exception as e:
        result.errors.append(f"Error replacing in legacy annotations: {e}")


def _replace_in_text_document(doc, replacements, result):
    """Replace fonts in a QTextDocument (legacy annotations)."""
    from qgis.PyQt.QtGui import QTextCursor, QTextCharFormat

    cursor = QTextCursor(doc)
    cursor.beginEditBlock()

    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                char_format = fragment.charFormat()
                family = char_format.font().family()
                if family in replacements:
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(
                        fragment.position() + fragment.length(),
                        QTextCursor.KeepAnchor
                    )
                    new_format = QTextCharFormat()
                    new_format.setFontFamily(replacements[family])
                    cursor.mergeCharFormat(new_format)
                    result.replacements_made += 1
            it += 1
        block = block.next()

    cursor.endEditBlock()
