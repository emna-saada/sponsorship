// EUDR Plot Checker, step 1: cloud-free Sentinel-2 median composites, 2018 vs 2025.
// Code Editor version of src/export_s2_composites.py.
// Paste into https://code.earthengine.google.com and click Run.

// ---------------- settings ----------------
var AOI_NAME = 'soubre';  // Soubré, Nawa region, Côte d'Ivoire
var aoi = ee.Geometry.Rectangle([-6.76, 5.63, -6.45, 5.94], 'EPSG:4326', false);
var CRS = 'EPSG:32629';   // UTM 29N
// Ghana alternative (Sefwi Wiawso):
// var AOI_NAME = 'sefwi';
// var aoi = ee.Geometry.Rectangle([-2.65, 6.05, -2.35, 6.35], 'EPSG:4326', false);
// var CRS = 'EPSG:32630';

var CS_THRESHOLD = 0.6;     // Cloud Score+ cs_cdf; higher = stricter
var MAX_SCENE_CLOUD = 70;   // drop scenes above this CLOUDY_PIXEL_PERCENTAGE
var MIN_SCENES = 10;        // fewer L2A scenes than this -> fall back to L1C
var BANDS = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'];
var DRIVE_FOLDER = 'eudr_plot_checker';

var EPOCHS = [
  {year: 2018, start: '2018-01-01', end: '2019-01-01'},
  {year: 2025, start: '2025-01-01', end: '2026-01-01'}
];

var VIS_TRUE = {bands: ['B4', 'B3', 'B2'], min: 100, max: 1800, gamma: 1.2};
// NIR / SWIR1 / Red: forest deep green, cocoa/fallow lighter, bare soil pink, water black
var VIS_FALSE = {bands: ['B8', 'B11', 'B4'], min: [500, 300, 100], max: [4500, 3000, 1800]};

// ---------------- composite ----------------
var csPlus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');

function scenes(id, e) {
  return ee.ImageCollection(id)
    .filterBounds(aoi)
    .filterDate(e.start, e.end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_SCENE_CLOUD));
}

function composite(e) {
  var sr = scenes('COPERNICUS/S2_SR_HARMONIZED', e);
  var toa = scenes('COPERNICUS/S2_HARMONIZED', e);
  // L2A only covers West Africa from ~Dec 2018, so 2018 falls back to L1C (TOA).
  var useSr = sr.size().gte(MIN_SCENES);
  var col = ee.ImageCollection(ee.Algorithms.If(useSr, sr, toa));
  var level = ee.String(ee.Algorithms.If(useSr, 'L2A', 'L1C'));

  var clear = col.linkCollection(csPlus, ['cs_cdf']).map(function (img) {
    return img.select(BANDS).updateMask(img.select('cs_cdf').gte(CS_THRESHOLD));
  });
  var clearObs = clear.select('B4').count().rename('clear_obs');
  return clear.median().addBands(clearObs).toUint16().clip(aoi)
    .set({year: e.year, product_level: level, n_scenes: col.size()});
}

// ---------------- run ----------------
var left = ui.Map();
var right = ui.Map();

EPOCHS.forEach(function (e) {
  var img = composite(e);
  var name = 's2_median_' + AOI_NAME + '_' + e.year;

  print(e.year, ee.Dictionary({
    product_level: img.get('product_level'),
    n_scenes: img.get('n_scenes'),
    clear_obs: img.select('clear_obs').reduceRegion({
      reducer: ee.Reducer.mean().combine(ee.Reducer.minMax(), null, true)
        .combine(ee.Reducer.percentile([5]), null, true),
      geometry: aoi, scale: 100, maxPixels: 1e9
    })
  }));

  var map = e.year === 2018 ? left : right;
  map.addLayer(img, VIS_TRUE, e.year + ' true colour');
  map.addLayer(img, VIS_FALSE, e.year + ' false colour (NIR/SWIR/R)', false);
  map.addLayer(img.select('clear_obs'), {min: 0, max: 40, palette: ['red', 'yellow', 'green']},
               e.year + ' clear observations', false);
  map.add(ui.Label(String(e.year), {fontWeight: 'bold', fontSize: '18px'}));

  // Appear in the Tasks tab: click RUN on each to write the 10 m GeoTIFF to Drive.
  Export.image.toDrive({
    image: img, description: name, folder: DRIVE_FOLDER, fileNamePrefix: name,
    region: aoi, scale: 10, crs: CRS, maxPixels: 1e10,
    fileFormat: 'GeoTIFF', formatOptions: {cloudOptimized: true}
  });
});

// Side-by-side swipe view: 2018 on the left, 2025 on the right.
ui.Map.Linker([left, right]);
ui.root.widgets().reset([ui.SplitPanel({firstPanel: left, secondPanel: right, wipe: true})]);
left.centerObject(aoi, 12);
left.addLayer(ee.FeatureCollection([ee.Feature(aoi)]).style({color: 'white', fillColor: '00000000'}), {}, 'AOI');
