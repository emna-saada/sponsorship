"""Step 1: export cloud-free Sentinel-2 median composites for 2018 and 2025.

For each year this script:
  1. builds a Cloud Score+ masked median composite over the AOI,
  2. saves true-colour and false-colour PNG quicklooks plus a 2x2 comparison
     figure to data/outputs/quicklooks/,
  3. writes the scene counts and clear-observation stats to
     data/outputs/s2_composites_metadata.json,
  4. starts a full-resolution (10 m) GeoTIFF export to Google Drive, and/or
     downloads it locally with --local.

Usage:
    python src/export_s2_composites.py --project my-gee-project
    python src/export_s2_composites.py --project my-gee-project --aoi sefwi --local
"""

import argparse
import json
from pathlib import Path

import ee
import matplotlib.pyplot as plt
import requests

from eudr_checker.config import AOIS, EPOCHS, OUTPUT_DIR, AOI_DIR
from eudr_checker.ee_utils import aoi_geometry, initialize, write_aoi_geojson
from eudr_checker.sentinel2 import Composite, median_composite

# Quicklook band combinations and gamma. Min/max come from a per-band 2-98 %
# stretch over the AOI: a fixed stretch leaves the hazy L1C 2018 composite
# blue-grey because it has no atmospheric correction.
VIS = {
    "true_color": {"bands": ["B4", "B3", "B2"], "gamma": 1.2},
    # SWIR1 / NIR / Red: closed forest dark green, cocoa and fallow brighter
    # yellow-green, bare soil and settlements pink-magenta, water dark blue.
    "false_color": {"bands": ["B11", "B8", "B4"], "gamma": 1.0},
}


def percentile_stretch(image: ee.Image, region: ee.Geometry, bands: list[str]) -> dict:
    p = image.select(bands).reduceRegion(
        reducer=ee.Reducer.percentile([2, 98]), geometry=region, scale=60,
        maxPixels=1e9, bestEffort=True,
    ).getInfo()
    return {"min": [p[f"{b}_p2"] for b in bands], "max": [p[f"{b}_p98"] for b in bands]}


def save_quicklook(image: ee.Image, region: ee.Geometry, vis: dict, path: Path,
                   dimensions: int) -> None:
    vis = {**vis, **percentile_stretch(image, region, vis["bands"])}
    url = image.visualize(**vis).getThumbURL(
        {"region": region, "dimensions": dimensions, "format": "png"}
    )
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    path.write_bytes(resp.content)


def clear_obs_stats(image: ee.Image, region: ee.Geometry) -> dict:
    stats = image.select("clear_obs").reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True)
        .combine(ee.Reducer.percentile([5]), sharedInputs=True),
        geometry=region,
        scale=100,
        maxPixels=1e9,
    ).getInfo()
    return {k.replace("clear_obs_", ""): v for k, v in stats.items()}


def comparison_figure(paths: dict, meta: dict, label: str, out: Path) -> None:
    years = sorted(paths)
    fig, axes = plt.subplots(len(years), 2, figsize=(12, 6 * len(years)))
    for row, year in enumerate(years):
        m = meta[str(year)]
        for col, kind in enumerate(["true_color", "false_color"]):
            ax = axes[row][col]
            ax.imshow(plt.imread(paths[year][kind]))
            ax.set_title(
                f"{year} {kind.replace('_', ' ')} ({m['product_level']}, "
                f"{m['n_scenes']} scenes, ~{m['clear_obs']['mean']:.0f} clear obs/px)",
                fontsize=10,
            )
            ax.axis("off")
    fig.suptitle(f"Sentinel-2 median composites, {label}", fontsize=13)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


