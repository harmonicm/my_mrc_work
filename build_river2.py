"""Stage 2: sample DEM bed elevation at each cross-section, enforce
non-increasing bed downstream, estimate width, and write mahanadi.river.

osgeo before numpy (OSGeo4W DLL conflict).
"""
from osgeo import gdal  # noqa: F401  (import order matters)
import numpy as np
import os

ROOT = r"D:/MRC_my"
ASC = os.path.join(ROOT, "mahanadi.asc")
OUT = os.path.join(ROOT, "mahanadi.river")

MANNING_CH = 0.035
MIN_SLOPE = 1e-5          # enforced minimum downstream bed drop (m/m)
OUTLET_UPLAND = 135524.0  # km2 at outlet, from HydroRIVERS


def read_asc_header(path):
    hdr = {}
    with open(path) as f:
        for _ in range(6):
            parts = f.readline().split()
            if len(parts) != 2:
                break
            try:
                hdr[parts[0].lower()] = float(parts[1])
            except ValueError:
                break
    return hdr


hdr = read_asc_header(ASC)
nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
cs = hdr["cellsize"]
xll, yll = hdr["xllcorner"], hdr["yllcorner"]
tlx, tly = xll, yll + nr * cs

print("loading DEM grid ...")
dem = np.loadtxt(ASC, skiprows=6, dtype=np.float32)
print("DEM array:", dem.shape)
assert dem.shape == (nr, nc), f"shape mismatch {dem.shape} vs {(nr, nc)}"

pts = np.load(os.path.join(ROOT, "_river_pts.npy"))
print("cross-sections:", len(pts))

# ---- sample DEM: min of a 3x3 window (channel bed sits below cell mean) ----
rows, cols, zs = [], [], []
for x, y in pts:
    i = int((x - tlx) / cs)
    j = int((tly - y) / cs)
    i = min(max(i, 0), nc - 1)
    j = min(max(j, 0), nr - 1)
    w = dem[max(0, j - 1):j + 2, max(0, i - 1):i + 2]
    valid = w[w > -1000]
    rows.append(j)
    cols.append(i)
    zs.append(float(valid.min()) if valid.size else np.nan)

zs = np.array(zs, dtype=float)
print(f"raw bed elev: min={np.nanmin(zs):.2f} max={np.nanmax(zs):.2f}")

# ---- chainage along channel ----
d = np.r_[0.0, np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])))]
print(f"channel length: {d[-1]/1000:.1f} km")

# ---- enforce non-increasing bed downstream (fix pits/reversals) ----
z = zs.copy()
fixed = 0
for k in range(1, len(z)):
    cap = z[k - 1] - MIN_SLOPE * (d[k] - d[k - 1])
    if not np.isfinite(z[k]) or z[k] > cap:
        z[k] = cap
        fixed += 1
print(f"monotonicity: adjusted {fixed}/{len(z)} points "
      f"({100*fixed/len(z):.0f}%)")
print(f"carved bed: {z[0]:.2f} -> {z[-1]:.2f} m, "
      f"mean slope={(z[0]-z[-1])/d[-1]:.2e}")

# ---- width: downstream hydraulic geometry scaled by upland area ----
frac = np.linspace(0.02, 1.0, len(z)) * OUTLET_UPLAND
width = np.clip(1.2 * frac ** 0.5, 30.0, 900.0)
print(f"width: {width[0]:.0f} -> {width[-1]:.0f} m")

# ---- write .river (x y width n bed_elev); QVAR inflow, FREE outlet ----
lines = ["mahanadi_channel", str(len(z))]
for k, ((x, y), w, zz) in enumerate(zip(pts, width, z)):
    row = f"{x:.2f}\t{y:.2f}\t{w:.2f}\t{MANNING_CH:.3f}\t{zz:.3f}"
    if k == 0:
        row += "\tQVAR\tmahanadi_inflow"
    elif k == len(z) - 1:
        row += "\tFREE\t-1"
    lines.append(row)

with open(OUT, "w", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
print(f"WROTE {OUT}  ({len(z)} cross-sections)")

np.save(os.path.join(ROOT, "_river_cells.npy"),
        np.c_[cols, rows, pts[:, 0], pts[:, 1], z, width])
print("wrote _river_cells.npy")
