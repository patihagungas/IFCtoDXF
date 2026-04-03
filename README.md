# IFCReader — IFC to DXF Converter

A desktop application for converting IFC (Industry Foundation Classes) building models into DXF (Drawing Exchange Format) files, with a built-in 3D preview and element inspector.

## What It Does

- **Scans IFC files** and lists all building elements (structural, architectural, MEP, etc.) in a searchable table with metadata: Tag/Mark, Name, IFC Class, Type, and Properties
- **3D Preview** — view any selected element in an embedded viewer with Shaded, Wireframe, and Shaded+Edges render modes; supports rotate, pan, and zoom
- **Converts to DXF** — exports selected elements as individual `.dxf` files, one per element named after its Tag/Mark value
- **Assembly decomposition** — `IfcElementAssembly` objects (trusses, frames, panels) are walked recursively and merged into a single DXF block
- **AutoCAD-ready output** — uses POLYFACE MESH with invisible-edge flags (negative vertex indices) to eliminate phantom diagonal lines; ACI color per IFC class; automatic unit scaling to mm

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

Download the pre-built installer (`IFC2DXF_Setup_v1.0.0.exe`) from the Releases page and run it. No Python installation required. The installer does not require administrator rights.

### Option 3 — Build the installer yourself

1. Complete steps 1–3 from Option 1.

2. Build the standalone executable with PyInstaller:
   ```bash
   pyinstaller ifc2dxf.spec
   ```
   Output is placed in `dist\IFC2DXF\`.

3. Open `installer.iss` in [Inno Setup Compiler](https://jrsoftware.org/isinfo.php) and press `Ctrl+F9` to compile. The installer will be generated at `Output\IFC2DXF_Setup_v1.0.0.exe`.

## Usage

1. Launch the app (`python main.py` or the installed `.exe`).
2. Click **Open IFC File** and select your `.ifc` file.
3. The table populates with all detected elements. Use the search bar to filter by name, tag, or class.
4. Select an element and click **Preview** to view it in 3D.
5. Check the elements you want to export, choose an output folder, and click **Convert to DXF**.
6. One `.dxf` file per element is written to the chosen folder, named after each element's Tag/Mark value.

## Dependencies

| Package | Purpose |
|---|---|
| `ifcopenshell` | IFC parsing and geometry kernel |
| `ezdxf >= 1.1.0` | DXF read/write |
| `customtkinter >= 5.2.0` | Modern dark-themed UI framework |
| `pyinstaller >= 6.0` | Build standalone executable (dev only) |

## Project Structure

```
IFCreader/
├── main.py               # Entry point
├── gui.py                # Desktop UI and 3D preview window
├── converter_engine.py   # IFC parsing and DXF conversion logic
├── requirements.txt      # Python dependencies
├── ifc2dxf.spec          # PyInstaller build configuration
└── installer.iss         # Inno Setup Windows installer script
```