def export_to_drive(comp: Composite, region: ee.Geometry, crs: str, name: str,
                    folder: str) -> ee.batch.Task:
    task = ee.batch.Export.image.toDrive(
        image=comp.image,
        description=name,
        folder=folder,
        fileNamePrefix=name,
        region=region,
        scale=10,
        crs=crs,
        maxPixels=1e10,
        fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    return task


def download_local(comp: Composite, region: ee.Geometry, crs: str, path: Path) -> None:
    import geemap  # imported lazily: heavy, and only needed for this path

    geemap.download_ee_image(comp.image, str(path), region=region, crs=crs,
                             scale=10, dtype="uint16")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", help="Earth Engine Cloud project (or set EE_PROJECT)")
    p.add_argument("--aoi", default="soubre", choices=sorted(AOIS))
    p.add_argument("--years", type=int, nargs="+", default=sorted(EPOCHS), choices=sorted(EPOCHS))
    p.add_argument("--cs-threshold", type=float, default=0.6,
                   help="Cloud Score+ cs_cdf threshold; higher = stricter (default 0.6)")
    p.add_argument("--max-scene-cloud", type=float, default=70,
                   help="Drop scenes above this CLOUDY_PIXEL_PERCENTAGE (default 70)")
    p.add_argument("--thumb-size", type=int, default=1600, help="Quicklook size in px")
    p.add_argument("--drive-folder", default="eudr_plot_checker")
    p.add_argument("--no-drive", action="store_true", help="Skip the Google Drive export")
    p.add_argument("--local", action="store_true",
                   help="Also download the 10 m GeoTIFF to data/raw/ (needs geedim)")
    args = p.parse_args()

    initialize(args.project)
    aoi = AOIS[args.aoi]
    region = aoi_geometry(aoi)
    print(f"AOI: {aoi.label} {aoi.bbox}")
    print(f"  saved to {write_aoi_geojson(aoi, AOI_DIR)}")

    quick_dir = OUTPUT_DIR / "quicklooks"
    quick_dir.mkdir(parents=True, exist_ok=True)
    meta_path = OUTPUT_DIR / "s2_composites_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    meta_aoi = meta.setdefault(aoi.name, {"label": aoi.label, "bbox": aoi.bbox, "crs": aoi.crs})
    quicklooks = {}

    for year in args.years:
        print(f"\n== {year} ==")
        comp = median_composite(region, EPOCHS[year], cs_threshold=args.cs_threshold,
                                max_scene_cloud=args.max_scene_cloud)
        print(f"  {comp.product_level} from {comp.collection_id}: {comp.n_scenes} scenes")

        stats = clear_obs_stats(comp.image, region)
        print(f"  clear observations per pixel: mean {stats['mean']:.1f}, "
              f"p5 {stats['p5']}, min {stats['min']}")

        name = f"s2_median_{aoi.name}_{year}"
        quicklooks[year] = {}
        for kind, vis in VIS.items():
            path = quick_dir / f"{name}_{kind}.png"
            save_quicklook(comp.image, region, vis, path, args.thumb_size)
            quicklooks[year][kind] = path
            print(f"  quicklook -> {path.relative_to(OUTPUT_DIR.parent.parent)}")

        entry = {
            "product_level": comp.product_level,
            "collection": comp.collection_id,
            "date_range": [EPOCHS[year].start, EPOCHS[year].end],
            "n_scenes": comp.n_scenes,
            "cs_threshold": args.cs_threshold,
            "max_scene_cloud": args.max_scene_cloud,
            "clear_obs": stats,
        }

        if not args.no_drive:
            task = export_to_drive(comp, region, aoi.crs, name, args.drive_folder)
            entry["drive_task_id"] = task.id
            print(f"  Drive export started: task {task.id} -> {args.drive_folder}/{name}.tif")
        if args.local:
            tif = OUTPUT_DIR.parent / "raw" / f"{name}.tif"
            download_local(comp, region, aoi.crs, tif)
            print(f"  local GeoTIFF -> {tif}")

        meta_aoi[str(year)] = entry

    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"\nmetadata -> {meta_path}")

    if len(quicklooks) > 1:
        fig_path = quick_dir / f"s2_median_{aoi.name}_comparison.png"
        comparison_figure(quicklooks, meta_aoi, aoi.label, fig_path)
        print(f"comparison figure -> {fig_path}")

    if not args.no_drive:
        print("\nTrack Drive exports at https://code.earthengine.google.com/tasks")


if __name__ == "__main__":
    main()
