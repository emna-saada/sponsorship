"""Cloud-free Sentinel-2 median composites.

Clouds are masked per pixel with Google's Cloud Score+ (cs_cdf), which is far
more reliable over humid West Africa than the QA60 band or the SCL layer.

Level-2A surface reflectance only covers West Africa from around December
2018, so a composite for 2018 would have almost no input scenes. In that case
we fall back to Level-1C top-of-atmosphere reflectance and record the product
level in the composite's metadata.
"""

from dataclasses import dataclass

import ee

from .config import CLOUD_SCORE_PLUS, S2_BANDS, S2_SR, S2_TOA, Epoch


@dataclass
class Composite:
    image: ee.Image          # S2_BANDS + clear_obs, uint16
    collection_id: str
    product_level: str       # "L2A" or "L1C"
    n_scenes: int


def _scenes(collection_id: str, region: ee.Geometry, epoch: Epoch,
            max_scene_cloud: float) -> ee.ImageCollection:
    return (
        ee.ImageCollection(collection_id)
        .filterBounds(region)
        .filterDate(epoch.start, epoch.end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_scene_cloud))
    )


def _mask_with_cloud_score(scenes: ee.ImageCollection, threshold: float) -> ee.ImageCollection:
    linked = scenes.linkCollection(ee.ImageCollection(CLOUD_SCORE_PLUS), ["cs_cdf"])

    def mask(img):
        clear = img.select("cs_cdf").gte(threshold)
        return img.select(S2_BANDS).updateMask(clear)

    return linked.map(mask)


def median_composite(region: ee.Geometry, epoch: Epoch, *, cs_threshold: float = 0.6,
                     max_scene_cloud: float = 70, min_scenes: int = 10) -> Composite:
    """Build a median composite of clear pixels for one epoch.

    Uses L2A when at least `min_scenes` scenes are available, L1C otherwise.
    Adds a `clear_obs` band counting the clear observations behind each pixel.
    """
    collection_id, level = S2_SR, "L2A"
    scenes = _scenes(S2_SR, region, epoch, max_scene_cloud)
    n_scenes = scenes.size().getInfo()
    if n_scenes < min_scenes:
        collection_id, level = S2_TOA, "L1C"
        scenes = _scenes(S2_TOA, region, epoch, max_scene_cloud)
        n_scenes = scenes.size().getInfo()
    if n_scenes == 0:
        raise RuntimeError(f"No Sentinel-2 scenes for {epoch.year} in this area.")

    clear = _mask_with_cloud_score(scenes, cs_threshold)
    clear_obs = clear.select("B4").count().rename("clear_obs")
    image = (
        clear.median()
        .addBands(clear_obs)
        .toUint16()
        .clip(region)
        .set({
            "year": epoch.year,
            "product_level": level,
            "source_collection": collection_id,
            "n_scenes": n_scenes,
            "cs_threshold": cs_threshold,
            "max_scene_cloud": max_scene_cloud,
        })
    )
    return Composite(image, collection_id, level, n_scenes)
