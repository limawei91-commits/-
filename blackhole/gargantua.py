"""
Gargantua-style black hole renderer (Schwarzschild geodesic ray tracer).

Every pixel's light ray is integrated backwards through curved spacetime, so the
"arch" over the shadow, the lower arc and the thin photon ring all come out of the
physics instead of being faked with extra geometry.

Units: Schwarzschild radius r_s = 1. Photon paths obey
    x'' = -1.5 * h^2 * x / r^5,   h = |x × x'|
which reproduces the exact null-geodesic shape in Schwarzschild spacetime.

Like the film, the disk is shown without Doppler beaming or redshift colouring
(pass --doppler to turn beaming on for the physically "honest" version).

Usage:
    python3 gargantua.py --width 1920 --height 1080 --out gargantua.png
    python3 gargantua.py --width 1280 --height 720 --frames 240 --out gargantua.mp4
"""
import argparse
import math
import subprocess

import numpy as np
from PIL import Image, ImageFilter


def normalize(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def trace(W, H, dist, incl_deg, fov_deg, roll_deg, r_in, r_out, max_hits=5, max_steps=4000):
    th = math.radians(incl_deg)
    cam = np.array([0.0, -dist * math.cos(th), dist * math.sin(th)])
    fwd = -cam / np.linalg.norm(cam)
    right = normalize(np.cross(fwd, [0.0, 0.0, 1.0]))
    up = np.cross(right, fwd)
    ro = math.radians(roll_deg)
    right, up = right * math.cos(ro) + up * math.sin(ro), -right * math.sin(ro) + up * math.cos(ro)

    t = math.tan(math.radians(fov_deg) / 2)
    xs = ((np.arange(W) + 0.5) / W * 2 - 1) * t
    ys = (1 - (np.arange(H) + 0.5) / H * 2) * t * H / W
    X, Y = np.meshgrid(xs, ys)
    d = normalize(fwd + X[..., None] * right + Y[..., None] * up).reshape(-1, 3)
    N = d.shape[0]

    x = np.broadcast_to(cam, (N, 3)).copy()
    v = d.copy()
    h2 = np.sum(np.cross(x, v) ** 2, axis=1)

    hit_r = np.zeros((N, max_hits))
    hit_phi = np.zeros((N, max_hits))
    hit_vel = np.zeros((N, max_hits))  # line-of-sight factor for optional Doppler
    nhit = np.zeros(N, dtype=np.int64)
    escaped = np.zeros(N, dtype=bool)
    esc_dir = np.zeros((N, 3))

    idx = np.arange(N)
    escape_r = dist * 1.3

    def acc(p, k):
        r = np.linalg.norm(p, axis=1)
        return -1.5 * k[:, None] * p / (r ** 5)[:, None]

    for _ in range(max_steps):
        if idx.size == 0:
            break
        r = np.linalg.norm(x, axis=1)
        dt = np.clip(0.03 * r, 0.002, 1.5)[:, None]

        k1x, k1v = v, acc(x, h2)
        k2x, k2v = v + 0.5 * dt * k1v, acc(x + 0.5 * dt * k1x, h2)
        k3x, k3v = v + 0.5 * dt * k2v, acc(x + 0.5 * dt * k2x, h2)
        k4x, k4v = v + dt * k3v, acc(x + dt * k3x, h2)
        xn = x + dt / 6 * (k1x + 2 * k2x + 2 * k3x + k4x)
        vn = v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)

        z0, z1 = x[:, 2], xn[:, 2]
        cross = (z0 * z1 < 0)
        if cross.any():
            c = np.nonzero(cross)[0]
            f = (z0[c] / (z0[c] - z1[c]))[:, None]
            p = x[c] + f * (xn[c] - x[c])
            pr = np.hypot(p[:, 0], p[:, 1])
            ok = (pr >= r_in * 0.97) & (pr <= r_out) & (nhit[idx[c]] < max_hits)
            c, p, pr = c[ok], p[ok], pr[ok]
            g = idx[c]
            slot = nhit[g]
            hit_r[g, slot] = pr
            hit_phi[g, slot] = np.arctan2(p[:, 1], p[:, 0])
            # disk orbital velocity direction (counter-clockwise) dotted with ray direction
            tang = np.stack([-p[:, 1], p[:, 0], np.zeros_like(pr)], axis=1) / pr[:, None]
            hit_vel[g, slot] = -np.sum(tang * normalize(vn[c]), axis=1) * np.sqrt(0.5 / np.maximum(pr - 1.0, 0.5))
            nhit[g] += 1

        rn = np.linalg.norm(xn, axis=1)
        out = (rn > escape_r) & (np.sum(xn * vn, axis=1) > 0)
        fell = rn < 1.0
        escaped[idx[out]] = True
        esc_dir[idx[out]] = normalize(vn[out])
        keep = ~(out | fell)
        idx, x, v, h2 = idx[keep], xn[keep], vn[keep], h2[keep]

    return dict(W=W, H=H, hit_r=hit_r, hit_phi=hit_phi, hit_vel=hit_vel,
                nhit=nhit, escaped=escaped, esc_dir=esc_dir)


