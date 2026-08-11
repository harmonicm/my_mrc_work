"""Build mahanadi.river from HydroRIVERS, sampling bed elevation from the DEM.

osgeo MUST be imported before numpy (OSGeo4W numpy 1.26 breaks the GDAL DLL load).
"""
from osgeo import ogr, osr, gdal
import numpy as np
import os

gdal.UseExceptions()
ogr.UseExceptions()

ROOT = r"D:/MRC_my"
GPKG = os.path.join(ROOT, "mahanadi_fld", "mahanadi_rivers.shp.gpkg")
ASC = os.path.join(ROOT, "mahanadi.asc")
OUT = os.path.join(ROOT, "mahanadi.river")
EPSG = 32644
STEP_CELLS = 4  # sample a cross-section every N cells


def read_asc_header(path):
    hdr = {}
    with open(path) as f:
        for _ in range(6):
            pos = f.tell()
            line = f.readline().split()
            if len(line) != 2:
                f.seek(pos)
                break
            try:
                hdr[line[0].lower()] = float(line[1])
            except ValueError:
                f.seek(pos)
                break
    return hdr


hdr = read_asc_header(ASC)
nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
cs = hdr["cellsize"]
xll, yll = hdr["xllcorner"], hdr["yllcorner"]
tlx, tly = xll, yll + nr * cs
print(f"DEM {nc}x{nr} cell={cs} TL=({tlx:.1f},{tly:.1f})")

# ---- pick the Mahanadi main stem: largest-accumulation reach network ----
ds = ogr.Open(GPKG)
lyr = ds.GetLayer(0)

src = osr.SpatialReference()
src.ImportFromEPSG(4326)
src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
dst = osr.SpatialReference()
dst.ImportFromEPSG(EPSG)
dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
tr = osr.CoordinateTransformation(src, dst)

# index reaches by id, find the outlet of the biggest MAIN_RIV group
feats = {}
for f in lyr:
    g = f.GetGeometryRef()
    if g is None:
        continue
    feats[f["HYRIV_ID"]] = {
        "next": f["NEXT_DOWN"],
        "up": f["UPLAND_SKM"] or 0.0,
        "dis": f["DIS_AV_CMS"] or 0.0,
        "main": f["MAIN_RIV"],
        "wkb": g.ExportToWkb(),
    }
print(f"reaches loaded: {len(feats)}")

# The max-upland reach IS the outlet, so walk UPSTREAM from it.
# At each junction follow the tributary with the largest upland area.
outlet = max(feats, key=lambda k: feats[k]["up"])

ups = {}
for rid, d in feats.items():
    ups.setdefault(d["next"], []).append(rid)

chain_up, cur = [outlet], outlet
while True:
    cands = ups.get(cur, [])
    if not cands:
        break
    cur = max(cands, key=lambda k: feats[k]["up"])
    chain_up.append(cur)

# reverse to get headwater -> outlet ordering
chain = chain_up[::-1]
print(f"main stem reaches: {len(chain)}  outlet upland="
      f"{feats[chain[-1]]['up']:.0f} km2  Qav={feats[chain[-1]]['dis']:.0f} m3/s")

# ---- densify into an ordered UTM polyline ----
pts = []
for rid in chain:
    g = ogr.CreateGeometryFromWkb(feats[rid]["wkb"])
    g.Transform(tr)
    for i in range(g.GetGeometryCount() or 1):
        part = g.GetGeometryRef(i) if g.GetGeometryCount() else g
        for k in range(part.GetPointCount()):
            x, y, *_ = part.GetPoint(k)
            if not pts or (x - pts[-1][0]) ** 2 + (y - pts[-1][1]) ** 2 > 1.0:
                pts.append((x, y))
print(f"densified vertices: {len(pts)}")

# keep only points inside the DEM window
pts = [(x, y) for x, y in pts
       if 0 <= (x - tlx) / cs < nc and 0 <= (tly - y) / cs < nr]
print(f"inside DEM: {len(pts)}")

# resample every STEP_CELLS cells of along-channel distance
target = STEP_CELLS * cs
keep = [pts[0]]
acc = 0.0
for a, b in zip(pts, pts[1:]):
    acc += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    if acc >= target:
        keep.append(b)
        acc = 0.0
if keep[-1] != pts[-1]:
    keep.append(pts[-1])
print(f"cross-sections: {len(keep)}")
np.save(os.path.join(ROOT, "_river_pts.npy"), np.array(keep))
print("wrote _river_pts.npy")
