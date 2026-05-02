# Path IFC to DXF

A desktop application for converting IFC (Industry Foundation Classes) building models into DXF (Drawing Exchange Format) files, with a built-in 3D preview and element inspector.

Made by **Path**.

## What It Does

- **Scans IFC files** and lists all building elements (structural, architectural, MEP, etc.) in a searchable table with metadata: Tag/Mark, Name, IFC Class, Type, and Properties
- **Checkbox selection** — tick elements individually; checkmarks persist across search/filter changes so you can search for different tags and build up a batch without losing your selection
- **3D Preview** — view any selected element in an embedded viewer with Shaded, Wireframe, and Shaded+Edges render modes; supports rotate, pan, and zoom
- **Converts to DXF** — exports all checked elements as individual `.dxf` files, one per element named after its Tag/Mark value
- **Assembly decomposition** — `IfcElementAssembly` objects (trusses, frames, panels) are walked recursively and merged into a single DXF block per assembly
- **AutoCAD-ready output** — geometry is exported as 3DFACE entities inside a named BLOCK; feature-edge visibility flags hide smooth interior triangle edges; full ACI colour per IFC class in all visual styles (Wireframe, Hidden, Shaded, Realistic, Conceptual); geometry is centred at the origin with correct extents so the element fills the viewport on open
- **Straight/flat orientation** — each exported element is automatically rotated so its longest axis (member length) lies along the global X axis and the cross-section height is along Z, regardless of the element's orientation in the building model; for assemblies with end plates and bolts, the rotation is computed from the main structural member only so the connection hardware does not skew the axis
- **Prefix-based filenames** — output files and DXF block names use the element's Prefix (from `Pset_BeamCommon.Reference` or equivalent) when available, falling back to the Tag; e.g. `RB1001.dxf`
- **Correct scale** — coordinates are always exported in millimetres regardless of the IFC project unit declaration

## Requirements

- Python 3.9+
- Windows 64-bit (for the packaged installer; source runs cross-platform)

## Installation

### Option 1 — Run from source

