import csv
import os
from urllib.parse import quote
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsLayoutExporter, QgsLayoutItemMap,
    QgsLayoutItemLabel, QgsLayoutItemLegend, QgsColorRampShader,
    QgsRasterShader, QgsSingleBandPseudoColorRenderer
)
from qgis.PyQt.QtGui import QColor

# ============================================================
# CONFIG
# ============================================================
CSV_PATH    = r"C:/Users/user/Downloads/GEE_TileURLs_2017_2025.csv"
OUTPUT_DIR  = r"C:/Users/user/Videos/Wami_Index_Outputs"

LAYOUT_NAME = "Standard A4 Landscape Wami_Project_Final"
DEM_NAME    = "Wami_Ruvu_Basin_DEM"
BASIN_NAME  = "Wami_Ruvu_Basin"

MAP_ITEM_ID    = "Map"
TITLE_ITEM_ID  = "Title Top"

DPI  = 300
ZMAX = 20
ZMIN = 0
# ============================================================

os.makedirs(OUTPUT_DIR, exist_ok=True)
project = QgsProject.instance()

# ---------------- AWEI LEGEND SCHEME ----------------
# 7-class brown -> teal ramp (dry -> wet)
AWEI_SCHEME = [
    ("#8c510a", "Very dry (< -2)"),
    ("#d8b365", "Dry (-2 to -1)"),
    ("#f6e8c3", "Slightly dry (-1 to 0)"),
    ("#c7eae5", "Moist (0 to 0.5)"),
    ("#5ab4ac", "Wet (0.5 to 1)"),
    ("#01665e", "Flooded (1 to 2)"),
    ("#003c30", "Permanent water (> 2)"),
]

# ---------------- DEM RECLASSIFICATION ----------------
def restyle_dem_awei(dem_layer):
    stats = dem_layer.dataProvider().bandStatistics(1)
    dem_min, dem_max = stats.minimumValue, stats.maximumValue

    n = len(AWEI_SCHEME)
    items = []
    for i, (hex_color, label) in enumerate(AWEI_SCHEME):
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
    """
    Manually populate each legend in the layout with the given layers.
    """
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
def export_one(year, layer_name, url, dem, basin, layout):
    safe_name = f"{year}_{layer_name}"
    print(f"Processing: {safe_name}")

    xyz = make_xyz_layer(safe_name, url)
    if xyz is None:
        print(f"  ! Invalid XYZ layer")
        return

    project.addMapLayer(xyz, False)

    # Restyle DEM with AWEI brown->teal ramp (used for legend swatches only)
    restyle_dem_awei(dem)

    # Rename DEM so the legend title reads "AWEI"
    original_dem_name = dem.name()
    dem.setName("AWEI")

    # Map item
    map_item = layout.itemById(MAP_ITEM_ID)
    if not isinstance(map_item, QgsLayoutItemMap):
        print(f"  ! Map item '{MAP_ITEM_ID}' not found")
        dem.setName(original_dem_name)
        project.removeMapLayer(xyz.id())
        return

    # DEM NOT drawn on map — only basin + XYZ tiles
    map_item.setKeepLayerSet(True)
    map_item.setLayers([basin, xyz])

    extent = basin.extent()
    extent.scale(1.05)
    map_item.zoomToExtent(extent)
    map_item.refresh()

    # Title
    title_item = layout.itemById(TITLE_ITEM_ID)
    if isinstance(title_item, QgsLayoutItemLabel):
        title_item.setText(f"Wami-Ruvu Basin — AWEI ({year})")
        title_item.refresh()

    # Legend: AWEI classification swatches + basin
    rebuild_legend(layout, [dem, basin])

    # Export
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
    basin  = find_layer_by_name(BASIN_NAME)
    layout = find_layout(LAYOUT_NAME)
    print(f"  DEM:    {dem.name()}")
    print(f"  Basin:  {basin.name()}")
    print(f"  Layout: {layout.name()}\n")

    print(f"Reading CSV: {CSV_PATH}")
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['layer'].strip().upper() == "AWEI":
                rows.append(row)
    rows.sort(key=lambda r: r['year'])
    print(f"Found {len(rows)} AWEI maps.\n")

    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}]", end=" ")
        try:
            export_one(row['year'], row['layer'], row['url'], dem, basin, layout)
        except Exception as e:
            print(f"  ! Error: {e}")

    print(f"\nDone. Output: {OUTPUT_DIR}")

main()
