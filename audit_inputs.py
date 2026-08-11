"""Audit every LISFLOOD-FP input file against the actual v5.99 parser rules
extracted from the source. Reports issues only -- fixes nothing.

Parser facts this encodes (source refs in comments):
  pars.cpp        : valid keyword list, one token + one value per line
  input.cpp:LoadDEM      : 6 header lines, fscanf("%s %lf") pairs
  input.cpp:LoadRiver    : first token = npoints (unless "Tribs"), then
                           x y [w n z] [BCTYPE arg]; needs >=2 pts
  input.cpp:LoadBCVar    : skips exactly ONE comment line, then
                           name / ndata units / value time pairs
  input.cpp:LoadBCs      : bci lines N/E/S/W = edge, P/F = point
"""
import os
import re

ROOT = r"D:/MRC_my"
issues = []
notes = []


def add(sev, fname, msg):
    issues.append((sev, fname, msg))


# ---------------------------------------------------------------- par
VALID_KW = set("""DEMfile Qfile Roe Roe_slow SGCA_mode SGCa SGCbank SGCbed
SGCbfh_mode SGCcat_area SGCchan SGCchangroup SGCchanprams SGCm SGCmanningfile
SGCn SGCp SGCr SGCs SGCvoutput SGCwidth acceleration adaptoff ascheader bcifile
bdyfile binary_out binarystartfile calcarea calcmeandepth calcvolume cfl
ch_dynamic ch_start_h chainageoff checkpoint comp_out debug depthoff depththresh
dhlin diffusive dirroot dist_routing drycheckoff elevoff evaporation fpfric
gaugefile gravity hazard htol infiltration initial_tstep latlong loadcheck
manningfile massint mint_hk momentumthresh multiriverfile overpass overpassfile
porfile profiles qlimfact qloutput qoutput rainfall rainfallrouting
resettimeinit resroot riverfile routesfthresh routing routingspeed saveint
sim_time stagefile startelev startfile startq theta toutput ts_multiple tstart
voutput weirfile""".split())
# keywords that are bare flags (consume no value)
FLAGS = {"acceleration", "adaptoff", "chainageoff", "qoutput", "voutput",
         "profiles", "debug", "comp_out", "mint_hk", "toutput", "qloutput",
         "calcarea", "calcmeandepth", "calcvolume", "startq", "depthoff",
         "elevoff", "drycheckoff", "latlong", "dist_routing", "routing",
         "ch_dynamic", "resettimeinit", "loadcheck", "Roe", "Roe_slow",
         "diffusive", "hazard", "binary_out", "SGCvoutput"}

PAR = os.path.join(ROOT, "mahanadi.par.txt")
par = {}
raw = open(PAR, "rb").read()
if b"\r\n" in raw:
    add("MINOR", "par", "file has CRLF line endings; fscanf tolerates it "
        "but filenames read with %s stay clean only because values are "
        "followed by newline -- safer to use LF")
for ln, line in enumerate(open(PAR).read().split("\n"), 1):
    if not line.strip():
        continue
    tok = line.split()
    kw = tok[0]
    if kw not in VALID_KW:
        add("BLOCKER", "par", f"line {ln}: '{kw}' is NOT a valid keyword "
            f"(silently ignored by pars.cpp)")
        continue
    if kw in FLAGS:
        if len(tok) > 1:
            add("MINOR", "par", f"line {ln}: '{kw}' is a bare flag but has "
                f"extra token '{tok[1]}'")
    else:
        if len(tok) < 2:
            add("BLOCKER", "par", f"line {ln}: '{kw}' expects a value")
        else:
            par[kw] = tok[1]

for need in ("DEMfile", "sim_time", "resroot", "dirroot"):
    if need not in par and need not in FLAGS:
        add("BLOCKER", "par", f"missing required keyword '{need}'")

# referenced files must exist
for kw in ("DEMfile", "bcifile", "bdyfile", "riverfile", "manningfile",
           "startfile", "weirfile", "stagefile", "gaugefile"):
    if kw in par:
        p = os.path.join(ROOT, par[kw])
        if not os.path.exists(p):
            add("BLOCKER", "par", f"{kw} -> '{par[kw]}' DOES NOT EXIST")

# dirroot must exist (LISFLOOD does not create it)
if "dirroot" in par:
    d = os.path.join(ROOT, par["dirroot"])
    if not os.path.isdir(d):
        add("BLOCKER", "par", f"dirroot '{par['dirroot']}' directory missing")

