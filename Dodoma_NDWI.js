// ══════════════════════════════════════════════════════════════════
// NDWI Classified · Dodoma Urban · Apr 2024, May 2024, Jun 2024
// Sentinel-2 SR · Blue palette · Exportable to Drive & Asset
// RGB export uses .visualize() so QGIS shows identical colours to GEE
// Classes:
//   Water           :  0.2 to  1.0  → #042C53 (deep blue)
//   Floods          :  0.0 to  0.2  → #185FA5 (mid-dark blue)
//   Moderate Drought: -0.3 to  0.0  → #378ADD (medium blue)
//   High Drought    : -1.0 to -0.3  → #B5D4F4 (light blue)
// ══════════════════════════════════════════════════════════════════

// ── 1. Area of Interest ───────────────────────────────────────────
Map.centerObject(dodoma, 12);

// ── 2. Export settings (edit before running) ──────────────────────
var EXPORT_FOLDER   = 'GEE_Exports';
var EXPORT_SCALE    = 10;
var EXPORT_CRS      = 'EPSG:32736';
var ASSET_FOLDER    = 'projects/YOUR_PROJECT/assets/NDWI_Dodoma';

// RGB stretch — MUST match rgbVis below for QGIS parity
var RGB_MIN = 0;
var RGB_MAX = 0.3;

// ── 3. Cloud-mask function (SCL band) ─────────────────────────────
function maskClouds(img) {
  var scl = img.select('SCL');
  var mask = scl.neq(3)
               .and(scl.neq(8))
               .and(scl.neq(9))
               .and(scl.neq(10));
  return img.select(['B2','B3','B4','B8','B11'])
            .updateMask(mask)
            .divide(10000)
            .copyProperties(img, ['system:time_start']);
}

// ── 4. NDWI classification function ───────────────────────────────
function classifyNDWI(ndwi) {
  var c1 = ndwi.lt(-0.3).multiply(1);
  var c2 = ndwi.gte(-0.3).and(ndwi.lt(0.0)).multiply(2);
  var c3 = ndwi.gte(0.0).and(ndwi.lt(0.2)).multiply(3);
  var c4 = ndwi.gte(0.2).multiply(4);
  return c1.add(c2).add(c3).add(c4)
    .rename('NDWI_Class')
    .toByte();
}

// ── 5. Process one month ──────────────────────────────────────────
function processMonth(startDate, endDate, label) {
  var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(dodoma)
    .filterDate(startDate, endDate)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
    .map(maskClouds);

  print(label + ' — image count:', s2.size());

  var composite = s2.median().clip(dodoma);

  var ndwi = composite.normalizedDifference(['B3', 'B8'])
    .rename('NDWI')
    .toFloat();

  var classified = classifyNDWI(ndwi);

  ndwi       = ndwi.set('month', label).set('source', 'S2_SR');
  classified = classified.set('month', label).set('source', 'S2_SR');

  return {
    ndwi: ndwi,
    classified: classified,
    composite: composite,
    label: label
  };
}

// ── 6. Run all three months ───────────────────────────────────────
var apr = processMonth('2024-04-01', '2024-04-30', 'Apr2024');
var may = processMonth('2024-05-01', '2024-05-31', 'May2024');
var jun = processMonth('2024-06-01', '2024-06-30', 'Jun2024');

var months = [apr, may, jun];

// ── 7. Visualisation palettes ─────────────────────────────────────
var classVis = {
  min: 1, max: 4,
  palette: ['#B5D4F4', '#378ADD', '#185FA5', '#042C53']
};

var ndwiRawVis = {
  min: -1, max: 1,
  palette: ['#B5D4F4','#85B7EB','#378ADD','#185FA5','#0C447C','#042C53']
};

var rgbVis = {bands: ['B4','B3','B2'], min: RGB_MIN, max: RGB_MAX};

// ── 8. Add layers to map ──────────────────────────────────────────
months.forEach(function(m) {
  Map.addLayer(m.classified, classVis, 'NDWI Classified ' + m.label);
  Map.addLayer(m.ndwi, ndwiRawVis, 'NDWI Raw ' + m.label, false);
  Map.addLayer(m.composite, rgbVis, 'RGB ' + m.label, false);
});

