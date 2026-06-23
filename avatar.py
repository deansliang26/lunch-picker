"""Shared avatar helpers — colored initials circles for each team member."""

COLORS: dict[str, str] = {
    "Dean":   "#3E7488",  # ocean
    "Evan":   "#D97757",  # clay
    "Parth":  "#7B5EA7",  # purple
    "Cooper": "#3F7355",  # green
    "Aaron":  "#A53F31",  # red
}

_DEFAULT = "#9C978C"


def color(name: str) -> str:
    return COLORS.get(name, _DEFAULT)


def html(name: str, size: int = 28, font_size: int | None = None) -> str:
    """Return an HTML string: a filled circle with the person's initial."""
    fs = font_size or max(10, size // 2)
    initials = name[:1].upper() if name else "?"
    bg = color(name)
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;border-radius:50%;background:{bg};'
        f'color:#fff;font-size:{fs}px;font-weight:700;flex-shrink:0;'
        f'font-family:\'Hanken Grotesk\',system-ui,sans-serif;line-height:1;">'
        f'{initials}</span>'
    )
