import csv
import os
from urllib.parse import quote
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsLayoutExporter, QgsLayoutItemMap,
    QgsLayoutItemLabel, QgsLayoutItemLegend, QgsColorRampShader,
    QgsRasterShader, QgsSingleBandPseudoColorRenderer, QgsRectangle
)
from qgis.PyQt.QtGui import QColor

# ============================================================
# CONFIG
# ============================================================
CSV_PATH    = r"C:/Users/user/Downloads/GEE_TileURLs_2017_2025.csv"
OUTPUT_DIR  = r"C:/Users/user/Videos/Dar_Index_Outputs"

LAYOUT_NAME = "Standard A4 Landscape Wami_Project_Final"
DEM_NAME    = "Wami_Ruvu_Basin_DEM"
BASIN_NAME  = "Dar_es_salaam"

MAP_ITEM_ID    = "Map"
TITLE_ITEM_ID  = "Title Top"

DPI  = 300
ZMAX = 20
ZMIN = 0

# Fixed map extent (Dar es Salaam)
DAR_EXTENT = QgsRectangle(38.793, -7.309, 39.760, -6.474)
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
project = QgsProject.instance()

# ---------------- CLASSIFICATION SCHEMES ----------------
SCHEMES = {
    "NDVI": [
        ("#d73027", "Bare/Water (-1 to 0.1)"),
        ("#fdae61", "Sparse veg (0.1 to 0.2)"),
        ("#fee08b", "Shrub/grass (0.2 to 0.4)"),
        ("#a6d96a", "Moderate veg (0.4 to 0.6)"),
        ("#1a9850", "Dense veg (0.6 to 1.0)"),
    ],
    "NDWI": [
        ("#f7fbff", "High drought (-1 to -0.3)"),
        ("#bbdefb", "Moderate drought (-0.3 to 0)"),
        ("#42a5f5", "Floods (0 to 0.2)"),
        ("#0d47a1", "Water bodies (0.2 to 1)"),
    ],
    "MNDWI": [
        ("#f7fbff", "Dry land (-1 to -0.3)"),
        ("#bbdefb", "Moist soil (-0.3 to 0)"),
        ("#42a5f5", "Flooded (0 to 0.3)"),
        ("#0d47a1", "Permanent water (0.3 to 1)"),
    ],
    "AWEI": [
        ("#8c510a", "Very dry (< -2)"),
        ("#d8b365", "Dry (-2 to -1)"),
        ("#f6e8c3", "Slightly dry (-1 to 0)"),
        ("#c7eae5", "Moist (0 to 0.5)"),
        ("#5ab4ac", "Wet (0.5 to 1)"),
        ("#01665e", "Flooded (1 to 2)"),
        ("#003c30", "Permanent water (> 2)"),
    ],
    "TrueColor":  [("#888888", "Sentinel-2 RGB composite")],
    "FalseColor": [("#888888", "NIR-Red-Green composite")],
}

def scheme_for(layer_name):
    name = layer_name.upper()
    if "NDVI" in name:  return "NDVI"
    if "MNDWI" in name: return "MNDWI"
    if "NDWI" in name:  return "NDWI"
    if "AWEI" in name:  return "AWEI"
    if "TRUECOLOR" in name:  return "TrueColor"
    if "FALSECOLOR" in name: return "FalseColor"
    return "NDVI"

# ---------------- DEM RECLASSIFICATION ----------------
def restyle_dem(dem_layer, scheme_key):
    scheme = SCHEMES[scheme_key]
    stats = dem_layer.dataProvider().bandStatistics(1)
    dem_min, dem_max = stats.minimumValue, stats.maximumValue

    n = len(scheme)
    items = []
    for i, (hex_color, label) in enumerate(scheme):
        frac = (i + 1) / n
        value = dem_min + frac * (dem_max - dem_min)
        items.append(QgsColorRampShader.ColorRampItem(
            value, QColor(hex_color), label
        ))

    shader_fn = QgsColorRampShader()
    shader_fn.setColorRampType(QgsColorRampShader.Discrete)
    shader_fn.setColorRampItemList(items)

    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_fn)

    renderer = QgsSingleBandPseudoColorRenderer(
        dem_layer.dataProvider(), 1, shader
    )
    dem_layer.setRenderer(renderer)
    dem_layer.triggerRepaint()