class StreakNoise:
    """Fractal value noise in (radius, angle), periodic in angle: long tangential streaks."""

    def __init__(self, seed=7, octaves=6):
        rng = np.random.default_rng(seed)
        self.grids = []
        for o in range(octaves):
            nr, na = 60 * 2 ** o, 12 * 2 ** o
            self.grids.append((rng.random((nr + 1, na)), nr, na, 0.55 ** o))

    def __call__(self, r_norm, phi):
        total, wsum = 0.0, 0.0
        a = (phi / (2 * np.pi)) % 1.0
        for grid, nr, na, w in self.grids:
            u = np.clip(r_norm, 0, 1) * nr
            vv = a * na
            i0 = np.minimum(np.floor(u).astype(int), nr - 1)
            j0 = np.floor(vv).astype(int) % na
            j1 = (j0 + 1) % na
            fu = u - i0
            fv = vv - np.floor(vv)
            fu = fu * fu * (3 - 2 * fu)
            fv = fv * fv * (3 - 2 * fv)
            n = (grid[i0, j0] * (1 - fu) * (1 - fv) + grid[i0 + 1, j0] * fu * (1 - fv)
                 + grid[i0, j1] * (1 - fu) * fv + grid[i0 + 1, j1] * fu * fv)
            total = total + n * w
            wsum += w
        return total / wsum


def make_starfield(seed=3, w=4096, h=2048):
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 3))
    yy = np.linspace(-1, 1, h)[:, None]
    img += np.array([0.010, 0.020, 0.045]) * (1.0 - 0.5 * np.abs(yy))[..., None]
    n = 9000
    sx, sy = rng.integers(0, w, n), rng.integers(0, h, n)
    b = rng.pareto(2.2, n) * 0.25
    tint = np.stack([0.8 + 0.2 * rng.random(n), 0.85 + 0.1 * rng.random(n), np.ones(n)], 1)
    img[sy, sx] += b[:, None] * tint
    pil = Image.fromarray(np.uint8(np.clip(img, 0, 1) * 255))
    blurred = np.asarray(pil.filter(ImageFilter.GaussianBlur(0.7)), dtype=float) / 255
    return np.maximum(img, blurred * 1.5)


