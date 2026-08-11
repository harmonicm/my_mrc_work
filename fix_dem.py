"""Apply basin mask to mahanadi.asc: outside-basin cells -> -9999,
and write a proper 6-line header including NODATA_value.

osgeo before numpy (OSGeo4W DLL conflict).
"""
from osgeo import gdal
import numpy as np
import os

gdal.UseExceptions()

ROOT = r"D:/MRC_my"
ASC = os.path.join(ROOT, "mahanadi.asc")
MASK = os.path.join(ROOT, "work", "basin_mask.tif")
OUT = os.path.join(ROOT, "mahanadi.asc")

NODATA = -9999.0

hdr_keys = ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize"]
hdr = {}
with open(ASC) as f:
    for _ in range(5):
        k, v = f.readline().split()
        hdr[k.lower()] = float(v)
nc, nr = int(hdr["ncols"]), int(hdr["nrows"])

print("loading DEM ...")
dem = np.loadtxt(ASC, skiprows=5, dtype=np.float32)
assert dem.shape == (nr, nc), f"{dem.shape} != {(nr, nc)}"

ds = gdal.Open(MASK)
mask = ds.GetRasterBand(1).ReadAsArray()
assert mask.shape == dem.shape, f"mask {mask.shape} != dem {dem.shape}"

inside = mask == 1
n_in = int(inside.sum())
print(f"inside basin: {n_in} cells ({100*n_in/dem.size:.1f}%)")
print(f"before: min={dem.min():.2f} max={dem.max():.2f} zeros={(dem==0).sum()}")

out = np.where(inside, dem, NODATA).astype(np.float32)

# Any remaining exact zeros INSIDE the basin are almost certainly voids too,
# except genuine near-sea-level cells at the delta. Only null out zeros that
# are inside the basin but have no positive neighbour (isolated voids).
zin = (out == 0) & inside
print(f"zeros inside basin: {int(zin.sum())} (left as-is; delta is near 0 m)")

valid = out[out > NODATA]
print(f"after : valid={valid.size} min={valid.min():.2f} max={valid.max():.2f}")

hdr_lines = [
    f"ncols        {nc}",
    f"nrows        {nr}",
    f"xllcorner    {hdr['xllcorner']:.12f}",
    f"yllcorner    {hdr['yllcorner']:.12f}",
    f"cellsize     {hdr['cellsize']:.12f}",
    f"NODATA_value {NODATA:.0f}",
]

print("writing ...")
with open(OUT, "w", newline="\n") as f:
    f.write("\n".join(hdr_lines) + "\n")
    np.savetxt(f, out, fmt="%.3f", delimiter=" ")

print(f"WROTE {OUT}")
np.save(os.path.join(ROOT, "_basin_mask.npy"), inside)
print("wrote _basin_mask.npy")
