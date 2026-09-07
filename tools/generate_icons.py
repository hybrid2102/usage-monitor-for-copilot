"""Generate the Codex monitor application and notification icons."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]


def render(*, active: bool) -> Image.Image:
    """Render a terminal-prompt mark with the monitor's two usage bars."""
    size = 256
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 255, 255), radius=48, fill=(28, 28, 30, 255))

    # A geometric prompt stays crisp when Windows downsizes it to tray scale.
    draw.line(((76, 48), (142, 105), (76, 162)), fill=(255, 255, 255, 255), width=25, joint='curve')

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


def main() -> None:
    active = render(active=True)
    save_ico(active, ROOT / 'usage_monitor_for_codex.ico')
    save_ico(render(active=False), ROOT / 'usage_monitor_for_codex' / 'notification_logo.ico')
    active.save(ROOT / 'docs' / 'icon.png', format='PNG', optimize=True)


if __name__ == '__main__':
    main()