// ── 9. Area per class per month ───────────────────────────────────
var classNames = {
  '1': 'High Drought     (< -0.3)',
  '2': 'Moderate Drought (-0.3 to 0.0)',
  '3': 'Floods           ( 0.0 to 0.2)',
  '4': 'Water            ( 0.2 to 1.0)'
};

months.forEach(function(m) {
  print('── Area stats (m²): ' + m.label + ' ──');
  [1, 2, 3, 4].forEach(function(cls) {
    var area = m.classified.eq(cls)
      .multiply(ee.Image.pixelArea())
      .reduceRegion({
        reducer: ee.Reducer.sum(),
        geometry: dodoma,
        scale: EXPORT_SCALE,
        maxPixels: 1e9
      });
    print(classNames[String(cls)], area);
  });
});

// ── 10. EXPORT — Google Drive (GeoTIFF) ───────────────────────────

// Classified maps (1-band byte)
months.forEach(function(m) {
  Export.image.toDrive({
    image: m.classified,
    description: 'NDWI_Classified_' + m.label,
    folder: EXPORT_FOLDER,
    fileNamePrefix: 'NDWI_Classified_Dodoma_' + m.label,
    region: dodoma,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e9,
    fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true}
  });
});

// Continuous NDWI (float32, for analysis)
months.forEach(function(m) {
  Export.image.toDrive({
    image: m.ndwi,
    description: 'NDWI_Raw_' + m.label,
    folder: EXPORT_FOLDER,
    fileNamePrefix: 'NDWI_Raw_Dodoma_' + m.label,
    region: dodoma,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e9,
    fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true}
  });
});

// RGB composites — baked with .visualize() so QGIS matches GEE exactly
// Output: 3-band 8-bit (Byte) GeoTIFF, values 0–255, stretch already applied
months.forEach(function(m) {
  var rgbExport = m.composite.visualize({
    bands: ['B4', 'B3', 'B2'],
    min: RGB_MIN,
    max: RGB_MAX
  });

  Export.image.toDrive({
    image: rgbExport,
    description: 'RGB_Composite_' + m.label,
    folder: EXPORT_FOLDER,
    fileNamePrefix: 'RGB_Dodoma_' + m.label,
    region: dodoma,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e9,
    fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true}
  });
});

// ── 11. EXPORT — GEE Asset ───────────────────────────────────────
months.forEach(function(m) {
  Export.image.toAsset({
    image: m.classified,
    description: 'Asset_NDWI_Classified_' + m.label,
    assetId: ASSET_FOLDER + '/NDWI_Classified_' + m.label,
    region: dodoma,
    scale: EXPORT_SCALE,
    crs: EXPORT_CRS,
    maxPixels: 1e9
  });
});

// ── 12. Water change: June vs April ──────────────────────────────
var gainedWater = jun.classified.eq(4)
  .and(apr.classified.neq(4)).selfMask();
var lostWater   = apr.classified.eq(4)
  .and(jun.classified.neq(4)).selfMask();

Map.addLayer(gainedWater, {palette:['#042C53']}, 'Water Gained Apr→Jun', false);
Map.addLayer(lostWater,   {palette:['#B5D4F4']}, 'Water Lost Apr→Jun',   false);

// ── 13. Legend (Console) ──────────────────────────────────────────
print('── NDWI Class Legend ──');
print('Class 1 | #B5D4F4 | High Drought     | NDWI < -0.3');
print('Class 2 | #378ADD | Moderate Drought | -0.3 to 0.0');
print('Class 3 | #185FA5 | Floods           |  0.0 to 0.2');
print('Class 4 | #042C53 | Water            |  0.2 to 1.0');
print('Exports queued — open Tasks tab and click Run on each task');
print('RGB stretch baked at min=' + RGB_MIN + ', max=' + RGB_MAX +
      ' → load in QGIS with "No enhancement"');