def shade(tr, r_in, r_out, t=0.0, doppler=False, stars=None, noise=None, exposure=1.7):
    W, H = tr["W"], tr["H"]
    N = W * H
    col = np.zeros((N, 3))
    T = np.ones(N)
    hot = np.array([1.0, 0.93, 0.85])
    warm = np.array([1.0, 0.62, 0.36])

    for k in range(tr["hit_r"].shape[1]):
        m = tr["nhit"] > k
        if not m.any():
            break
        r = tr["hit_r"][m, k]
        phi = tr["hit_phi"][m, k]
        omega = 0.6 * r ** -1.5                      # Keplerian differential rotation
        rn = (r - r_in) / (r_out - r_in)
        ph = phi - omega * t
        warp = noise(rn * 0.25 + 0.5, ph * 0.5) - 0.5     # coarse wobble so streaks wander
        s = noise(rn + 0.04 * warp, ph)
        clump = np.clip(noise(rn * 0.4 + 0.3, ph * 2.0 + 1.0) * 1.4 - 0.1, 0.45, 1.3)
        streak = np.clip((s - 0.25) / 0.45, 0, 1) ** 1.3
        prof = (r_in / r) ** 1.6
        prof *= np.clip((r - r_in) / 0.35, 0, 1)
        prof *= np.clip((r_out - r) / (0.35 * (r_out - r_in)), 0, 1) ** 1.5
        I = prof * (0.3 + 2.2 * streak) * clump
        if doppler:
            beta = np.clip(tr["hit_vel"][m, k], -0.7, 0.7)
            I = I * ((np.sqrt(1 - beta ** 2) / (1 - beta)) ** 3)
        alpha = np.clip(I * 1.1, 0, 0.97)
        c = hot * np.clip(1 - rn * 1.6, 0, 1)[:, None] + warm * np.clip(rn * 1.6, 0, 1)[:, None]
        col[m] += (T[m] * alpha * I * 2.2)[:, None] * c
        T[m] *= 1 - alpha

    if stars is not None:
        e = tr["escaped"]
        d = tr["esc_dir"][e]
        sh, sw = stars.shape[:2]
        lon = (np.arctan2(d[:, 1], d[:, 0]) / (2 * np.pi) + 0.5) * sw
        lat = (0.5 - np.arcsin(np.clip(d[:, 2], -1, 1)) / np.pi) * sh
        bg = stars[np.clip(lat.astype(int), 0, sh - 1), np.clip(lon.astype(int), 0, sw - 1)]
        col[e] += T[e][:, None] * bg

    img = col.reshape(H, W, 3) * exposure
    # bloom: blurred bright pass at several radii
    bright = np.clip(img - 0.6, 0, None)
    bpil = [Image.fromarray(np.uint8(np.clip(bright[..., i] / 4, 0, 1) * 255)) for i in range(3)]
    bloom = np.zeros_like(img)
    for rad, w in ((W / 300, 0.6), (W / 90, 0.45), (W / 30, 0.35)):
        bloom += w * 4 * np.stack([np.asarray(b.filter(ImageFilter.GaussianBlur(rad)), float) / 255 for b in bpil], -1)
    img = img + bloom
    img = 1 - np.exp(-img)                           # filmic-ish tone curve
    img = img ** (1 / 1.1)
    return np.uint8(np.clip(img, 0, 1) * 255)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--dist", type=float, default=24.0, help="camera distance in r_s")
    ap.add_argument("--incl", type=float, default=6.0, help="camera elevation above disk, degrees")
    ap.add_argument("--fov", type=float, default=52.0)
    ap.add_argument("--roll", type=float, default=-12.0)
    ap.add_argument("--r-in", type=float, default=3.0, help="inner disk edge (ISCO = 3 r_s)")
    ap.add_argument("--r-out", type=float, default=20.0)
    ap.add_argument("--doppler", action="store_true")
    ap.add_argument("--frames", type=int, default=1, help=">1 renders an mp4 of the rotating disk")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default="gargantua.png")
    a = ap.parse_args()

    print("tracing geodesics ...", flush=True)
    tr = trace(a.width, a.height, a.dist, a.incl, a.fov, a.roll, a.r_in, a.r_out)
    stars, noise = make_starfield(), StreakNoise()

    if a.frames <= 1:
        Image.fromarray(shade(tr, a.r_in, a.r_out, 0.0, a.doppler, stars, noise)).save(a.out)
        print("saved", a.out)
        return

    # geodesics are traced once; each frame only re-shades the rotating disk
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{a.width}x{a.height}", "-r", str(a.fps), "-i", "-",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", a.out],
                          stdin=subprocess.PIPE)
    for f in range(a.frames):
        ff.stdin.write(shade(tr, a.r_in, a.r_out, f * 0.25, a.doppler, stars, noise).tobytes())
        if f % 20 == 0:
            print(f"frame {f}/{a.frames}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("saved", a.out)


if __name__ == "__main__":
    main()