# solver selection
if "acceleration" not in open(PAR).read().split() and \
   not any(k in par for k in ("diffusive", "Roe")):
    add("MAJOR", "par", "no solver keyword -- defaults to original "
        "Bates diffusive-ish scheme")

# ---------------------------------------------------------------- DEM
DEM = os.path.join(ROOT, par.get("DEMfile", "mahanadi.asc"))
hdr = {}
if os.path.exists(DEM):
    with open(DEM) as f:
        head = [f.readline() for _ in range(6)]
    keys = [h.split()[0].lower() if h.split() else "" for h in head]
    want = ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize",
            "nodata_value"]
    for i, (got, exp) in enumerate(zip(keys, want)):
        if got != exp:
            add("BLOCKER", "asc", f"header line {i+1} is '{got}' but "
                f"LoadDEM reads 6 pairs in order; expected '{exp}'")
    for h in head:
        p = h.split()
        if len(p) == 2:
            try:
                hdr[p[0].lower()] = float(p[1])
            except ValueError:
                pass
    if "xllcenter" in keys or "yllcenter" in keys:
        add("BLOCKER", "asc", "uses xllcenter/yllcenter; LoadDEM assumes "
            "corner origin -- half-cell offset")
else:
    add("BLOCKER", "asc", "DEM file not found")

nc = int(hdr.get("ncols", 0))
nr = int(hdr.get("nrows", 0))
cs = hdr.get("cellsize", 0)
blx = hdr.get("xllcorner", 0)
bly = hdr.get("yllcorner", 0)
tly = bly + nr * cs
brx = blx + nc * cs

# ---------------------------------------------------------------- river
RIV = os.path.join(ROOT, par.get("riverfile", "mahanadi.river"))
if os.path.exists(RIV):
    lines = [l for l in open(RIV).read().split("\n")]
    first = lines[0].split()
    if first and first[0].lower() in ("tribs",):
        add("INFO", "river", "multi-segment Tribs header present")
    else:
        try:
            npts = int(first[0])
        except (ValueError, IndexError):
            add("BLOCKER", "river", f"first token must be the point count "
                f"(or 'Tribs'); got '{lines[0][:40]}'")
            npts = -1
        body = [l for l in lines[1:] if l.strip()]
        if npts >= 0 and len(body) != npts:
            add("BLOCKER", "river", f"declares {npts} points but has "
                f"{len(body)} data rows")
        # per-row checks
        nqvar = nfree = nhfix = 0
        oob = 0
        for i, l in enumerate(body):
            t = l.split()
            if len(t) < 2:
                add("BLOCKER", "river", f"row {i}: fewer than 2 columns")
                continue
            if len(t) >= 5:
                try:
                    x, y, w, n, z = map(float, t[:5])
                except ValueError:
                    add("BLOCKER", "river", f"row {i}: non-numeric in "
                        f"first 5 columns")
                    continue
                if not (blx <= x <= brx and bly <= y <= tly):
                    oob += 1
                if w <= 0:
                    add("MAJOR", "river", f"row {i}: width {w} <= 0")
                if n <= 0 or n > 0.2:
                    add("MAJOR", "river", f"row {i}: Manning n={n} "
                        f"out of plausible range")
            if len(t) >= 6:
                bc = t[5].upper()
                if bc == "QVAR":
                    nqvar += 1
                elif bc == "FREE":
                    nfree += 1
                elif bc == "HFIX":
                    nhfix += 1
                elif bc not in ("QFIX", "HVAR", "QOUT", "TRIB", "RATE"):
                    add("BLOCKER", "river", f"row {i}: unknown BC '{t[5]}'")
                if bc in ("QVAR", "HVAR", "RATE") and len(t) < 7:
                    add("BLOCKER", "river", f"row {i}: {bc} needs a name")
        if oob:
            add("BLOCKER", "river", f"{oob} cross-sections fall outside the "
                f"DEM extent")
        if nqvar == 0:
            add("MAJOR", "river", "no QVAR/QFIX inflow declared")
        if nfree + nhfix == 0:
            add("MAJOR", "river", "no downstream BC (FREE/HFIX) declared; "
                "LoadRiver warns and defaults to FREE")
        notes.append(f"river: {len(body)} xsecs, QVAR={nqvar} "
                     f"FREE={nfree} HFIX={nhfix}")
else:
    add("BLOCKER", "river", "river file not found")

