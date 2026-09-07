"""Generate the Copilot monitor application and notification icons."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def render(*, active: bool) -> Image.Image:
    """Render an upward wing/chevron mark with the monitor's two usage bars.

    Distinct in both shape and orientation from the sibling monitors' marks -
    Claude's lettered "C" and Codex's sideways ">" prompt chevron - so the
    three tray/EXE icons stay tellable apart at a glance when pinned side by
    side. The upward chevron reads as a wing or aircraft nose (the "pilot" in
    Copilot) rather than a CLI prompt, since this monitor's data source is a
    local server process rather than a bare command-line session the way
    Codex's is.
    """
    size = 256
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 255, 255), radius=48, fill=(28, 28, 30, 255))

    # A geometric chevron stays crisp when Windows downsizes it to tray scale.
    draw.line(((66, 148), (128, 52), (190, 148)), fill=(255, 255, 255, 255), width=25, joint='curve')

    track = (91, 91, 96, 255)
    draw.rounded_rectangle((47, 183, 209, 204), radius=4, fill=track)
    draw.rounded_rectangle((47, 217, 209, 238), radius=4, fill=track)
    if active:
        draw.rounded_rectangle((47, 183, 164, 204), radius=4, fill=(255, 255, 255, 255))
        draw.rounded_rectangle((47, 217, 105, 238), radius=4, fill=(255, 255, 255, 255))
    return image


def save_ico(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format='ICO', sizes=SIZES, bitmap_format='bmp')


# Procedurally generated icon with a mark distinct from the other monitor twins
# (see render()'s docstring). It does not depict GitHub's actual Copilot mark -
# that is a trademarked asset, and adopting it here would be a separate,
# deliberate decision for a human to make, not something to generate.
def main() -> None:
    active = render(active=True)
    save_ico(active, ROOT / 'usage_monitor_for_copilot.ico')
    save_ico(render(active=False), ROOT / 'usage_monitor_for_copilot' / 'notification_logo.ico')
    active.save(ROOT / 'docs' / 'icon.png', format='PNG', optimize=True)


if __name__ == '__main__':
    main()
