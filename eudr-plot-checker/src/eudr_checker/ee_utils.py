"""Earth Engine initialisation and small geometry helpers."""

import json
import os
from pathlib import Path

import ee

from .config import AOI


def initialize(project: str | None = None) -> None:
    """Initialise Earth Engine, running the browser auth flow if needed.

    The Cloud project comes from the argument or the EE_PROJECT env var.
    """
    project = project or os.environ.get("EE_PROJECT")
    if not project:
        raise SystemExit(
            "No Earth Engine Cloud project given. Pass --project or set EE_PROJECT."
        )
    try:
        ee.Initialize(project=project)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=project)


def aoi_geometry(aoi: AOI) -> ee.Geometry:
    return ee.Geometry.Rectangle(list(aoi.bbox), proj="EPSG:4326", geodesic=False)


def write_aoi_geojson(aoi: AOI, folder: Path) -> Path:
    """Save the AOI rectangle as GeoJSON so it can be opened in QGIS or geojson.io."""
    w, s, e, n = aoi.bbox
    feature = {
        "type": "Feature",
        "properties": {"name": aoi.name, "label": aoi.label, "why": aoi.why},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]],
        },
    }
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{aoi.name}_aoi.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}, indent=2))
    return path
