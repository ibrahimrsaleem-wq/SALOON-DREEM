from __future__ import annotations

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "icons" / "icon-512.png"
OUTPUT = ROOT / "frontend" / "icons" / "saloondreem.ico"
SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Official SALOON DREEM logo PNG not found: {SOURCE}")
    with Image.open(SOURCE) as image:
        if image.size != (512, 512):
            raise ValueError(f"Expected a 512x512 brand logo, got {image.size}")
        image.convert("RGBA").save(OUTPUT, format="ICO", sizes=SIZES)

    if not OUTPUT.is_file() or OUTPUT.stat().st_size < 1000:
        raise RuntimeError("Windows ICO output is missing or unexpectedly small.")
    with Image.open(OUTPUT) as icon:
        available = icon.info.get("sizes", set())
        missing = [size for size in SIZES if size not in available]
        if missing:
            raise RuntimeError(f"ICO is missing expected resolutions: {missing}")
    print(f"Created branded Windows icon: {OUTPUT} ({OUTPUT.stat().st_size} bytes; sizes={SIZES})")


if __name__ == "__main__":
    main()