1. Clone the repository:
   ```bash
   git clone https://github.com/patihagungas/IFCtoDXF.git
   cd IFCtoDXF
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate      # Windows
   # source venv/bin/activate  # macOS/Linux
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

   > **Note on ifcopenshell:** if `pip install ifcopenshell` fails on your platform, use the official conda channel or download a pre-built wheel from [IfcOpenShell Releases](https://github.com/IfcOpenShell/IfcOpenShell/releases).

4. Run the app:
   ```bash
   python main.py
   ```

### Option 2 — Windows installer

Download the pre-built installer (`IFC2DXF_Setup_v1.0.2.exe`) from the Releases page and run it. No Python installation required.

### Option 3 — Build the installer yourself

1. Complete steps 1–3 from Option 1.

2. Build the standalone executable with PyInstaller:
   ```bash
   pyinstaller ifc2dxf.spec
   ```
   Output is placed in `dist\IFC2DXF\`.

3. Install [Inno Setup 6](https://jrsoftware.org/isdl.php) and compile the installer:
   ```bash
   ISCC.exe installer.iss
   ```
   The installer will be generated at `Output\IFC2DXF_Setup_v1.0.1.exe`.

## Usage

1. Launch the app (`python main.py` or the installed `.exe`).
2. Click **Browse** next to IFC File and select your `.ifc` file — the scan runs automatically.
3. The table populates with all detected elements. Use the search bar to filter by tag, name, or IFC class.
4. **Tick the ☐ checkbox** on each row you want to export. Checkmarks survive filtering — search for more tags and keep ticking without losing previous selections.
5. Click **All** to check all currently visible rows, or **None** to uncheck them.
6. Click a row (outside the checkbox) to select it and view its full properties in the right panel.
7. With exactly one row selected, click **👁 Preview** to view the element in 3D.
8. Choose an output folder and click **▶ Convert Checked (N)**.
9. One `.dxf` file per element is written to the chosen folder, named after the element's Tag/Mark.

## DXF Output Format

| Feature | Detail |
|---|---|
| Entity type | `3DFACE` (all edges hidden) + `LINE` at feature edges |
| Block name | Element Tag/Mark |
| Edge visibility | Smooth interior edges hidden; sharp structural corners and fillet-boundary seams visible as LINE entities |
| Colour | ACI per IFC class (walls=red, columns=cyan, beams=green, …) |
| Units | Millimetres (`$INSUNITS = 4`) |
| Origin | Bounding-box centre of element geometry |
| Visual styles | Works in Wireframe, Hidden, Shaded, Realistic, Conceptual |

## ACI Colour Map

| IFC Class | AutoCAD Colour |
|---|---|
| IfcColumn | Cyan (4) |
| IfcBeam / IfcMember | Green (3) / Olive (62) |
| IfcWall | Red (1) |
| IfcSlab | Orange (30) |
| IfcDoor | Blue (5) |
| IfcWindow | Magenta (6) |
| IfcStair | Dark orange (40) |
| IfcFurnishingElement | Navy (90) |

## Dependencies

| Package | Purpose |
|---|---|
| `ifcopenshell` | IFC parsing and geometry kernel |
| `numpy` | Vertex deduplication and edge-angle computation |
| `ezdxf >= 1.1.0` | DXF read/write |
| `customtkinter >= 5.2.0` | Modern dark-themed UI framework |
| `trimesh` | Optional mesh decimation (Mesh Quality setting) |
| `pyinstaller >= 6.0` | Build standalone executable (dev only) |

## Changelog

### v1.0.2
- **Smaller DXF files** — Geometry is now exported as `3DFACE` entities with all edges hidden (for 3D shading/colour) plus separate `LINE` entities only at visible feature edges. This dramatically reduces file size vs the previous approach where every triangle edge was visible.
- **Cleaner 2D Wireframe** — Smooth interior surface edges (flat-to-flat transitions < 5°) are no longer drawn as lines. Only sharp structural corners (> 30°) and fillet-boundary seams are shown, giving a clean engineering drawing look.
- **Fillet boundary line** — A single `LINE` is drawn at the seam where a flat plate region meets a fillet/curved region (detected by checking whether each face has any smooth neighbour). This matches standard CAD representation of rolled steel sections.
- **Mesh Quality setting** — New dropdown in the GUI: Full (100%), High (70%), Medium (50%), Low (30%), Very Low (15%). Lower settings use `trimesh` quadric decimation to reduce face count and file size further.
- **Skip Fasteners / Bolts checkbox** — When checked, all `IfcFastener`, `IfcMechanicalFastener`, `IfcElementComponent`, and `IfcDiscreteAccessory` elements are skipped. Parts with a bounding-box dimension under 20 mm are also skipped as bolt-hole artefacts.
- **Vertex deduplication** — Shared vertices are now merged at 0.1 mm tolerance before edge-adjacency is computed, ensuring correct crease-angle detection even with floating-point jitter in IFC coordinates.

### v1.0.1
- **Straight/flat DXF output** — Elements are automatically rotated so the member length lies along X and the cross-section height is along Z. For assemblies, the rotation is derived from the largest part only (the main member), so end plates and bolts do not skew the axis.
- **Prefix detection** — Scans `Pset_BeamCommon.Reference` (and equivalent psets) at load time using `should_inherit=True` so type-level properties are included. The Prefix value is shown as a dedicated column in the element table.
- **Prefix-based filenames** — DXF output files and block names use the Prefix when available (e.g. `RB1001.dxf`), falling back to Tag only when no prefix is found.
- **Expanded search** — Search bar now matches against Prefix, Material, Description, and Predefined Type in addition to Tag, Name, and IFC Class.
- **Paste & Select** — New dialog lets you paste a list of marks/references (newline, comma, tab, or semicolon separated) and auto-checks all matching elements. Includes a "First match only" option to skip duplicates.
- **Copy List** — Copies all checked rows to the clipboard as TSV (Tab-Separated Values) ready to paste into Excel. Columns: Tag, Prefix, Name, IFC Class, Predefined Type, Type, Reference, Material, Description.
- **Larger checkboxes** — Row height increased from 26 to 32 px; checkbox column widened for easier clicking.
- **UI layout fix** — Paste & Select dialog buttons are now always visible regardless of window size.

### v1.0.0
- Initial release.

## Project Structure

```
IFCtoDXF/
├── main.py               # Entry point
├── gui.py                # Desktop UI, checkbox table, and 3D preview window
├── converter_engine.py   # IFC parsing, geometry extraction, and DXF export
├── requirements.txt      # Python dependencies
├── ifc2dxf.spec          # PyInstaller build configuration
├── installer.iss         # Inno Setup Windows installer script
├── P.ico                 # Application icon
├── IFC.png               # Installer sidebar image
├── wizard_banner.bmp     # Installer sidebar image (164x314)
└── wizard_logo.bmp       # Installer top-right logo (55x55)
```
