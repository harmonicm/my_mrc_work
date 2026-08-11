# my_mrc_work

Mahanadi River Flood Simulation (LISFLOOD-FP)
Hydrodynamic flood model of the Mahanadi basin built on LISFLOOD-FP v5.9 (BMI build: harmonicm/lisflood-fp-bmi). Terrain from Copernicus GLO-30, channel network from HydroRIVERS v10, inflow hydrograph shape from Dartmouth Flood Observatory (DFO) satellite discharge, rescaled to the documented 1982 flood magnitude at Tikarapara.

Dynamic rainfall coupling (the end goal of the project) is not yet implemented — see Status / What's missing.

Directory layout
D:\MRC_my
├── mahanadi.asc              # DEM, 500 m, ESRI ASCII, basin-masked (NODATA outside catchment)
├── mahanadi.river             # 377-point channel cross-section file (main stem, HydroRIVERS-derived)
├── mahanadi.bdy               # Inflow hydrograph (DFO shape, rescaled to 45,000 m3/s peak)
├── mahanadi.bci               # Legacy boundary file — NOT used; BCs live in mahanadi.river (see note below)
├── mahanadi.par.txt           # LISFLOOD-FP parameter/config file
├── mahanadi.river.FREE_broken # Backup of an earlier broken outlet config, kept for reference
├── mahanadi_fld/               
│   └── mahanadi_rivers.shp.gpkg   # HydroRIVERS source vector (network topology, upstream area)
├── work/
│   └── basin_mask.tif          # Rasterized basin boundary, used to mask the DEM and check containment
├── results/
│   ├── mahanadi_out.mass       # Mass-balance log (one row per massint)
│   ├── mahanadi_out.max        # Max depth grid (whole-run summary)
│   ├── mahanadi_out.maxtm      # Time of max depth
│   ├── mahanadi_out.totaltm    # Total time flooded
│   ├── mahanadi_out.inittm     # Time water first arrived
│   └── mahanadi_out-0000..0020.wd / .elev   # Per-day depth / water-surface grids (21 timesteps)
├── checks/
│   ├── 01_basin_and_river.png       # Basin mask + channel centerline sanity plot
│   ├── 02_bed_profile.png           # Channel bed elevation profile, headwater → outlet
│   ├── flood_animation.gif          # Animated flood evolution, gamma-corrected colour scale
│   ├── flood_animation_linear.gif   # Same animation, linear colour scale (for reference)
│   └── frames/day00.png … day20.png # Individual daily stills
├── build_river.py              # Stage 1: trace main-stem channel from HydroRIVERS (topology only)
├── build_river2.py             # Stage 2: sample DEM bed elevation onto channel points, enforce monotonicity (superseded — see build_river3.py)
├── build_river3.py             # Stage 3 (current): rebuilds width + bed profile with the conveyance fix — this is the script that produced the live mahanadi.river
├── fix_dem.py                  # Applies basin mask to raw DEM, writes proper 6-line NODATA header
├── rebuild_dem.py              # Rebuilds mahanadi.asc from the gap-filled DEM mosaic
├── audit_inputs.py             # Static validator: checks every input file's keywords/format against the LISFLOOD-FP source parser rules
├── run_stats.py                # Post-run analysis: flood extent/depth stats, mass-balance check, containment check
├── make_plots.py                # Produces checks/01_basin_and_river.png and 02_bed_profile.png
├── make_animation.py           # Builds the flood evolution GIF(s) from the .wd output grids
├── flood_frequency.py          # Gumbel (EV1) flood-frequency analysis on the DFO annual-maximum series
├── dfo_2031_discharge.csv      # Raw DFO daily discharge record, 1998–2026 (input to flood_frequency.py)
├── flood_frequency_results.json # Cached numeric output of flood_frequency.py
└── PROJECT_DOCUMENTATION.md    # Full technical log — data sources, every bug found/fixed, limitations
Note on boundary conditions: mahanadi.bci exists on disk but is not read into the active configuration — LISFLOOD-FP's point-FREE boundary type is only honoured when the SGC solver is on, which this setup doesn't use. Both the inflow (QVAR, linked to mahanadi.bdy) and the outlet (FREE) boundary conditions are instead declared directly on the first and last cross-sections inside mahanadi.river. mahanadi.bci is kept only so the directory isn't missing a file the .par used to reference; it has no effect on the run.

Pipeline (how the inputs were produced)
Run in this order if rebuilding from scratch:

fix_dem.py / rebuild_dem.py — merge the gap-filled Copernicus GLO-30 mosaic (two extra strips fetched from the OpenTopography API to cover a western and northern coverage void), mask everything outside the basin to NODATA, write the corrected 6-line ESRI ASCII header → mahanadi.asc.
build_river.py — load mahanadi_rivers.shp.gpkg (HydroRIVERS), walk upstream from the outlet reach along the branch with the largest UPLAND_SKM at each junction, to get the main-stem reach chain.
build_river3.py — for each of the 377 cross-sections along that chain: sample bed elevation from mahanadi.asc, smooth and enforce a non-increasing (monotonic) downstream bed profile, assign channel width from a hydraulic-geometry relation (W ∝ Q^0.5, anchored at 60 m headwater / ~4,000 m outlet), and write mahanadi.river with the inflow QVAR tag on cross-section 0 and the outlet FREE tag on cross-section 376. (build_river2.py is the earlier version of this step that used a hard elevation clamp instead of smoothing — kept in the repo but superseded; see Bugs fixed below for why it mattered.)
Hydrograph — DFO daily discharge (dfo_2031_discharge.csv) was scanned for the best-shaped candidate flood event; the 2019-07-08 event was selected and its rise/recession pattern rescaled so the peak equals the documented 1982 flood magnitude (45,000 m³/s) → mahanadi.bdy. The file header documents this shape/magnitude split explicitly.
audit_inputs.py — run before every simulation. Statically checks every keyword in mahanadi.par.txt against the valid keyword list in the LISFLOOD-FP source (pars.cpp), confirms referenced files exist, checks comment-line/header-line counts against each file's actual parser, and checks point counts and monotonicity in mahanadi.river.
Run lisflood.exe mahanadi.par.txt (solvers: acceleration for the 2D floodplain, kinematic for the 1D channel — see notes below on why diffusive was tried and rejected).
run_stats.py — reads results/mahanadi_out.max and mahanadi_out.mass, reports flood extent by depth threshold, peak/mean depth, mass-balance error, and containment (flooded cells outside the basin mask should be zero).
make_plots.py — sanity-check figures (basin + channel overlay, bed profile).
make_animation.py — stitches the 21 daily .wd grids into flood_animation.gif, one shared colour scale across all frames (PowerNorm(gamma=0.45) so shallow floodplain depths aren't washed out next to the ~19 m Hirakud pool).
flood_frequency.py — independent of the simulation; fits a Gumbel distribution to 28 years (1998–2025) of DFO annual-maximum discharge and reports Q10/Q50/Q100, for context on where the simulated 45,000 m³/s event sits statistically.
Requirements
lisflood.exe + lisflood.dll (compiled from the BMI fork; needs g++/MSYS2 UCRT64 toolchain DLLs alongside the executable at run time)
Python (via OSGeo4W, not system Python) with osgeo.gdal, numpy, matplotlib, PIL
Import osgeo before numpy in every script — OSGeo4W's numpy build conflicts with GDAL's DLL loading otherwise. All scripts in this repo already do this; keep the order if you add new ones.
scipy (for the MLE fit in flood_frequency.py; method-of-moments and L-moments fits don't need it)
Results (most recent validated run)
20-simulated-day run (sim_time = 1,728,000 s), fixed 10 s initial timestep, acceleration + kinematic-channel solvers.

Metric	Value
Wall-clock runtime	188.6 min (≈3 h 09 min)
Peak inflow (design flood)	45,000 m³/s
Peak outflow at outlet	37,019 m³/s (≈82.3% of peak inflow)
Mass-balance error	0.0167% of final stored volume
Cells flooded outside basin mask	0 (fully contained)
Flood extent, depth ≥ 0.05 m	4,872 km² (≈3.6% of basin)
Flood extent, depth ≥ 1.00 m	4,184 km²
Flood extent, depth ≥ 5.00 m	2,106 km²
Peak simulated depth	18.75 m (Hirakud terrain pool)
Mean wet-cell depth	4.83 m
Mean arrival time / time-to-peak	≈88 h / ≈268 h
Caveat: the run ends mid-recession (outlet still passing ~35,000 m³/s at t = 1,728,000 s), so extent/depth figures are peak-of-window, not a fully drained final state. The model has not been validated against any observed flood extent or gauge record — mass conservation being clean confirms numerical correctness, not hydrological accuracy.

Flood frequency context (flood_frequency.py output)
Gumbel fit on 28 years of DFO annual maxima (raw DFO units):

Estimator	Q10	Q50	Q100
Method of moments	3,307	3,905	4,158 m³/s
L-moments	3,338	3,968	4,234 m³/s
MLE	3,567	4,373	4,714 m³/s
The simulated 45,000 m³/s event is ~10.6× the DFO-scale Q100 — a scale mismatch, not a real return period, since DFO discharge is satellite-derived and calibrated against a water-balance model (stated accuracy ±20% at best, whereas the DFO-vs-1982-gauge discrepancy here is ~12.7×). Rescaling the fit by that 12.7× ratio (an explicit, untested assumption) puts 45,000 m³/s at roughly a 16-year return period. Treat this as a rough magnitude comparison ("comparable to the 1982 flood"), not a validated return-period estimate.

Bugs found and fixed
All verified against the LISFLOOD-FP source, not assumed. Full write-up with before/after numbers is in PROJECT_DOCUMENTATION.md §5; short version:

DEM had a 5-line header (missing NODATA_value) and outside-basin cells were elevation 0, not nodata → water would sheet across the full rectangular grid. Fixed in fix_dem.py.
.par referenced rivername mahanadi.rivers (wrong keyword and wrong filename — the correct keyword is riverfile, correct file is mahanadi.river). Channel was being silently ignored.
Original .river had 2 points → straight-line channel. Rebuilt with 377 points from real HydroRIVERS geometry.
FREE outlet was declared as a .bci point ~88 km inside the domain edge — invalid placement for that boundary type. Moved onto the last .river cross-section instead.
Original hydrograph used GRDC monthly-mean data (peak 10,000 m³/s) — structurally incapable of representing a flood peak. Replaced with DFO daily event shape rescaled to 45,000 m³/s.
Channel width was fabricated too small (an early placeholder formula, 10–35× too narrow), and the monotonicity fix used a hard downstream clamp that flattened a real ~1.3×10⁻⁴ terrain slope down to an artificial 1×10⁻⁵ floor over a long reach. Combined effect: outlet could only pass ~154 m³/s of 45,000 m³/s in (0.36%) — the basin filled like a bathtub. Fixed by (a) hydraulic-geometry width formula and (b) smoothing-based monotonicity instead of a hard clamp, in build_river3.py. Outlet conveyance capacity went from ~150 m³/s to ~47,500 m³/s at design depth.
A candidate fix — switching the outlet to HFIX 1.5 (fixed tidal stage) — was checked against source before applying and found to be wrong: HFIX is a water-surface elevation, and depth = HFIX − bed elevation. With the outlet bed sitting slightly below datum at the time, this would have given ~1.6 m depth / ~84 m³/s — worse than the bug it was meant to fix. Reverted; real fix was #6.
diffusive channel solver was tried and diverges immediately on this long, low-gradient channel (Newton iteration doesn't converge — confirmed via a short probe run before committing to a full 50+ minute run). Kept kinematic channel solver + acceleration floodplain solver.
flood_frequency.py's first L-moments implementation had a factor-of-2 bug in the λ₂ formula (L-moments fit came out below method-of-moments, which shouldn't happen for Gumbel). Fixed; estimators now order correctly.
Status / What's missing
Dynamic rainfall — the actual project goal — is not implemented. All inflow currently enters through the single upstream channel boundary. This LISFLOOD-FP build's .rain keyword only supports spatially uniform rainfall (confirmed in infevap.cpp); true distributed rainfall needs the BMI interface (H, DEM, Qx, rain are exposed in lib_bmi.cpp), called via ctypes since this build is BMI 1.0, not 2.0.
Hirakud Dam exists only as DEM terrain (a flat ~190 m reservoir surface); no gate operations or release routing are modeled.
Channel width at the outlet (4,000 m) and the drainage-area profile used to scale width along the channel are estimated (hydraulic geometry), not measured from GRWL or real per-reach UPLAND_SKM — the latter is already present in the HydroRIVERS data and unused.
Tidal outlet stage is a placeholder (1.5 m), not sourced from INCOIS.
1982 peak magnitude (45,000 m³/s target) is from the project brief, not independently re-verified against a CWC primary source.
No output-format conversion has been done for whatever downstream tool consumes results/*.wd / *.elev — see the "Raw output format" note in PROJECT_DOCUMENTATION.md §6.2 for the format as-is.
ESA WorldCover 10 m land cover is downloaded but not yet used (Manning's n is currently uniform: 0.035 channel, 0.06 floodplain).
\