# ---------------- HELPERS ----------------
def find_layer_by_name(name):
    matches = project.mapLayersByName(name)
    if not matches:
        raise RuntimeError(f"Layer not found in project: {name}")
    return matches[0]

def find_layout(name):
    lm = project.layoutManager()
    layout = lm.layoutByName(name)
    if layout is None:
        raise RuntimeError(f"Layout not found: {name}")
    return layout

def make_xyz_layer(name, url):
    encoded = quote(url, safe=':/%')
    uri = f"type=xyz&url={encoded}&zmin={ZMIN}&zmax={ZMAX}"
    layer = QgsRasterLayer(uri, name, "wms")
    return layer if layer.isValid() else None

def rebuild_legend(layout, layers_in_order):
    for item in layout.items():
        if not isinstance(item, QgsLayoutItemLegend):
            continue

        item.setAutoUpdateModel(False)
        item.setLegendFilterByMapEnabled(False)

        root = item.model().rootGroup()
        for child in list(root.children()):
            root.removeChildNode(child)

        for lyr in layers_in_order:
            node = root.addLayer(lyr)
            node.setCustomProperty("legend/title-label", lyr.name())

        item.updateLegend()
        item.refresh()

# ---------------- EXPORT ONE ----------------
def export_one(year, layer_name, url, dem, dar, layout):
    safe_name = f"{year}_{layer_name}"
    print(f"Processing: {safe_name}")

    xyz = make_xyz_layer(safe_name, url)
    if xyz is None:
        print(f"  ! Invalid XYZ layer")
        return

    project.addMapLayer(xyz, False)

    # Restyle DEM to mirror this layer's classification (for legend swatches)
    restyle_dem(dem, scheme_for(layer_name))

    # Rename DEM so legend title shows the index name
    original_dem_name = dem.name()
    dem.setName(f"{layer_name} Classification")

    map_item = layout.itemById(MAP_ITEM_ID)
    if not isinstance(map_item, QgsLayoutItemMap):
        print(f"  ! Map item '{MAP_ITEM_ID}' not found")
        dem.setName(original_dem_name)
        project.removeMapLayer(xyz.id())
        return

    # DEM not drawn — only Dar boundary + XYZ tiles
    map_item.setKeepLayerSet(True)
    map_item.setLayers([dar, xyz])

    # Fixed Dar es Salaam extent
    map_item.zoomToExtent(DAR_EXTENT)
    map_item.refresh()

    title_item = layout.itemById(TITLE_ITEM_ID)
    if isinstance(title_item, QgsLayoutItemLabel):
        title_item.setText(f"Dar es Salaam — {layer_name} ({year})")
        title_item.refresh()

    rebuild_legend(layout, [dem, dar])

    out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.png")
    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = DPI
    result = exporter.exportToImage(out_path, settings)

    if result == QgsLayoutExporter.Success:
        print(f"  OK -> {out_path}")
    else:
        print(f"  ! Export failed")

    dem.setName(original_dem_name)
    project.removeMapLayer(xyz.id())

# ---------------- MAIN ----------------
def main():
    print("Locating project items...")
    dem    = find_layer_by_name(DEM_NAME)
    dar    = find_layer_by_name(BASIN_NAME)
    layout = find_layout(LAYOUT_NAME)
    print(f"  DEM:    {dem.name()}")
    print(f"  Dar:    {dar.name()}")
    print(f"  Layout: {layout.name()}\n")

    print(f"Reading CSV: {CSV_PATH}")
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    rows.sort(key=lambda r: (r['year'], r['layer']))
    print(f"Found {len(rows)} maps.\n")

    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}]", end=" ")
        try:
            export_one(row['year'], row['layer'], row['url'], dem, dar, layout)
        except Exception as e:
            print(f"  ! Error: {e}")

    print(f"\nDone. Output: {OUTPUT_DIR}")

main()
