"""Background effects (blur / virtual background) with on-device person segmentation (MediaPipe selfie segmenter).

Everything runs locally on the PC; frames never leave the machine.

Precise pipeline (per frame, ~10-16 ms at 720p):
  1. segment the whole frame (fast landscape model)
  2. zoom in: segment again on a crop around the person (more model pixels on the edges)
  3. drop detached blobs (objects mistaken for a person)
  4. temporal smoothing (no edge flicker)
  5. edge-aware refinement with a guided filter (mask edges snap to real image edges)
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np

try:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    IMPORT_ERROR = None
except Exception as _e:  # noqa: BLE001
    cv2 = mp = vision = BaseOptions = None
    IMPORT_ERROR = f"{_e.__class__.__name__}: {_e}"

WORK_W = 640  # mask work resolution (width); height follows the frame aspect


def _asset(*parts: str) -> Path | None:
    here = Path(__file__).resolve().parent
    for d in (getattr(sys, "_MEIPASS", None), here, Path(sys.executable).resolve().parent):
        if d and Path(d, "assets", *parts).exists():
            return Path(d, "assets", *parts)
    return None


def builtin_backgrounds() -> list[Path]:
    d = _asset("backgrounds")
    return sorted(d.glob("*.jpg")) if d else []


def available() -> tuple[bool, str]:
    if IMPORT_ERROR:
        return False, "Falta el módulo de IA (mediapipe): " + IMPORT_ERROR
    if not _asset("models", "selfie_segmenter.tflite"):
        return False, "No se encontró el modelo de segmentación"
    return True, ""


class BackgroundFilter:
    """process() must be called from a single thread."""

    def __init__(self):
        ok, why = available()
        if not ok:
            raise RuntimeError(why)
        self._models: dict[str, object] = {}
        self._prev = None          # previous low-res mask for temporal smoothing
        self._ts = 0
        self._bg_key = None
        self._bg = None
        self._has_guided = hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "guidedFilter")
        self.person = False        # a person is currently detected
        self.coverage = 0.0        # fraction of frame covered by person
        # segmentation runs in its own thread; process() composites with the latest mask (<= 1 frame old)
        self._cv = threading.Condition()
        self._job = None           # (frame, precise) waiting to be segmented
        self._mask = None          # latest full-resolution mask
        self._seg_error = None
        self._stop = False
        self._thread = None

    # ------------------------------------------------------------------ model
    def _model(self, landscape: bool):
        name = "selfie_segmenter_landscape.tflite" if landscape else "selfie_segmenter.tflite"
        m = self._models.get(name)
        if m is None:
            opts = vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_buffer=_asset("models", name).read_bytes()),
                running_mode=vision.RunningMode.VIDEO,
                output_confidence_masks=True,
                output_category_mask=False,
            )
            m = self._models[name] = vision.ImageSegmenter.create_from_options(opts)
        return m, ((256, 144) if landscape else (256, 256))

    def _infer(self, rgb: np.ndarray) -> np.ndarray:
        h, w = rgb.shape[:2]
        seg, (mw, mh) = self._model(w > h * 1.4)
        small = np.ascontiguousarray(cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA))
        self._ts = max(self._ts + 1, int(time.monotonic() * 1000))
        res = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=small), self._ts)
        m = np.array(res.confidence_masks[0].numpy_view(), np.float32).reshape(mh, mw)
        return cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)

    def _loop(self) -> None:
        while True:
            with self._cv:
                while self._job is None and not self._stop:
                    self._cv.wait()
                if self._stop:
                    break
                frame, precise = self._job
                self._job = None
            try:
                mask = self.person_mask(frame, precise)
            except Exception as e:  # noqa: BLE001
                with self._cv:
                    self._seg_error = e
                    self._cv.notify_all()
                break
            with self._cv:
                self._mask = mask
                self._cv.notify_all()
        for m in self._models.values():
            try:
                m.close()
            except Exception:  # noqa: BLE001
                pass
        self._models.clear()

    def _latest_mask(self, rgb: np.ndarray, precise: bool) -> np.ndarray:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True, name="bg-segment")
            self._thread.start()
        h, w = rgb.shape[:2]
        with self._cv:
            if self._seg_error:
                raise self._seg_error
            self._job = (rgb, precise)  # replaces an older pending frame: always segment the newest
            self._cv.notify_all()
            if self._mask is None or self._mask.shape != (h, w):
                # first frame (or new size): wait for a matching mask
                deadline = time.monotonic() + 5
                while (self._mask is None or self._mask.shape != (h, w)) and not self._seg_error:
                    if not self._cv.wait(max(0.0, deadline - time.monotonic())):
                        raise TimeoutError("la segmentación no respondió")
                if self._seg_error:
                    raise self._seg_error
            return self._mask

    def close(self) -> None:
        if self._thread is not None:
            with self._cv:
                self._stop = True
                self._cv.notify_all()
            self._thread.join(2)
            return
        for m in self._models.values():
            try:
                m.close()
            except Exception:  # noqa: BLE001
                pass
        self._models.clear()

    # ------------------------------------------------------------------ mask
    @staticmethod
    def _keep_main(m: np.ndarray) -> np.ndarray:
        """Remove blobs that are much smaller than the main person (false positives)."""
        b = (m > 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(b, connectivity=8)
        if n <= 2:
            return m
        areas = st[1:, cv2.CC_STAT_AREA]
        keep = np.zeros(n, np.float32)
        keep[1:] = areas >= areas.max() * 0.15
        k = cv2.dilate(keep[lab], np.ones((9, 9), np.uint8))
        return m * k

    def person_mask(self, rgb: np.ndarray, precise: bool = True) -> np.ndarray:
        """Full-resolution float32 mask (1 = person)."""
        h, w = rgb.shape[:2]
        ww, wh = WORK_W, max(2, int(round(WORK_W * h / w)))
        work = cv2.resize(rgb, (ww, wh), interpolation=cv2.INTER_AREA)
        m = self._infer(work)
        if precise:
            ys, xs = np.nonzero(m > 0.5)
            if len(xs) > 50:
                x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
                px, py = (x1 - x0) * 0.12 + 8, (y1 - y0) * 0.12 + 8
                x0, x1 = int(max(0, x0 - px)), int(min(ww, x1 + px))
                y0, y1 = int(max(0, y0 - py)), int(min(wh, y1 + py))
                if (x1 - x0) * (y1 - y0) < 0.8 * ww * wh and x1 - x0 > 16 and y1 - y0 > 16:
                    crop = self._infer(np.ascontiguousarray(work[y0:y1, x0:x1]))
                    m2 = np.zeros_like(m)
                    # keep a little of the full-frame estimate so parts outside the crop are not lost abruptly
                    m2[y0:y1, x0:x1] = np.maximum(crop, m[y0:y1, x0:x1] * 0.5)
                    m = m2
            m = self._keep_main(m)
        if self._prev is not None and self._prev.shape == m.shape:
            m = 0.6 * m + 0.4 * self._prev  # temporal smoothing
        self._prev = m
        self.coverage = float((m > 0.5).mean())
        self.person = self.coverage > 0.015
        k = np.clip((m - 0.3) / 0.4, 0.0, 1.0)
        if precise and self._has_guided:
            k = cv2.ximgproc.guidedFilter(guide=work, src=k, radius=6, eps=6.5)
            k = np.clip((k - 0.5) * 1.6 + 0.5, 0.0, 1.0)
        else:
            k = cv2.GaussianBlur(k, (5, 5), 0)
        return cv2.resize(k.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)

    # ------------------------------------------------------------------ backgrounds
    @staticmethod
    def _blurred(rgb: np.ndarray, strength: int) -> np.ndarray:
        """strength 1..100 → gaussian sigma up to ~60 px at full resolution (computed at 1/4 size)."""
        h, w = rgb.shape[:2]
        s = max(1, min(100, int(strength))) / 100.0
        f = 4 if s <= 0.5 else 8  # strong blur: work at lower resolution (same look, faster)
        small = cv2.resize(rgb, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), (2.4 + 57.6 * s) / f)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _image_bg(self, path: str | None, w: int, h: int) -> np.ndarray:
        key = (path, w, h)
        if key == self._bg_key and self._bg is not None:
            return self._bg
        img = None
        if path:
            raw = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR) if Path(path).is_file() else None
            if raw is not None:
                raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
                ih, iw = raw.shape[:2]
                s = max(w / iw, h / ih)  # cover + center crop
                nw, nh = max(w, int(round(iw * s))), max(h, int(round(ih * s)))
                raw = cv2.resize(raw, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
                x, y = (nw - w) // 2, (nh - h) // 2
                img = np.ascontiguousarray(raw[y:y + h, x:x + w])
        if img is None:  # missing file: neutral dark gradient
            gy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
            img = np.ascontiguousarray(np.broadcast_to(60 - 30 * gy, (h, w, 3)).astype(np.uint8))
        self._bg_key, self._bg = key, img
        return img

    # ------------------------------------------------------------------ main
    def process(self, rgb: np.ndarray, mode: str, image_path: str | None = None,
                strength: int = 50, precise: bool = True) -> np.ndarray:
        """mode: "blur" or "image"."""
        h, w = rgb.shape[:2]
        mask = self._latest_mask(rgb, precise)
        bg = self._image_bg(image_path, w, h) if mode == "image" else self._blurred(rgb, strength)
        return cv2.blendLinear(rgb, bg, mask, 1.0 - mask)
