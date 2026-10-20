# EUDR Plot Checker

Deforestation-compliance screening for farm plots under the EU Deforestation
Regulation (EU 2023/1115). Cocoa, coffee and palm oil placed on the EU market
must come from land that was not deforested after the **31 December 2020**
cut-off date. This project checks plot polygons against satellite evidence
and gives each plot a risk flag.

## Pipeline (planned)

| Step | What | Data |
|---|---|---|
| 1 ✅ | Cloud-free Sentinel-2 median composites, 2018 and 2025 | Sentinel-2 L2A/L1C + Cloud Score+ |
| 2 | ~50 sample cocoa plot polygons (GeoJSON) | drawn on the composites |
| 3 | Forest cover in each plot at 2020 | JRC Global Forest Cover 2020 V4 |
| 4 | Forest loss after 2020 | Sentinel-2 NDVI time series, Dynamic World, Hansen GFC as a cross-check |
| 5 | Risk flag: compliant / at risk / non-compliant | rules on steps 3–4 |
| 6 | Per-plot evidence page with before/after images | app/ |
| 7 | Plain-language explanations citing the regulation (optional) | RAG over the EUDR text |

## Study area

**Soubré, Nawa region, Côte d'Ivoire** (`bbox -6.76, 5.63, -6.33, 5.94`, about 47 × 34 km).
Nawa is the country's largest cocoa-producing region, and Soubré is its
main hub. The area lies between Taï National Park and the Sassandra river.
Forest was converted to cocoa here over the past decades, so it's a good place
to look for both compliant and non-compliant plots. The Soubré
hydro-dam reservoir (filled in 2017) is an easy landmark for checking
georeferencing. The eastern edge takes in a block plantation, so the sample covers estate as well as smallholder land use. A Ghanaian alternative (Sefwi Wiawso, Western North) is
available with `--aoi sefwi`. AOIs are defined in `src/eudr_checker/config.py`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
earthengine authenticate          # once; or the script opens the auth flow
export EE_PROJECT=your-gee-cloud-project
```

You need a Google Cloud project registered for Earth Engine
(https://code.earthengine.google.com/register).

## Step 1: Sentinel-2 composites

```bash
python src/export_s2_composites.py                 # Soubré, 2018 + 2025
python src/export_s2_composites.py --local         # also download the GeoTIFFs to data/raw/
python src/export_s2_composites.py --aoi sefwi --no-drive
```

The same step as a Code Editor script, with a 2018/2025 swipe view: `src/gee_editor/s2_composites.js`.

Outputs:

- `data/aoi/<aoi>_aoi.geojson`: the study-area rectangle
- `data/outputs/quicklooks/s2_median_<aoi>_<year>_{true,false}_color.png`
- `data/outputs/quicklooks/s2_median_<aoi>_comparison.png`: 2×2 before/after figure
- `data/outputs/s2_composites_metadata.json`: product level, scene counts, clear-observation stats
- Google Drive `eudr_plot_checker/s2_median_<aoi>_<year>.tif`: 10 m Cloud-Optimised GeoTIFF,
  bands `B2 B3 B4 B8 B11 B12` (reflectance × 10 000, uint16) plus `clear_obs`
  (number of clear observations behind each pixel)

Method notes:

- **Cloud masking** uses Cloud Score+ (`cs_cdf ≥ 0.6`) per pixel, then takes a per-band median.
  Scenes over 70 % cloudy are dropped first. Côte d'Ivoire is cloudy for most of the year, so
  check `clear_obs` before trusting any pixel. `p5` in the metadata is the 5th percentile across the AOI.
- **2018 uses Level-1C (TOA).** In Earth Engine, Sentinel-2 Level-2A surface reflectance only covers
  West Africa from about December 2018. The script falls back to L1C when there are fewer than
  10 L2A scenes and records which level it used. That's fine for visual context, but the
  quantitative NDVI analysis in step 4 will use L2A from 2019 onward, which covers the 2020
  cut-off.
- **Quicklooks use a per-band 2–98 % stretch** over the AOI, so the hazy L1C 2018 composite and the
  L2A 2025 composite both display with balanced colours. Don't compare brightness between the two
  quicklooks; use the GeoTIFFs for anything quantitative.
- The `HARMONIZED` collections remove the +1000 DN offset that ESA added in January 2022, so 2018 and
  2025 values are on the same scale.

## Layout

```
data/       aoi/, raw/ (GeoTIFFs, not in git), outputs/ (quicklooks, metadata)
src/        eudr_checker/ package + step scripts
notebooks/  exploration
app/        evidence-page viewer
```
