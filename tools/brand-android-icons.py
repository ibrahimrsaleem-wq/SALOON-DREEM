#!/usr/bin/env python3
"""Apply SALOON DREEM branding to the generated Capacitor Android launcher icons."""
from __future__ import annotations

import re
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "frontend" / "icons" / "icon-512.png"
RES = ROOT / "android" / "app" / "src" / "main" / "res"
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
BACKGROUND = "#101916"


def make_adaptive_foreground(source: Image.Image, target_size: int) -> Image.Image:
    """Extract the gold mark from the dark tile and center it in Android's safe zone."""
    image = source.convert("RGBA")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            # The original brand tile's dark green background is removed for adaptive icons.
            brightness = max(r, g, b)
            if brightness <= 66:
                pixels[x, y] = (r, g, b, 0)
            elif brightness < 118 and r < 100 and g < 110 and b < 100:
                alpha = round(a * (brightness - 66) / 52)
                pixels[x, y] = (r, g, b, alpha)

    alpha = image.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 12 else 0).getbbox()
    if bbox is None:
        raise RuntimeError("Could not isolate the logo mark for the Android adaptive icon.")
    mark = image.crop(bbox)
    mark.thumbnail((int(target_size * 0.68), int(target_size * 0.68)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    canvas.alpha_composite(mark, ((target_size - mark.width) // 2, (target_size - mark.height) // 2))
    return canvas


def update_color_resource(name: str, value: str) -> None:
    """Set an existing Android color resource or add a dedicated resource file."""
    color_tags = re.compile(rf'<color\s+name=["\']{re.escape(name)}["\'][^>]*>.*?</color>', re.S)
    for path in RES.glob("values*/**/*.xml"):
        text = path.read_text(encoding="utf-8")
        if color_tags.search(text):
            path.write_text(color_tags.sub(f'<color name="{name}">{value}</color>', text), encoding="utf-8")
            return
    target = RES / "values" / "saloondreem_brand_colors.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        text = target.read_text(encoding="utf-8")
        if color_tags.search(text):
            target.write_text(color_tags.sub(f'<color name="{name}">{value}</color>', text), encoding="utf-8")
        else:
            target.write_text(text.replace("</resources>", f'    <color name="{name}">{value}</color>\n</resources>'), encoding="utf-8")
    else:
        target.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
            f'    <color name="{name}">{value}</color>\n'
            '</resources>\n',
            encoding="utf-8",
        )


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Brand icon not found: {SOURCE}")
    if not RES.is_dir():
        raise FileNotFoundError(f"Capacitor Android resources not found: {RES}")

    with Image.open(SOURCE) as opened:
        brand = opened.convert("RGBA")
    if brand.size != (512, 512):
        raise ValueError(f"Expected a 512x512 brand icon, got {brand.size}")

    written: list[Path] = []
    for density, size in DENSITIES.items():
        directory = RES / density
        directory.mkdir(parents=True, exist_ok=True)
        for filename in ("ic_launcher.png", "ic_launcher_round.png"):
            path = directory / filename
            brand.resize((size, size), Image.Resampling.LANCZOS).save(path, format="PNG", optimize=True)
            written.append(path)

        foreground = directory / "ic_launcher_foreground.png"
        make_adaptive_foreground(brand, round(size * 2.25)).save(foreground, format="PNG", optimize=True)
        written.append(foreground)

    # Use the branded dark green tile as the adaptive icon background where the generated
    # Capacitor template references a color resource for it.
    adaptive_files = list((RES / "mipmap-anydpi-v26").glob("ic_launcher*.xml")) if (RES / "mipmap-anydpi-v26").exists() else []
    for xml in adaptive_files:
        xml_text = xml.read_text(encoding="utf-8")
        references = re.findall(r'@color/([A-Za-z0-9_]+)', xml_text)
        for name in references:
            if "launcher" in name.lower() or "background" in name.lower():
                update_color_resource(name, BACKGROUND)

    if len(written) < 15:
        raise RuntimeError(f"Expected launcher assets for five density levels; generated only {len(written)} files.")
    print(f"Applied SALOON DREEM Android branding to {len(written)} launcher images.")
    for path in written:
        with Image.open(path) as image:
            if image.format != "PNG" or image.width != image.height:
                raise RuntimeError(f"Invalid launcher image: {path}")
    print("Android launcher icon image validation passed.")


if __name__ == "__main__":
    main()
