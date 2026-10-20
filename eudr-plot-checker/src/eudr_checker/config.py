"""Project-wide constants: study areas, epochs, dataset IDs, paths."""

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
AOI_DIR = DATA_DIR / "aoi"
OUTPUT_DIR = DATA_DIR / "outputs"

# EUDR Article 2(13): the deforestation cut-off date.
EUDR_CUTOFF = "2020-12-31"

# --- Earth Engine datasets ---------------------------------------------------
S2_SR = "COPERNICUS/S2_SR_HARMONIZED"          # Level-2A surface reflectance
S2_TOA = "COPERNICUS/S2_HARMONIZED"            # Level-1C top-of-atmosphere
CLOUD_SCORE_PLUS = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
JRC_GFC2020 = "JRC/GFC2020/V4"
DYNAMIC_WORLD = "GOOGLE/DYNAMICWORLD/V1"
HANSEN_GFC = "UMD/hansen/global_forest_change_2024_v1_12"

# 10 m bands plus the two 20 m SWIR bands (resampled to 10 m on export).
# SWIR separates closed forest from cocoa agroforestry better than RGB alone.
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]


@dataclass(frozen=True)
class AOI:
    name: str
    label: str
    bbox: tuple[float, float, float, float]  # (west, south, east, north), WGS84
    crs: str                                  # UTM zone used for exports
    why: str


AOIS = {
    "soubre": AOI(
        name="soubre",
        label="Soubré, Nawa region, Côte d'Ivoire",
        bbox=(-6.76, 5.63, -6.33, 5.94),
        crs="EPSG:32629",  # UTM 29N (-12° to -6°)
        why=(
            "Nawa is Côte d'Ivoire's largest cocoa-producing region and Soubré "
            "its main hub. The area lies between Taï National Park and the "
            "Sassandra river, a frontier where forest was converted to cocoa, "
            "and it includes the Soubré dam reservoir (filled 2017), a clear "
            "landmark for checking the composites. The eastern edge takes in a "
            "block plantation, so the sample covers estate as well as "
            "smallholder land use."
        ),
    ),
    "sefwi": AOI(
        name="sefwi",
        label="Sefwi Wiawso, Western North region, Ghana",
        bbox=(-2.65, 6.05, -2.35, 6.35),
        crs="EPSG:32630",  # UTM 30N (-6° to 0°)
        why=(
            "Western North is Ghana's leading cocoa region, with forest "
            "reserves next to smallholder cocoa farms."
        ),
    ),
}


@dataclass(frozen=True)
class Epoch:
    year: int
    start: str
    end: str  # exclusive


EPOCHS = {
    2018: Epoch(2018, "2018-01-01", "2019-01-01"),
    2025: Epoch(2025, "2025-01-01", "2026-01-01"),
}
