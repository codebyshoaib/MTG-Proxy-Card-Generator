#!/usr/bin/env python3
"""Find the blank panels the model painted, so text can be printed into them.

The model is asked to leave a name banner, a type ribbon, a rules panel and (on creatures) a
power/toughness plaque blank. It obeys, but it puts them in a different place and a different
shape every single generation — so they have to be found, not assumed.

Method: shrink the card, mark every pixel whose neighbourhood is flat, group those pixels into
connected blobs, then score each blob on how much it looks like a panel — roughly rectangular,
wider than tall, big enough to print into, in the part of the card where that panel belongs.

Pure numpy/PIL on a 224px-wide copy, so the flood fill stays cheap.
"""
from collections import deque
import numpy as np
from PIL import Image, ImageFilter

SMALL_W = 224


def _flat_mask(im, tol):
    """True where the picture is locally smooth — i.e. a surface, not illustration."""
    g = im.convert("L").resize((SMALL_W, int(SMALL_W * im.height / im.width)))
    a = np.asarray(g, dtype=np.float32)
    blur = np.asarray(g.filter(ImageFilter.GaussianBlur(3)), dtype=np.float32)
    return np.abs(a - blur) < tol, a.shape


def _components(mask):
    """Label connected True regions. 4-connectivity, iterative, small images only."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            q, px = deque([(sy, sx)]), []
            seen[sy, sx] = True
            while q:
                y, x = q.popleft()
                px.append((y, x))
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            yield px


def _score(px, shape, y_lo, y_hi, min_w, min_h, max_h, x_lo=0.0, max_w=1.0):
    h, w = shape
    ys = [p[0] for p in px]; xs = [p[1] for p in px]
    y0, y1, x0, x1 = min(ys), max(ys), min(xs), max(xs)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    cy = (y0 + y1) / 2 / h
    if not (y_lo <= cy <= y_hi):
        return None
    if bw < w * min_w or bh < h * min_h or bh > h * max_h or bw < bh:
        return None
    if bw > w * max_w or (x0 + x1) / 2 / w < x_lo:
        return None
    rect = len(px) / (bw * bh)          # how completely the blob fills its own box
    if rect < 0.55:
        return None
    return (bw * bh) * rect, (x0, y0, x1, y1)


def find(im, kind):
    """kind: 'rules' | 'ribbon' | 'plaque'. Returns a box in full-resolution coordinates."""
    spec = {"rules":  dict(y_lo=0.58, y_hi=0.97, min_w=0.30, min_h=0.055, max_h=0.34),
            "ribbon": dict(y_lo=0.40, y_hi=0.80, min_w=0.45, min_h=0.015, max_h=0.055),
            "plaque": dict(y_lo=0.80, y_hi=0.99, min_w=0.045, min_h=0.015, max_h=0.085,
                           x_lo=0.70, max_w=0.26)}[kind]
    best = None
    for tol in (5, 8, 12, 17, 24, 33):
        mask, shape = _flat_mask(im, tol)
        for px in _components(mask):
            if len(px) < 40:
                continue
            s = _score(px, shape, **spec)
            if s and (best is None or s[0] > best[0]):
                best = s
    if not best:
        return None
    x0, y0, x1, y1 = best[1]
    k = im.width / SMALL_W
    return int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)
