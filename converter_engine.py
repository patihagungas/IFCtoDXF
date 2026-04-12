"""
converter_engine.py  —  IFC → DXF Converter engine
────────────────────────────────────────────────────
Assembly fix (v4)
  • _collect_geometry_sources(): walks IfcRelAggregates to find leaf parts.
    An IfcElementAssembly (truss, frame, panel…) has NO direct geometry —
    the mesh lives in its children.  We now recurse into the decomposition
    tree and combine every leaf-part mesh into ONE BLOCK per assembly so
    the whole assembly stays a single selectable object in AutoCAD.
  • scan_ifc(): marks assemblies with a part-count badge in the table.
  • Conversion loop: tries direct geometry first; falls back to parts.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

import os
import re
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.unit
import ezdxf
from ezdxf.math import Vec3


# ─────────────────────────────────────────────────────────────────────────────
# ACI colour map  (AutoCAD Colour Index)
# ─────────────────────────────────────────────────────────────────────────────
_CLASS_COLOR: Dict[str, int] = {
    "IfcColumn":                4,    # cyan
    "IfcPile":                 24,    # dark cyan
    "IfcFooting":              34,
    "IfcBeam":                  3,    # green
    "IfcMember":               62,    # olive  (rafters, purlins, trusses…)
    "IfcPlate":                70,
    "IfcWall":                  1,    # red
    "IfcWallStandardCase":      1,
    "IfcCurtainWall":         141,
    "IfcSlab":                 30,    # orange
    "IfcRoof":                 10,
    "IfcCovering":             42,
    "IfcDoor":                  5,    # blue
    "IfcWindow":                6,    # magenta
    "IfcStair":                40,
    "IfcStairFlight":          40,
    "IfcRamp":                 50,
    "IfcRampFlight":           50,
    "IfcFlowSegment":         160,
    "IfcFlowFitting":         170,
    "IfcFlowTerminal":        180,
    "IfcFurnishingElement":    90,
    "IfcSpace":               252,
    "IfcBuildingElementProxy":  8,
}
_DEFAULT_COLOR = 7

# ACI → (R, G, B) for the in-app 3D preview renderer
ACI_TO_RGB: Dict[int, tuple] = {
    1:   (220,  50,  50),   # red       – walls
    3:   ( 60, 200,  60),   # green     – beams
    4:   ( 40, 200, 220),   # cyan      – columns
    5:   ( 60,  60, 220),   # blue      – doors
    6:   (200,  60, 200),   # magenta   – windows
    7:   (200, 200, 200),   # white/grey
    8:   (110, 110, 110),   # dark grey
    10:  (255,  80,  80),
    24:  (  0, 140, 140),
    30:  (230, 130,   0),   # orange    – slabs
    34:  (  0, 140, 100),
    40:  (180, 100,   0),
    42:  (180,  70,   0),
    50:  (180, 150,   0),
    62:  (130, 130,   0),   # olive     – members/rafters
    70:  (  0, 110, 110),
    90:  (  0,   0, 140),
    141: (110, 110, 190),
    160: ( 80,  80, 220),
    252: (190, 190, 190),
}
_DEFAULT_RGB = (160, 160, 160)


def _color_for(element) -> int:
    cls = element.is_a()
    if cls in _CLASS_COLOR:
        return _CLASS_COLOR[cls]
    for key, col in _CLASS_COLOR.items():
        try:
            if element.is_a(key):
                return col
        except Exception:
            pass
    return _DEFAULT_COLOR


# ─────────────────────────────────────────────────────────────────────────────
# Attribute helpers
# ─────────────────────────────────────────────────────────────────────────────

def _s(val) -> str:
    """Safely stringify any IFC attribute value."""
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return ", ".join(_s(v) for v in val)
    return str(val)


def _get_tag(element) -> str:
    tag  = getattr(element, "Tag",  None)
    name = getattr(element, "Name", None)
    return _s(tag or name or element.GlobalId[:8])


def _get_prefix(element) -> str:
    """Get Prefix / Mark from psets (mirrors get_element_details prefix logic)."""
    # Same keys as get_element_details — Reference from Pset_BeamCommon etc. counts as prefix
    _PREFIX_KEYS = {"prefix", "mark", "reference", "objectmark", "elementmark"}
    try:
        psets = ifcopenshell.util.element.get_psets(element, should_inherit=True)
        for pset_props in psets.values():
            if not isinstance(pset_props, dict):
                continue
            for key, val in pset_props.items():
                kl = key.lower().replace(" ", "").replace("_", "")
                if kl in _PREFIX_KEYS:
                    sv = _s(val)
                    if sv:
                        return sv
    except Exception:
        pass
    return ""


def _get_reference(element) -> str:
    """Get Reference property from psets (e.g. Pset_BeamCommon), including type-inherited."""
    try:
        psets = ifcopenshell.util.element.get_psets(element, should_inherit=True)
        for pset_props in psets.values():
            if not isinstance(pset_props, dict):
                continue
            for key, val in pset_props.items():
                if key == "Reference":
                    sv = _s(val)
                    if sv:
                        return sv
    except Exception:
        pass
    return ""


def _get_type_name(element) -> str:
    try:
        t = ifcopenshell.util.element.get_type(element)
        return _s(getattr(t, "Name", "")) if t else ""
    except Exception:
        return ""


def _get_material_name(element) -> str:
    """Return a human-readable material name for any IFC material association."""
    try:
        mat = ifcopenshell.util.element.get_material(element)
        if mat is None:
            return ""
        cls = mat.is_a()
        if cls == "IfcMaterial":
            return _s(mat.Name)
        if cls == "IfcMaterialList":
            return ", ".join(_s(m.Name) for m in (mat.Materials or []) if m)
        if cls in ("IfcMaterialLayerSetUsage", "IfcMaterialLayerSet"):
            ls = mat.ForLayerSet if cls.endswith("Usage") else mat
            layers = ls.MaterialLayers if ls else []
            return ", ".join(
                _s(l.Material.Name) for l in (layers or []) if l and l.Material)
        if cls in ("IfcMaterialProfileSetUsage", "IfcMaterialProfileSet"):
            ps = mat.ForProfileSet if cls.endswith("Usage") else mat
            profiles = ps.MaterialProfiles if ps else []
            return ", ".join(
                _s(p.Material.Name) for p in (profiles or []) if p and p.Material)
        return _s(getattr(mat, "Name", ""))
    except Exception:
        return ""


def _unit_scale_to_mm(model) -> float:
    """Multiply IFC world-coords by this to get millimetres.
    With USE_WORLD_COORDS=True ifcopenshell always returns SI metres,
    so the scale is always ×1000 regardless of the IFC project unit."""
    return 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# Assembly decomposition helper
# ─────────────────────────────────────────────────────────────────────────────

def _collect_geometry_sources(element) -> List:
    """
    Return the flat list of IFC elements whose geometry should be combined
    into one DXF BLOCK for *element*.

    Why this is needed
    ------------------
    IfcElementAssembly (trusses, frames, stair flights, curtain-wall panels…)
    owns NO body geometry itself.  Geometry is attached to its child parts via
    IfcRelAggregates → RelatedObjects.  Calling create_shape() on the assembly
    directly always fails.

    Algorithm
    ---------
    Walk IsDecomposedBy → IfcRelAggregates recursively.
    Collect only LEAF nodes (elements with no further decomposition).
    If the element has no children at all, return [element] so the caller
    can still attempt create_shape() on it directly.
    """
    leaves: List = []

    def _walk(el):
        children = []
        for rel in (getattr(el, "IsDecomposedBy", None) or []):
            if rel.is_a("IfcRelAggregates"):
                children.extend(rel.RelatedObjects)
        if children:
            for child in children:
                _walk(child)
        else:
            leaves.append(el)

    _walk(element)
    return leaves or [element]


def _count_parts(element) -> int:
    """Return total number of leaf parts (0 if element is a leaf itself)."""
    sources = _collect_geometry_sources(element)
    if len(sources) == 1 and sources[0] is element:
        return 0
    return len(sources)


# ─────────────────────────────────────────────────────────────────────────────
# Public: fast metadata scan  (no geometry)
# ─────────────────────────────────────────────────────────────────────────────

def scan_ifc(
    ifc_path: str,
    status_cb:   Callable[[str], None]  | None = None,
    progress_cb: Callable[[int], None]  | None = None,
) -> tuple[Any, List[Dict[str, Any]]]:
    """
    Open *ifc_path*, iterate all IfcElement instances and collect basic
    metadata — NO geometry is built so this is fast.

    Returns
    -------
    (model, rows)
        model : open ifcopenshell model  — kept alive so detail lookups are free
        rows  : list of dicts with keys: guid, tag, name, ifc_class, type_name, color
    """
    if status_cb:
        status_cb("Opening IFC file…")

    model = ifcopenshell.open(ifc_path)
    all_elements = model.by_type("IfcElement")
    total = len(all_elements)
    rows: List[Dict[str, Any]] = []

    for idx, el in enumerate(all_elements):
        if progress_cb and idx % 100 == 0:
            progress_cb(int(idx / total * 100))

        n_parts = _count_parts(el)
        rows.append({
            "guid":            el.GlobalId,
            "tag":             _get_tag(el),
            "name":            _s(getattr(el, "Name", "")),
            "description":     _s(getattr(el, "Description", "")),
            "ifc_class":       el.is_a(),
            "predefined_type": _s(getattr(el, "PredefinedType", "")),
            "type_name":       _get_type_name(el),
            "material":        _get_material_name(el),
            "prefix":          _get_prefix(el),
            "reference":       _get_reference(el),
            "color":           _color_for(el),
            "n_parts":         n_parts,   # 0 = leaf element, >0 = assembly
        })

    if progress_cb:
        progress_cb(100)
    if status_cb:
        status_cb(f"Scan complete — {len(rows)} elements found.")

    return model, rows


# ─────────────────────────────────────────────────────────────────────────────
# Public: full detail for one element  (called on UI selection — fast)
# ─────────────────────────────────────────────────────────────────────────────

def get_element_details(model, guid: str) -> Dict[str, Any]:
    """
    Return a comprehensive property dict for a single element identified by
    *guid*.  Reads from the already-open *model* — no file I/O.

    Returned keys
    -------------
    guid, tag, name, description, ifc_class, predefined_type, type_name,
    material, phase, layer, prefix, model_ref, detail  +  psets (nested dict).
    """
    try:
        element = model.by_guid(guid)
    except Exception:
        return {}

    # Collect all property sets (inheriting from type)
    psets: Dict[str, Any] = {}
    try:
        psets = ifcopenshell.util.element.get_psets(element, should_inherit=True)
    except Exception:
        pass

    # Scrape well-known fields from whatever psets exist
    phase = layer = prefix = model_ref = detail = ""
    for pset_props in psets.values():
        if not isinstance(pset_props, dict):
            continue
        for key, val in pset_props.items():
            kl = key.lower().replace(" ", "").replace("_", "")
            sv = _s(val)
            if not sv:
                continue
            if kl in ("phase", "constructionphase", "buildingphase") and not phase:
                phase = sv
            if kl in ("layer", "cadlayer", "drawlayer") and not layer:
                layer = sv
            if kl in ("prefix", "mark", "reference", "objectmark", "elementmark") and not prefix:
                prefix = sv
            if kl == "model" and not model_ref:
                model_ref = sv
            if kl == "detail" and not detail:
                detail = sv

    return {
        "guid":            guid,
        "tag":             _get_tag(element),
        "name":            _s(getattr(element, "Name",        "")),
        "description":     _s(getattr(element, "Description", "")),
        "ifc_class":       element.is_a(),
        "predefined_type": _s(getattr(element, "PredefinedType", "")),
        "type_name":       _get_type_name(element),
        "material":        _get_material_name(element),
        "phase":           phase,
        "layer":           layer,
        "prefix":          prefix,
        "model_ref":       model_ref,
        "detail":          detail,
        "psets":           psets,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public: extract geometry for in-app 3D preview
# ─────────────────────────────────────────────────────────────────────────────

def get_preview_geometry(model, guid: str) -> Dict[str, Any]:
    """
    Extract and centre mesh data for one element/assembly for the 3D viewer.

    Returns
    -------
    {
      "tag"   : str,
      "parts" : [{"verts": [(x,y,z)…], "faces": [(i,j,k)…], "rgb": (r,g,b)}, …]
    }
    All coordinates are centred around the element's bounding-box midpoint
    and scaled so the largest dimension fits in ±1 unit (viewer handles zoom).
    """
    try:
        element = model.by_guid(guid)
    except Exception:
        return {"tag": guid, "parts": []}

    scale_mm = _unit_scale_to_mm(model)
    geo_sources = _collect_geometry_sources(element)

    gs = ifcopenshell.geom.settings()
    gs.set(gs.USE_WORLD_COORDS, True)
    gs.set(gs.WELD_VERTICES, True)

    raw_parts = []
    for part in geo_sources:
        try:
            shape = ifcopenshell.geom.create_shape(gs, part)
        except Exception:
            continue
        vf = shape.geometry.verts
        ff = shape.geometry.faces
        if not vf or not ff:
            continue
        verts = [(vf[i]*scale_mm, vf[i+1]*scale_mm, vf[i+2]*scale_mm)
                 for i in range(0, len(vf), 3)]
        faces = [(ff[i], ff[i+1], ff[i+2]) for i in range(0, len(ff), 3)]
        aci   = _color_for(part)
        rgb   = ACI_TO_RGB.get(aci, _DEFAULT_RGB)
        raw_parts.append({"verts": verts, "faces": faces, "rgb": rgb})

    if not raw_parts:
        return {"tag": _get_tag(element), "parts": []}

    # Centre and normalise
    all_v = [v for p in raw_parts for v in p["verts"]]
    mn = [min(v[i] for v in all_v) for i in range(3)]
    mx = [max(v[i] for v in all_v) for i in range(3)]
    mid = [(mn[i]+mx[i])/2 for i in range(3)]
    extent = max(mx[i]-mn[i] for i in range(3)) or 1.0

    centred_parts = []
    for p in raw_parts:
        cv = [((v[0]-mid[0])/extent,
               (v[1]-mid[1])/extent,
               (v[2]-mid[2])/extent) for v in p["verts"]]
        centred_parts.append({"verts": cv, "faces": p["faces"], "rgb": p["rgb"]})

    return {"tag": _get_tag(element), "parts": centred_parts}


# ─────────────────────────────────────────────────────────────────────────────
# Conversion Engine
# ─────────────────────────────────────────────────────────────────────────────

def _safe_filename(tag: str) -> str:
    """Sanitise a tag string so it can be used as a Windows/Linux filename."""
    safe = re.sub(r'[\\/:*?"<>|]', "_", tag).strip(" .")
    return safe or "unnamed"


class ConversionEngine:
    """
    Convert selected IFC elements to DXF — one file per element, named
    after the element's Tag attribute, saved into *output_dir*.

    Geometry
    --------
    Each element (or assembly of parts) is stored as one AutoCAD BLOCK made
    of classic POLYFACE MESH entities (PFACE POLYLINE) — visible in every
    AutoCAD view mode (wireframe, hidden, shaded) with correct ACI colour.
    """

    def __init__(
        self,
        ifc_path:    str,
        output_dir:  str,          # folder — one .dxf per element
        guids:       List[str],
        progress_cb: Callable[[int], None],
        status_cb:   Callable[[str], None],
        complete_cb: Callable[[bool, str], None],
    ) -> None:
        self.ifc_path   = ifc_path
        self.output_dir = output_dir
        self.guids      = set(guids)
        self._progress  = progress_cb
        self._status    = status_cb
        self._complete  = complete_cb
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self._convert()
        except Exception as exc:
            import traceback
            self._complete(False, f"Unexpected error:\n{exc}\n\n{traceback.format_exc()}")

    def _convert(self) -> None:
        # ── Open IFC ────────────────────────────────────────────────
        self._status("Opening IFC file…")
        try:
            model = ifcopenshell.open(self.ifc_path)
        except Exception as exc:
            self._complete(False, f"Cannot open IFC:\n{exc}")
            return

        scale = _unit_scale_to_mm(model)
        self._status(f"Unit scale → mm: ×{scale:.6g}")

        # ── Filter elements ──────────────────────────────────────────
        all_elements = model.by_type("IfcElement")
        elements = [e for e in all_elements if e.GlobalId in self.guids]
        total = len(elements)
        if total == 0:
            self._complete(False,
                "No matching elements found in the IFC.\n"
                "Scan first, then select elements before converting.")
            return

        os.makedirs(self.output_dir, exist_ok=True)
        self._status(f"Converting {total} element(s) → {self.output_dir}")

        gs = ifcopenshell.geom.settings()
        gs.set(gs.USE_WORLD_COORDS, True)
        gs.set(gs.WELD_VERTICES,    True)

        converted     = 0
        skipped       = 0
        skip_log:     List[str] = []
        created_files: List[str] = []
        used_filenames: set[str] = set()

        for idx, element in enumerate(elements):
            if self._cancelled:
                self._complete(False, "Cancelled.")
                return

            self._progress(int(idx / total * 100))
            tag    = _get_tag(element)
            prefix = _get_prefix(element)
            label  = prefix or tag   # use prefix for block name + filename when available
            color  = _color_for(element)
            layer  = re.sub(r"[^A-Za-z0-9_\-]", "_", element.is_a())

            geo_sources = _collect_geometry_sources(element)
            is_asm = not (len(geo_sources) == 1 and geo_sources[0] is element)
            asm_label = f"(assembly: {len(geo_sources)} parts)" if is_asm else ""
            self._status(f"[{idx+1}/{total}]  {element.is_a()} — {label}  {asm_label}")

            # ── Fresh DXF doc per element ─────────────────────────────
            doc = ezdxf.new(dxfversion="R2010")
            doc.header["$INSUNITS"] = 4   # mm
            msp = doc.modelspace()

            doc.layers.new(name=layer, dxfattribs={"color": color})

            bname = re.sub(r"[^A-Za-z0-9_\-]", "_", label)
            blk = doc.blocks.new(name=bname)

            import math as _math
            CREASE = _math.radians(25)

            def _tri_normal(a, b, c):
                ax, ay, az = b[0]-a[0], b[1]-a[1], b[2]-a[2]
                bx, by, bz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
                nx, ny, nz = ay*bz-az*by, az*bx-ax*bz, ax*by-ay*bx
                l = _math.sqrt(nx*nx + ny*ny + nz*nz)
                return (nx/l, ny/l, nz/l) if l > 1e-12 else (0.0, 0.0, 1.0)

            # ── Pass 1: collect geometry from all parts ───────────────
            parts_data = []
            all_verts_flat = []
            for part in geo_sources:
                try:
                    shape = ifcopenshell.geom.create_shape(gs, part)
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    skip_log.append(f"  ✗ part {_get_tag(part)} of {tag}: {reason}")
                    self._status(f"    ✗ part {_get_tag(part)}: {reason}")
                    continue

                vf = shape.geometry.verts
                ff = shape.geometry.faces
                if not vf or not ff:
                    skip_log.append(f"  ✗ part {_get_tag(part)} of {tag}: empty geometry")
                    continue

                verts = [(vf[i]*scale, vf[i+1]*scale, vf[i+2]*scale)
                         for i in range(0, len(vf), 3)]
                all_verts_flat.extend(verts)
                parts_data.append((part, verts, ff))

            if not parts_data:
                skip_log.append(f"  ✗ {tag}: no mesh produced")
                self._status(f"  ✗ Skipped {tag}: no geometry")
                skipped += 1
                continue

            # ── Centre geometry at origin (bounding-box midpoint) ─────
            xs = [v[0] for v in all_verts_flat]
            ys = [v[1] for v in all_verts_flat]
            zs = [v[2] for v in all_verts_flat]
            cx = (min(xs) + max(xs)) / 2
            cy = (min(ys) + max(ys)) / 2
            cz = (min(zs) + max(zs)) / 2
            hw = (max(xs) - min(xs)) / 2
            hh = (max(ys) - min(ys)) / 2
            hd = (max(zs) - min(zs)) / 2

            # Set drawing extents so AutoCAD zoom-extents works correctly
            doc.header["$EXTMIN"] = (-hw, -hh, -hd)
            doc.header["$EXTMAX"] = ( hw,  hh,  hd)
            doc.header["$LIMMIN"] = (-hw, -hh)
            doc.header["$LIMMAX"] = ( hw,  hh)

            # ── Pass 2: build feature-edge 3DFACEs inside block ──────
            mesh_count = 0
            for part, raw_verts, ff in parts_data:
                verts = [(x-cx, y-cy, z-cz) for x, y, z in raw_verts]

                part_color = _color_for(part)
                part_layer = re.sub(r"[^A-Za-z0-9_\-]", "_", part.is_a())
                if part_layer not in doc.layers:
                    doc.layers.new(name=part_layer, dxfattribs={"color": part_color})

                nv = len(verts)
                tris = [(ff[i], ff[i+1], ff[i+2])
                        for i in range(0, len(ff), 3)
                        if ff[i] < nv and ff[i+1] < nv and ff[i+2] < nv]

                normals = [_tri_normal(verts[fi], verts[fj], verts[fk])
                           for fi, fj, fk in tris]

                edge_normals: Dict[tuple, List] = {}
                for ti, (fi, fj, fk) in enumerate(tris):
                    for a, b in ((fi, fj), (fj, fk), (fk, fi)):
                        edge_normals.setdefault((min(a,b), max(a,b)), []).append(normals[ti])

                def _feature(a, b):
                    ns = edge_normals.get((min(a,b), max(a,b)), [])
                    if len(ns) != 2:
                        return True
                    dot = max(-1.0, min(1.0, sum(ns[0][i]*ns[1][i] for i in range(3))))
                    return _math.acos(dot) > CREASE

                for fi, fj, fk in tris:
                    inv = 4
                    if not _feature(fi, fj): inv |= 1
                    if not _feature(fj, fk): inv |= 2
                    if not _feature(fk, fi): inv |= 8
                    blk.add_3dface(
                        [verts[fi], verts[fj], verts[fk], verts[fk]],
                        dxfattribs={"layer": part_layer, "color": part_color,
                                    "invisible_edges": inv},
                    )
                mesh_count += 1

            if mesh_count == 0:
                skip_log.append(f"  ✗ {tag}: no mesh produced")
                self._status(f"  ✗ Skipped {tag}: no geometry")
                skipped += 1
                continue

            msp.add_blockref(bname, (0.0, 0.0, 0.0), dxfattribs={"layer": layer})

            # ── Save as {prefix or tag}.dxf ──────────────────────────
            fname = _safe_filename(label) + ".dxf"
            if fname in used_filenames:
                n = 2
                base = _safe_filename(label)
                while f"{base}_{n}.dxf" in used_filenames:
                    n += 1
                fname = f"{base}_{n}.dxf"
            used_filenames.add(fname)
            fpath = os.path.join(self.output_dir, fname)

            try:
                doc.saveas(fpath)
                created_files.append(fname)
                converted += 1
            except Exception as exc:
                skip_log.append(f"  ✗ {tag}: save failed — {exc}")
                skipped += 1

        self._progress(100)

        file_list = "\n  ".join(created_files[:20])
        ellipsis  = f"\n  … and {len(created_files)-20} more" \
                    if len(created_files) > 20 else ""
        skip_part = ("\n\nSkipped:\n" + "\n".join(skip_log)) if skip_log else ""

        self._complete(
            True,
            f"Done!  {converted} file(s) created,  {skipped} skipped.\n"
            f"Folder → {self.output_dir}\n\n"
            f"Files:\n  {file_list}{ellipsis}"
            + skip_part,
        )
