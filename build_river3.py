"""Rebuild mahanadi.river with physically defensible channel geometry.

Fixes from the audit:
  #1 width  - downstream hydraulic geometry W = a*Q^b anchored to the
              Mahanadi delta, replacing the fabricated 1.2*frac**0.5 cap
  #3 bed    - outlet bed forced to sit at/above MSL datum
  #4 slope  - MIN_SLOPE lowered so real terrain gradient survives carving
  #2        - outlet BC returned to FREE (HFIX was unit-wrong: it is a
              water-surface ELEVATION, and ch_flow.cpp subtracts bed to
              get depth, so HFIX 1.5 on a -0.067 m bed = 1.57 m -> 84 m3/s)

Hydraulic geometry (Leopold & Maddock downstream relations):
  W = a * Q_bankfull^b, b ~ 0.5 for large alluvial rivers.
  Anchored so the delta reaches ~4 km, consistent with the Mahanadi
  mouth near Paradip. Bankfull Q is scaled from upstream area by
  Q ~ A^0.8 (standard regional flood-frequency exponent).

osgeo before numpy (OSGeo4W DLL conflict).
"""
from osgeo import gdal  # noqa: F401
import numpy as np
import os

ROOT = r"D:/MRC_my"
ASC = os.path.join(ROOT, "mahanadi.asc")
OUT = os.path.join(ROOT, "mahanadi.river")

MANNING_CH = 0.035
MIN_SLOPE = 1.0e-6      # was 1e-5: that floor overwrote real terrain slope
OUTLET_UPLAND = 135524.0
Q_DESIGN = 45000.0      # design flood at outlet (matches .bdy peak)
W_OUTLET = 4000.0       # delta width at the mouth, m
W_HEAD = 60.0           # headwater channel width, m
BED_DATUM_MIN = 0.5     # keep outlet bed above MSL so HFIX/FREE are sane

hdr = {}
with open(ASC) as f:
    for _ in range(6):
        k, v = f.readline().split()
        hdr[k.lower()] = float(v)
nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
cs, xll, yll = hdr["cellsize"], hdr["xllcorner"], hdr["yllcorner"]
tly = yll + nr * cs

dem = np.loadtxt(ASC, skiprows=6, dtype=np.float32)
pts = np.load(os.path.join(ROOT, "_river_pts.npy"))
npts = len(pts)

d = np.r_[0.0, np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])))]

# ---- sample raw bed from DEM (3x3 min = thalweg proxy) ----
cols, rows, zs = [], [], []
for x, y in pts:
    i = min(max(int((x - xll) / cs), 0), nc - 1)
    j = min(max(int((tly - y) / cs), 0), nr - 1)
    w = dem[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
    v = w[w > -1000]
    cols.append(i)
    rows.append(j)
    zs.append(float(v.min()) if v.size else np.nan)
zs = np.array(zs, float)

# ---- width from downstream hydraulic geometry ----
# upstream area grows along the channel; use it to scale bankfull Q
frac_area = np.linspace(1.0 / npts, 1.0, npts) * OUTLET_UPLAND
q_bankfull = Q_DESIGN * (frac_area / OUTLET_UPLAND) ** 0.8
a_coef = W_OUTLET / Q_DESIGN ** 0.5
width = np.maximum(a_coef * q_bankfull ** 0.5, W_HEAD)

print(f"width: {width[0]:.0f} -> {width[-1]:.0f} m "
      f"(a={a_coef:.3f}, b=0.5)")

# ---- monotonic bed via smoothing, NOT cell-by-cell clamping ----
# The old approach walked downstream capping each point against its
# neighbour minus MIN_SLOPE. Where the raw DEM was noisy that floor
# propagated for hundreds of km and replaced real terrain gradient
# (1.3e-4 measured) with the floor itself (1e-5), collapsing outlet
# conveyance from ~60000 to ~150 m3/s. Instead: smooth first, then
# enforce monotonicity only against the smoothed trend.
z = zs.copy()
bad = ~np.isfinite(z)
if bad.any():
    z[bad] = np.interp(d[bad], d[~bad], z[~bad])

# running-mean smooth over ~15 km to kill DEM noise
win = max(3, int(15000.0 / max(np.median(np.diff(d)), 1.0)) | 1)
pad = win // 2
zs_pad = np.r_[np.full(pad, z[0]), z, np.full(pad, z[-1])]
z_sm = np.convolve(zs_pad, np.ones(win) / win, mode="valid")

# isotonic (non-increasing) projection of the smoothed profile
z_mono = np.minimum.accumulate(z_sm)

# guarantee a strictly non-zero gradient without flattening terrain
for k in range(1, npts):
    cap = z_mono[k - 1] - MIN_SLOPE * (d[k] - d[k - 1])
    z_mono[k] = min(z_mono[k], cap)
z = z_mono

if z[-1] < BED_DATUM_MIN:
    z += (BED_DATUM_MIN - z[-1])
resid = float(np.nanmax(np.abs(z - zs[~bad].mean() * 0 - zs))) if npts else 0
print(f"smoothing window {win} pts; max |z - raw| = {resid:.2f} m")
print(f"bed: {z[0]:.2f} -> {z[-1]:.2f} m")

# ---- conveyance check at the outlet ----
s_out = max((z[-6] - z[-1]) / (d[-1] - d[-6]), MIN_SLOPE)
for h in (8.0, 12.0, 15.0):
    q = (1.0 / MANNING_CH) * width[-1] * h ** (5.0 / 3.0) * s_out ** 0.5
    print(f"  outlet capacity @ {h:4.1f} m depth, slope {s_out:.2e}: "
          f"{q:9.0f} m3/s")

lines = [str(npts)]
for k in range(npts):
    r = (f"{pts[k,0]:.2f}\t{pts[k,1]:.2f}\t{width[k]:.2f}\t"
         f"{MANNING_CH:.3f}\t{z[k]:.3f}")
    if k == 0:
        r += "\tQVAR\tmahanadi_inflow"
    elif k == npts - 1:
        r += "\tFREE\t-1"
    lines.append(r)

with open(OUT, "w", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(f"WROTE {OUT}")

np.save(os.path.join(ROOT, "_river_cells.npy"),
        np.c_[cols, rows, pts[:, 0], pts[:, 1], z, width])
