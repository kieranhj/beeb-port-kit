"""orient.py - screen rotation, measured: raw space, play space, cells and flip bits.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/arcade.py` (`to_play`, `flips_to_play`), `tools/verify_orientation.py`
and `tools/mame/orient.lua` (decision 13, BUGS.md #1, CLAUDE.md s2).

A vertical cabinet's hardware scans a landscape raster; the player sees it rotated.
MAME's driver, its tilemap RAM, its sprite records and EVERY CELL IN THE GRAPHICS ROMS
are in the hardware's orientation (RAW); MAME rotates the finished screen at the end.
So every dimension is ambiguous until its space is named, and a port that draws in
the player's orientation (PLAY) has to rotate placements, cell contents AND the
attribute flip bits.

How 1942 measured it, 2026-09-07: the visible tilemap was rebuilt from captured
tilemap RAM and the scroll counter, rendered under all four rotations, and matched
against a MAME screenshot of the same frame:

    ROT270:  play(x, y) = raw(255 - y, x)       96.3% of pixels identical
    other three rotations                        46-48%

The residual 3.7% was the HUD and one sprite, which the rebuild did not draw. The
scene was mostly sea, which is the trap: a SYMMETRIC scene passes a broken rotation,
and 1942's sea tile happened to be diagonally hatched, which is what made the test
discriminate. `score_rotations` refuses to name a winner without a margin.

The first level reconstruction placed every tile right and drew every one 90 degrees
out, and "it looks like terrain" passed it (BUGS.md #1): the aircraft are nearly
symmetric. `-listxml` gives the driver's rotate attribute; treat it as the
prediction and this as the measurement.

CONVENTIONS. An image is a list of rows (row = y, column = x), raw W wide and H high.
The rotation names are MAME's ROT flags: the rotation applied to the raw raster to
get what the player sees, CLOCKWISE in degrees.

    ROT0     play(x, y) = raw(x, y)                      play is W x H
    ROT90    play(x, y) = raw(y, H - 1 - x)              play is H x W
    ROT180   play(x, y) = raw(W - 1 - x, H - 1 - y)      play is W x H
    ROT270   play(x, y) = raw(W - 1 - y, x)              play is H x W

and per cell (w x h) the same mapping with the cell's own size - for ROT270,
play[r][c] = raw[c][w - 1 - r], 1942's `arcade.to_play`. Under ROT90/ROT270 a raw
X-flip is a play Y-flip and vice versa; under ROT0/ROT180 they stay put.
"""

ROTATIONS = (0, 90, 180, 270)


def _check(rot):
    if rot not in ROTATIONS:
        raise ValueError("rotation must be one of %s, not %r" % (ROTATIONS, rot))


def play_size(raw_w, raw_h, rot):
    _check(rot)
    return (raw_h, raw_w) if rot in (90, 270) else (raw_w, raw_h)


def play_to_raw(x, y, raw_w, raw_h, rot):
    """The raw coordinate shown at play (x, y)."""
    _check(rot)
    if rot == 0:
        return x, y
    if rot == 90:
        return y, raw_h - 1 - x
    if rot == 180:
        return raw_w - 1 - x, raw_h - 1 - y
    return raw_w - 1 - y, x


def raw_to_play(x, y, raw_w, raw_h, rot):
    """Where raw (x, y) appears in play space."""
    _check(rot)
    if rot == 0:
        return x, y
    if rot == 90:
        return raw_h - 1 - y, x
    if rot == 180:
        return raw_w - 1 - x, raw_h - 1 - y
    return y, raw_w - 1 - x


def to_play(rows, rot):
    """Rotate an image or a cell (list of rows) from raw into play space."""
    _check(rot)
    h, w = len(rows), len(rows[0])
    pw, ph = play_size(w, h, rot)
    out = []
    for y in range(ph):
        row = []
        for x in range(pw):
            rx, ry = play_to_raw(x, y, w, h, rot)
            row.append(rows[ry][rx])
        out.append(row)
    return out


def to_raw(rows, rot):
    """The inverse of to_play: a play-space image back to raw."""
    _check(rot)
    ph, pw = len(rows), len(rows[0])
    w, h = (ph, pw) if rot in (90, 270) else (pw, ph)
    out = [[None] * w for _ in range(h)]
    for y in range(ph):
        for x in range(pw):
            rx, ry = play_to_raw(x, y, w, h, rot)
            out[ry][rx] = rows[y][x]
    return out


def flips_to_play(raw_fx, raw_fy, rot):
    """(play_fx, play_fy) for attribute flip bits defined in raw space.

    A flip mirrors about an axis, and the rotation moves the axis: under ROT90 and
    ROT270 raw X becomes play Y. Under ROT180 both axes reverse but a mirror stays a
    mirror on the same axis, so the bits are unchanged."""
    _check(rot)
    return (raw_fy, raw_fx) if rot in (90, 270) else (raw_fx, raw_fy)


def flip(rows, fx, fy):
    """Apply X and/or Y flip to a list of rows."""
    out = [list(reversed(r)) if fx else list(r) for r in rows]
    return list(reversed(out)) if fy else out


def _pixels(img):
    """Accept a list of rows or anything with .size and .getdata() (a PIL image)."""
    if hasattr(img, "getdata") and hasattr(img, "size"):
        w, h = img.size
        flat = getattr(img, "get_flattened_data", None) or img.getdata   # Pillow 12+
        d = list(flat())
        return [d[y * w:(y + 1) * w] for y in range(h)]
    return img


def agreement(a, b):
    """Fraction of identical pixels between two same-shaped images, or None if their
    shapes differ."""
    a, b = _pixels(a), _pixels(b)
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return None
    same = sum(1 for ra, rb in zip(a, b) for pa, pb in zip(ra, rb) if pa == pb)
    return same / float(len(a) * len(a[0]))


class NotDiscriminating(Exception):
    pass


def score_rotations(raw_render, reference, margin=0.2):
    """Render-in-raw against a same-frame screenshot, under all four rotations.

    Returns (best_rotation, {rotation: fraction or None}). A rotation whose play
    shape does not match the reference scores None. Raises NotDiscriminating unless
    the best beats the runner-up by `margin` - a near-tie means the scene is too
    symmetric to tell (pick a frame with diagonal or asymmetric content), not that
    either answer is right. 1942 measured 0.963 against 0.46-0.48."""
    raw = _pixels(raw_render)
    scores = {}
    for rot in ROTATIONS:
        scores[rot] = agreement(to_play(raw, rot), reference)
    ranked = sorted((s, r) for r, s in scores.items() if s is not None)
    if not ranked:
        raise NotDiscriminating("no rotation gives the reference's shape")
    best_s, best = ranked[-1]
    second = ranked[-2][0] if len(ranked) > 1 else 0.0
    if best_s - second < margin:
        raise NotDiscriminating("best ROT%d %.3f against %.3f: within %.2f - the scene "
                                "does not discriminate" % (best, best_s, second, margin))
    return best, scores
