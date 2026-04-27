"""
Font classification database for identifying OS-specific and cross-platform fonts.
"""

MACOS_ONLY_FONTS = {
    "SF Pro", "SF Pro Display", "SF Pro Text", "SF Pro Rounded",
    "SF Compact", "SF Compact Display", "SF Compact Text", "SF Compact Rounded",
    "SF Mono", "San Francisco", "San Francisco Display", "San Francisco Text",
    "Lucida Grande",
    "Helvetica Neue",
    "Apple SD Gothic Neo", "Apple Symbols", "Apple Color Emoji", "Apple Chancery",
    "Avenir", "Avenir Next", "Avenir Next Condensed",
    "Phosphate", "Chalkduster", "Marker Felt", "Noteworthy",
    "Kohinoor", "Kefa", "Galvji",
    "Geneva", "Monaco",
    "Menlo",
    "Osaka",
    "Hiragino Sans", "Hiragino Kaku Gothic Pro", "Hiragino Mincho Pro",
    "PingFang SC", "PingFang TC", "PingFang HK",
    ".AppleSystemUIFont", ".SF NS", ".SF NS Text", ".SF NS Display",
}

WINDOWS_ONLY_FONTS = {
    "Segoe UI", "Segoe UI Variable", "Segoe UI Emoji", "Segoe UI Symbol",
    "Segoe UI Historic", "Segoe Print", "Segoe Script",
    "Calibri", "Cambria", "Candara", "Consolas", "Constantia", "Corbel",
    "Bahnschrift",
    "Yu Gothic", "Yu Gothic UI", "Yu Mincho",
    "MS Gothic", "MS PGothic", "MS UI Gothic",
    "MS Mincho", "MS PMincho",
    "Meiryo", "Meiryo UI",
    "Sitka Text", "Sitka Small", "Sitka Heading", "Sitka Display",
    "Sitka Banner", "Sitka Subheading",
    "Ebrima", "Gadugi", "Leelawadee UI", "Nirmala UI", "Javanese Text",
    "Microsoft Sans Serif", "Microsoft YaHei", "Microsoft JhengHei",
    "Malgun Gothic",
    "Ink Free",
}

LINUX_SPECIFIC_FONTS = {
    "Ubuntu", "Ubuntu Mono", "Ubuntu Condensed", "Ubuntu Light",
    "Cantarell",
    "Droid Sans", "Droid Serif", "Droid Sans Mono",
}

CROSS_PLATFORM_SAFE_FONTS = [
    "Arial",
    "Helvetica",
    "Times New Roman",
    "Courier New",
    "Verdana",
    "Georgia",
    "Tahoma",
    "Trebuchet MS",
    "Liberation Sans",
    "Liberation Serif",
    "Liberation Mono",
    "Noto Sans",
    "Noto Serif",
    "Noto Mono",
    "Open Sans",
    "Roboto",
    "DejaVu Sans",
    "DejaVu Serif",
    "DejaVu Sans Mono",
]

ALL_OS_SPECIFIC_FONTS = MACOS_ONLY_FONTS | WINDOWS_ONLY_FONTS | LINUX_SPECIFIC_FONTS


def classify_font(family):
    """Classify a font as OS-specific or cross-platform.

    Returns one of: 'macos', 'windows', 'linux', 'safe', 'unknown'
    """
    if family in MACOS_ONLY_FONTS:
        return "macos"
    if family in WINDOWS_ONLY_FONTS:
        return "windows"
    if family in LINUX_SPECIFIC_FONTS:
        return "linux"
    if family in CROSS_PLATFORM_SAFE_FONTS:
        return "safe"
    return "unknown"


def get_available_safe_fonts():
    """Return cross-platform safe fonts that are available on the current system."""
    try:
        from qgis.core import QgsFontUtils
        return [f for f in CROSS_PLATFORM_SAFE_FONTS if QgsFontUtils.fontFamilyOnSystem(f)]
    except ImportError:
        return list(CROSS_PLATFORM_SAFE_FONTS)


def is_os_specific(family):
    """Check if a font family is OS-specific."""
    return family in ALL_OS_SPECIFIC_FONTS


def is_font_available(family):
    """Check if a font family is available on the current system."""
    try:
        from qgis.core import QgsFontUtils
        return QgsFontUtils.fontFamilyOnSystem(family)
    except ImportError:
        from qgis.PyQt.QtGui import QFontDatabase
        return family in QFontDatabase().families()
