"""Generates the built-in virtual backgrounds (assets/backgrounds/*.jpg). Run once: python make_backgrounds.py"""
from pathlib import Path

import cv2
import numpy as np

W, H = 1920, 1080
OUT = Path(__file__).resolve().parent / "assets" / "backgrounds"
rng = np.random.default_rng(7)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
X, Y = xx / W, yy / H


def lerp(a, b, t):
    a, b = np.array(a, np.float32), np.array(b, np.float32)
    return a * (1 - t[..., None]) + b * t[..., None]


def vignette(img, k=0.35):
    d = np.sqrt((X - 0.5) ** 2 + (Y - 0.5) ** 2) / 0.7071
    return img * (1 - k * d[..., None] ** 2)


def glow(img, cx, cy, r, color, a=1.0):
    d = np.sqrt(((X - cx) * W / H) ** 2 + (Y - cy) ** 2)
    g = np.exp(-(d / r) ** 2)[..., None]
    return img + np.array(color, np.float32) * g * a


def grain(img, s=3.0):
    return img + rng.normal(0, s, img.shape[:2])[..., None]


def blur(img, sigma):
    return cv2.GaussianBlur(img, (0, 0), sigma)


def studio():
    img = lerp((70, 74, 80), (38, 41, 46), np.clip(Y * 0.9 + 0.1, 0, 1))
    img = glow(img, 0.5, 0.35, 0.55, (60, 60, 58), 0.9)
    img = vignette(img, 0.55)
    return grain(img, 2.5)


def sunset():
    img = lerp((255, 168, 92), (92, 54, 120), np.clip(Y ** 0.8, 0, 1))
    img = lerp((255, 214, 150), (0, 0, 0), np.zeros_like(Y)) * 0 + img
    img = glow(img, 0.72, 0.62, 0.18, (255, 210, 140), 1.0)
    hills = (Y > 0.78 + 0.05 * np.sin(X * 7 + 1.3) + 0.02 * np.sin(X * 23)).astype(np.float32)
    img = img * (1 - hills[..., None] * 0.75)
    return grain(blur(img, 2), 2)


def bokeh():
    img = lerp((14, 22, 48), (6, 10, 24), Y)
    layer = np.zeros_like(img)
    palette = [(255, 196, 120), (120, 180, 255), (255, 140, 180), (160, 255, 220)]
    for _ in range(70):
        cx, cy = rng.uniform(0, W), rng.uniform(0, H)
        r = rng.uniform(20, 95)
        c = np.array(palette[rng.integers(len(palette))], np.float32) * rng.uniform(0.25, 0.7)
        disk = np.zeros((H, W), np.float32)
        cv2.circle(disk, (int(cx), int(cy)), int(r), 1.0, -1, cv2.LINE_AA)
        layer += disk[..., None] * c
    img = img + blur(layer, 6)
    return grain(vignette(img, 0.4), 2)


def aurora():
    img = lerp((6, 12, 26), (10, 20, 34), Y)
    for k, (col, ph, amp, y0) in enumerate((((40, 255, 160), 0.0, 0.08, 0.35), ((30, 200, 255), 1.7, 0.06, 0.45),
                                            ((140, 90, 255), 3.1, 0.05, 0.28))):
        curve = y0 + amp * np.sin(X * 5 + ph) + 0.03 * np.sin(X * 13 + ph * 2)
        band = np.exp(-((Y - curve) / 0.06) ** 2) * (0.6 + 0.4 * np.sin(X * 31 + k) ** 2)
        img = img + band[..., None] * np.array(col, np.float32) * 0.7
    stars = (rng.random((H, W)) > 0.9993).astype(np.float32) * 200
    img = img + blur(stars, 0.8)[..., None]
    return grain(blur(img, 1.5), 2)


def ocean():
    sky = lerp((150, 205, 240), (225, 238, 248), np.clip(Y / 0.55, 0, 1))
    sea = lerp((40, 120, 170), (12, 60, 100), np.clip((Y - 0.55) / 0.45, 0, 1))
    m = (Y > 0.55).astype(np.float32)[..., None]
    img = sky * (1 - m) + sea * m
    img = glow(img, 0.3, 0.2, 0.25, (255, 250, 230), 0.5)
    waves = 6 * np.sin(Y * 400 + np.sin(X * 20) * 3) * (Y > 0.55)
    img = img + waves[..., None]
    return grain(blur(img, 1.2), 2)


def window_room():
    img = lerp((232, 226, 216), (196, 188, 176), Y)
    win = np.zeros((H, W), np.float32)
    x0, x1, y0, y1 = int(W * 0.52), int(W * 0.95), int(H * 0.12), int(H * 0.72)
    win[y0:y1, x0:x1] = 1
    for i in range(1, 4):  # window bars
        x = x0 + (x1 - x0) * i // 4
        win[y0:y1, x - 8:x + 8] = 0
    win[(y0 + y1) // 2 - 8:(y0 + y1) // 2 + 8, x0:x1] = 0
    outside = lerp((210, 232, 250), (150, 200, 140), np.clip((Y - 0.2) / 0.5, 0, 1))
    img = img * (1 - win[..., None]) + outside * win[..., None] * 1.05
    img = glow(img, 0.73, 0.4, 0.35, (40, 35, 20), 0.8)
    plant = np.zeros((H, W), np.float32)
    for _ in range(40):
        a = rng.uniform(-2.6, -0.5)
        L = rng.uniform(120, 300)
        p0 = (int(W * 0.2), int(H * 0.78))
        p1 = (int(p0[0] + np.cos(a) * L), int(p0[1] + np.sin(a) * L))
        cv2.line(plant, p0, p1, 1.0, int(rng.uniform(10, 22)), cv2.LINE_AA)
    img = img * (1 - plant[..., None] * 0.55) + plant[..., None] * np.array((40, 90, 50), np.float32) * 0.55
    floor = (Y > 0.8).astype(np.float32)[..., None]
    img = img * (1 - floor) + lerp((150, 120, 90), (110, 85, 62), Y) * floor
    return grain(blur(img, 7), 2)


def graphite():
    img = lerp((34, 36, 40), (20, 21, 24), np.clip(0.6 * X + 0.4 * Y, 0, 1))
    tex = blur(rng.normal(0, 1, (H, W)).astype(np.float32), 18)
    img = img + (tex / (np.abs(tex).max() + 1e-6) * 8)[..., None]
    img = glow(img, 0.2, 0.15, 0.6, (34, 197, 94), 0.18)
    return grain(vignette(img, 0.4), 2)


def brand():
    t = np.clip(0.6 * X + 0.4 * Y, 0, 1)
    img = lerp((22, 163, 74), (14, 116, 144), t) * 0.8
    img = glow(img, 0.8, 0.2, 0.5, (80, 255, 200), 0.25)
    return grain(vignette(img, 0.45), 2)


BACKGROUNDS = [("01-estudio", studio), ("02-ventanal", window_room), ("03-atardecer", sunset), ("04-bokeh", bokeh),
               ("05-aurora", aurora), ("06-oceano", ocean), ("07-grafito", graphite), ("08-pocketlens", brand)]

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in BACKGROUNDS:
        img = np.clip(fn(), 0, 255).astype(np.uint8)
        cv2.imwrite(str(OUT / f"{name}.jpg"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
        print(name)