# ---------------------------------------------------------------- bdy
BDY = os.path.join(ROOT, par.get("bdyfile", "mahanadi.bdy"))
bdy_names = set()
if os.path.exists(BDY):
    txt = open(BDY).read().split("\n")
    ncomment = 0
    for l in txt:
        if l.strip().startswith("#"):
            ncomment += 1
        else:
            break
    if ncomment != 1:
        add("BLOCKER", "bdy", f"LoadBCVar skips exactly ONE leading line; "
            f"file has {ncomment} comment lines")
    rest = [l for l in txt[ncomment:] if l.strip()]
    if rest:
        name = rest[0].strip()
        bdy_names.add(name)
        parts = rest[1].split() if len(rest) > 1 else []
        if len(parts) < 2:
            add("BLOCKER", "bdy", "second line must be '<ndata> <units>'")
        else:
            try:
                ndata = int(parts[0])
            except ValueError:
                add("BLOCKER", "bdy", f"ndata '{parts[0]}' not an integer")
                ndata = -1
            units = parts[1]
            if units not in ("seconds", "hours", "days"):
                add("BLOCKER", "bdy", f"units '{units}' unrecognised; "
                    f"LoadBCVar only converts 'hours'/'days', anything "
                    f"else is treated as seconds")
            rows = [l.split() for l in rest[2:] if l.strip()]
            if ndata >= 0 and len(rows) != ndata:
                add("BLOCKER", "bdy", f"declares {ndata} rows, found "
                    f"{len(rows)}")
            ts, qs = [], []
            for r in rows:
                if len(r) != 2:
                    add("BLOCKER", "bdy", f"row '{' '.join(r)}' needs "
                        f"exactly 2 columns (value time)")
                    continue
                qs.append(float(r[0]))
                ts.append(float(r[1]))
            if ts != sorted(ts):
                add("BLOCKER", "bdy", "time column not monotonically "
                    "increasing")
            mult = {"seconds": 1, "hours": 3600, "days": 86400}.get(units, 1)
            end = ts[-1] * mult if ts else 0
            simt = float(par.get("sim_time", 0))
            if end < simt:
                add("MAJOR", "bdy", f"series ends at {end:.0f}s but "
                    f"sim_time={simt:.0f}s ({(simt-end)/3600:.1f} h short)")
            notes.append(f"bdy: name='{name}' {len(rows)} rows, "
                         f"peak={max(qs):.0f}, covers {end/86400:.1f} d")
else:
    add("BLOCKER", "bdy", "bdy file not found")

# cross-file: every QVAR/HVAR name in .river must exist in .bdy
if os.path.exists(RIV) and bdy_names:
    for l in open(RIV).read().split("\n")[1:]:
        t = l.split()
        if len(t) >= 7 and t[5].upper() in ("QVAR", "HVAR", "RATE"):
            if t[6] not in bdy_names:
                add("BLOCKER", "river/bdy", f"'{t[6]}' referenced in .river "
                    f"but not defined in .bdy")

# ---------------------------------------------------------------- bci
if "bcifile" in par:
    BCI = os.path.join(ROOT, par["bcifile"])
    if os.path.exists(BCI):
        for i, l in enumerate(open(BCI).read().split("\n")):
            if not l.strip():
                continue
            t = l.split()
            if t[0][0] not in "NESWPF":
                add("BLOCKER", "bci", f"line {i}: '{t[0]}' not a valid "
                    f"marker (N/E/S/W edge, P/F point)")
            if t[0][0] in "PF" and len(t) >= 3:
                x, y = float(t[1]), float(t[2])
                if not (blx <= x <= brx and bly <= y <= tly):
                    add("BLOCKER", "bci", f"line {i}: point ({x},{y}) "
                        f"outside DEM")
            if len(t) >= 4 and t[3].upper() == "FREE" and t[0][0] == "P":
                add("BLOCKER", "bci", f"line {i}: point-FREE is only "
                    f"honoured when SGC is ON (input.cpp:1523)")
else:
    notes.append("bci: not referenced in par (channel BCs come from .river)")

# ---------------------------------------------------------------- report
print("=" * 70)
print("LISFLOOD-FP INPUT AUDIT")
print("=" * 70)
order = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 3}
if not issues:
    print("\n  No issues found.\n")
for sev, f, m in sorted(issues, key=lambda r: order.get(r[0], 9)):
    print(f"  [{sev:<7}] {f:<10} {m}")
print()
print("-" * 70)
for n in notes:
    print("  " + n)
print(f"\n  grid: {nc} x {nr} @ {cs} m   X {blx:.0f}..{brx:.0f}  "
      f"Y {bly:.0f}..{tly:.0f}")
