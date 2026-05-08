import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "public");

const py = `
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

out = Path(r"${outDir}")
out.mkdir(parents=True, exist_ok=True)

BG = "#060818"
VIOLET_TOP = (170, 118, 255, 255)
VIOLET_BOTTOM = (121, 53, 237, 255)

def draw_icon(size, font_size, filename):
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        r = int(VIOLET_TOP[0] * (1 - t) + VIOLET_BOTTOM[0] * t)
        g = int(VIOLET_TOP[1] * (1 - t) + VIOLET_BOTTOM[1] * t)
        b = int(VIOLET_TOP[2] * (1 - t) + VIOLET_BOTTOM[2] * t)
        gdraw.line([(0, y), (size, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    text = "H"
    bbox = mdraw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2
    ty = (size - th) // 2 - int(size * 0.03)
    mdraw.text((tx, ty), text, fill=255, font=font)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    glow_pad = max(4, int(size * 0.03))
    g.rounded_rectangle(
        [glow_pad, glow_pad, size - glow_pad, size - glow_pad],
        radius=int(size * 0.22),
        outline=(121, 53, 237, 80),
        width=max(2, int(size * 0.01)),
    )
    img.alpha_composite(glow)
    img.paste(grad, (0, 0), mask)
    img.save(out / filename, format="PNG")

draw_icon(192, 120, "icon-192.png")
draw_icon(512, 320, "icon-512.png")
draw_icon(180, 108, "apple-touch-icon.png")
print("OK")
`;

const result = spawnSync("/root/hermes/venv/bin/python", ["-c", py], {
  cwd: root,
  encoding: "utf-8",
});

if (result.status !== 0) {
  console.error(result.stderr || "Icon generation failed.");
  process.exit(result.status || 1);
}

console.log(result.stdout.trim() || "OK");
