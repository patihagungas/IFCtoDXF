"""
gui.py  —  IFC → DXF Converter
Split-panel layout  +  in-app 3D preview  +  per-tag file output.
"""

from __future__ import annotations

import math
import os
import threading
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

import customtkinter as ctk

from converter_engine import (
    ConversionEngine, scan_ifc, get_element_details, get_preview_geometry
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_ACCENT      = "#0096c7"
_ACCENT_DARK = "#023e8a"
_BG_HEADER   = "#0d1b2a"
_BG_TABLE    = "#1e1e1e"
_FG_TABLE    = "#dce1e7"
_SEL_BG      = "#0077b6"
_HDG_BG      = "#0d1b2a"
_HDG_FG      = "#0096c7"
_PROP_KEY    = "#7ab8d4"
_PROP_SECT   = "#0096c7"
_FONT_MONO   = ("Consolas", 11)
_FONT_TABLE  = ("Segoe UI", 11)
_FONT_HDG    = ("Segoe UI", 11, "bold")


# ─────────────────────────────────────────────────────────────────────────────
# 3-D Preview Window
# ─────────────────────────────────────────────────────────────────────────────

class PreviewWindow(tk.Toplevel):
    """
    Interactive 3-D mesh viewer — three display modes:
      Shaded          : flat-shaded filled polygons (painter's algorithm)
      Wireframe       : coloured mesh edges only, depth-sorted
      Shaded + Edges  : shaded polygons with black edge outlines

    Controls
    --------
    Left-drag   → orbit   |   Scroll → zoom   |   Right-drag → pan
    """

    SHADED       = "shaded"
    WIREFRAME    = "wireframe"
    SHADED_EDGES = "shaded+edges"

    # Two lights: key (upper-right) + fill (lower-left) so no face goes black
    _KEY_LIGHT  = (0.50,  0.70,  0.55)
    _FILL_LIGHT = (-0.30, -0.40, -0.20)
    _AMBIENT    = 0.30                   # minimum brightness (0-1)
    _BG         = "#111318"
    _GRID       = "#1a1d24"
    _GRID_STEP  = 60

    def __init__(self, parent, geo: dict) -> None:
        super().__init__(parent)
        tag = geo.get("tag", "?")
        self.title(f"3D Preview — {tag}")
        self.geometry("900x680")
        self.configure(bg=self._BG)
        self.minsize(500, 380)

        self._parts = geo.get("parts", [])
        self._mode  = self.SHADED
        self._rot_x =  22.0
        self._rot_y = -38.0
        self._zoom  = 270.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._drag  = None
        self._mode_btns: dict[str, tk.Button] = {}

        if not self._parts:
            tk.Label(self, text="No geometry available for this element.",
                     bg=self._BG, fg="#446688",
                     font=("Segoe UI", 13)).pack(expand=True)
            return

        n_verts = sum(len(p["verts"]) for p in self._parts)
        n_faces = sum(len(p["faces"]) for p in self._parts)

        self._build_toolbar(tag, n_verts, n_faces)
        self._build_canvas()
        self._draw()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self, tag: str, n_verts: int, n_faces: int) -> None:
        tb = tk.Frame(self, bg="#0d1b2a", height=46)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        # Mode buttons
        for mode, label, icon in [
            (self.SHADED,       "Shaded",         "◼"),
            (self.WIREFRAME,    "Wireframe",       "⬡"),
            (self.SHADED_EDGES, "Shaded + Edges",  "◈"),
        ]:
            btn = tk.Button(
                tb, text=f" {icon}  {label} ",
                bg="#0096c7" if mode == self._mode else "#1a2a3a",
                fg="#ffffff", activebackground="#023e8a",
                activeforeground="#ffffff",
                relief="flat", bd=0,
                font=("Segoe UI", 10, "bold"),
                cursor="hand2",
                command=lambda m=mode: self._set_mode(m),
            )
            btn.pack(side="left", padx=(6, 2), pady=8, ipady=4, ipadx=6)
            self._mode_btns[mode] = btn

        # Separator
        tk.Frame(tb, bg="#1a3a4a", width=1).pack(side="left", fill="y",
                                                   padx=10, pady=8)

        # Stats
        tk.Label(tb,
                 text=f"{n_verts:,} verts  ·  {n_faces:,} faces",
                 bg="#0d1b2a", fg="#446688",
                 font=("Segoe UI", 10)).pack(side="left", padx=4)

        # Hint
        tk.Label(tb,
                 text="L-drag: rotate   R-drag: pan   Scroll: zoom",
                 bg="#0d1b2a", fg="#334455",
                 font=("Segoe UI", 9)).pack(side="left", padx=16)

        # Reset
        tk.Button(tb, text="  ↺  Reset  ",
                  bg="#1a3a4a", fg="#dce1e7",
                  activebackground="#0d2a3a",
                  relief="flat", bd=0, cursor="hand2",
                  font=("Segoe UI", 10),
                  command=self._reset_view
                  ).pack(side="right", padx=10, pady=8, ipady=4)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        for m, btn in self._mode_btns.items():
            btn.configure(bg="#0096c7" if m == mode else "#1a2a3a")
        self._draw()

    # ── Canvas + bindings ─────────────────────────────────────────────────────

    def _build_canvas(self) -> None:
        self._canvas = tk.Canvas(self, bg=self._BG,
                                 highlightthickness=0, cursor="fleur")
        self._canvas.pack(fill="both", expand=True)
        cv = self._canvas
        cv.bind("<Configure>",     lambda _: self._draw())
        cv.bind("<ButtonPress-1>", self._lpress)
        cv.bind("<B1-Motion>",     self._ldrag)
        cv.bind("<ButtonPress-3>", self._rpress)
        cv.bind("<B3-Motion>",     self._rpan)
        cv.bind("<MouseWheel>",    self._scroll)
        cv.bind("<Button-4>",      self._scroll)
        cv.bind("<Button-5>",      self._scroll)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def _reset_view(self) -> None:
        self._rot_x, self._rot_y = 22.0, -38.0
        self._zoom  = 270.0
        self._pan_x = self._pan_y = 0.0
        self._draw()

    def _lpress(self, e) -> None:
        self._drag = (e.x, e.y, self._rot_x, self._rot_y)

    def _ldrag(self, e) -> None:
        if not self._drag:
            return
        sx, sy, rx0, ry0 = self._drag
        self._rot_y = ry0 + (e.x - sx) * 0.4
        self._rot_x = rx0 - (e.y - sy) * 0.4
        self._draw()

    def _rpress(self, e) -> None:
        self._drag = (e.x, e.y, self._pan_x, self._pan_y)

    def _rpan(self, e) -> None:
        if not self._drag:
            return
        sx, sy, px0, py0 = self._drag
        self._pan_x = px0 + (e.x - sx)
        self._pan_y = py0 + (e.y - sy)
        self._draw()

    def _scroll(self, e) -> None:
        f = 1.13
        d = getattr(e, "delta", 0)
        self._zoom *= f if (d > 0 or e.num == 4) else (1 / f)
        self._zoom  = max(8.0, min(self._zoom, 6000.0))
        self._draw()

    # ── Math ──────────────────────────────────────────────────────────────────

    def _project(self, v, cx: float, cy: float) -> tuple:
        x, y, z = v
        ry = math.radians(self._rot_y)
        x2 =  x * math.cos(ry) - z * math.sin(ry)
        z2 =  x * math.sin(ry) + z * math.cos(ry)
        rx = math.radians(self._rot_x)
        y2 =  y * math.cos(rx) + z2 * math.sin(rx)
        z3 = -y * math.sin(rx) + z2 * math.cos(rx)
        return (cx + x2 * self._zoom + self._pan_x,
                cy - y2 * self._zoom + self._pan_y,
                z3)

    @staticmethod
    def _cross(a, b) -> tuple:
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

    @staticmethod
    def _norm(v) -> tuple:
        l = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        return (v[0]/l, v[1]/l, v[2]/l) if l > 1e-12 else (0.0, 0.0, 1.0)

    def _flat_shade(self, v0, v1, v2, rgb: tuple) -> tuple:
        """
        Return (fill_hex, edge_hex) for a face.
        Uses a two-light model (key + fill) so every face gets some colour —
        no face goes completely black regardless of orientation.
        """
        e1 = (v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2])
        e2 = (v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2])
        n  = self._norm(self._cross(e1, e2))

        kx, ky, kz = self._KEY_LIGHT
        fx, fy, fz = self._FILL_LIGHT
        key  = max(0.0, n[0]*kx + n[1]*ky + n[2]*kz)
        fill = max(0.0, n[0]*fx + n[1]*fy + n[2]*fz) * 0.40
        intensity = self._AMBIENT + (1.0 - self._AMBIENT) * (key + fill)
        intensity = min(1.0, intensity)

        # Edge: slightly darker so it's readable on the face
        ei = max(0.0, intensity - 0.28)

        def _hex(r, g, b, i):
            return f"#{min(255,int(r*i)):02x}{min(255,int(g*i)):02x}{min(255,int(b*i)):02x}"
        return _hex(*rgb, intensity), _hex(*rgb, ei)

    # ── Render ────────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        {
            self.SHADED:       self._render_shaded,
            self.WIREFRAME:    self._render_wireframe,
            self.SHADED_EDGES: self._render_shaded_edges,
        }[self._mode]()

    def _prep(self):
        """Clear canvas, draw background grid, return (canvas, w, h, cx, cy)."""
        c = self._canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 2 or h < 2:
            return c, 0, 0, 0, 0
        # Background
        c.create_rectangle(0, 0, w, h, fill=self._BG, outline="")
        # Grid
        for x in range(0, w, self._GRID_STEP):
            c.create_line(x, 0, x, h, fill=self._GRID, width=1)
        for y in range(0, h, self._GRID_STEP):
            c.create_line(0, y, w, y, fill=self._GRID, width=1)
        return c, w, h, w/2, h/2

    def _collect_faces(self, cx, cy):
        """Project all parts and return list of (avg_z, p0,p1,p2, fill,edge, v0,v1,v2)."""
        result = []
        for part in self._parts:
            verts, faces, rgb = part["verts"], part["faces"], part["rgb"]
            proj = [self._project(v, cx, cy) for v in verts]
            for fi, fj, fk in faces:
                try:
                    p0, p1, p2 = proj[fi], proj[fj], proj[fk]
                except IndexError:
                    continue
                fill, edge = self._flat_shade(verts[fi], verts[fj], verts[fk], rgb)
                avg_z = (p0[2]+p1[2]+p2[2]) / 3
                result.append((avg_z, p0, p1, p2, fill, edge))
        result.sort(key=lambda t: t[0])
        return result

    def _collect_edges(self, cx, cy):
        """Return deduplicated edges as (avg_z, p0, p1, hex_color) per part."""
        result = []
        for part in self._parts:
            verts, faces, rgb = part["verts"], part["faces"], part["rgb"]
            proj  = [self._project(v, cx, cy) for v in verts]
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            seen  : set[tuple] = set()
            for fi, fj, fk in faces:
                for a, b in ((fi,fj),(fj,fk),(fk,fi)):
                    key = (min(a,b), max(a,b))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        p0, p1 = proj[a], proj[b]
                        result.append(((p0[2]+p1[2])/2, p0, p1, color))
                    except IndexError:
                        pass
        return result

    def _render_shaded(self) -> None:
        c, w, h, cx, cy = self._prep()
        if not w:
            return
        for _, p0, p1, p2, fill, _ in self._collect_faces(cx, cy):
            c.create_polygon(p0[0],p0[1], p1[0],p1[1], p2[0],p2[1],
                             fill=fill, outline="")
        self._draw_axis(c, 55, h-55)
        self._draw_label(c, w, h)

    def _render_wireframe(self) -> None:
        """Coloured edges only — each part drawn in its ACI class colour."""
        c, w, h, cx, cy = self._prep()
        if not w:
            return
        edges = self._collect_edges(cx, cy)
        edges.sort(key=lambda e: e[0])   # back→front
        for _, p0, p1, color in edges:
            c.create_line(p0[0], p0[1], p1[0], p1[1],
                          fill=color, width=1)
        self._draw_axis(c, 55, h-55)
        self._draw_label(c, w, h)

    def _render_shaded_edges(self) -> None:
        """Shaded fill + coloured edge overlay — closest to AutoCAD 'Shaded with Edges'."""
        c, w, h, cx, cy = self._prep()
        if not w:
            return
        # Pass 1: shaded filled polygons
        for _, p0, p1, p2, fill, _ in self._collect_faces(cx, cy):
            c.create_polygon(p0[0], p0[1], p1[0], p1[1], p2[0], p2[1],
                             fill=fill, outline="")
        # Pass 2: deduplicated coloured edges on top
        edges = self._collect_edges(cx, cy)
        edges.sort(key=lambda e: e[0])
        for _, p0, p1, color in edges:
            # Dim the edge colour so it contrasts against the shaded fill
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            dim = f"#{int(r*0.55):02x}{int(g*0.55):02x}{int(b*0.55):02x}"
            c.create_line(p0[0], p0[1], p1[0], p1[1], fill=dim, width=1)
        self._draw_axis(c, 55, h-55)
        self._draw_label(c, w, h)

    # ── HUD helpers ───────────────────────────────────────────────────────────

    def _draw_axis(self, c, ox: float, oy: float) -> None:
        """Small RGB XYZ triad in the bottom-left corner."""
        # Draw circle backdrop
        r = 34
        c.create_oval(ox-r, oy-r, ox+r, oy+r, fill="#0d1520", outline="#1a2a3a")
        scale = r * 0.80
        for vec, col, lbl in [
            ((1,0,0), "#ff4444", "X"),
            ((0,1,0), "#44dd44", "Y"),
            ((0,0,1), "#4488ff", "Z"),
        ]:
            px, py, _ = self._project(vec, 0, 0)
            # Normalise to unit length for the indicator
            l = math.sqrt(px**2 + py**2) or 1
            ex = ox + (px/l) * scale
            ey = oy + (py/l) * scale
            c.create_line(ox, oy, ex, ey, fill=col, width=2, arrow="last",
                          arrowshape=(6, 8, 3))
            c.create_text(ex, ey-1, text=lbl, fill=col,
                          font=("Segoe UI", 8, "bold"))

    def _draw_label(self, c, w: float, h: float) -> None:
        """Mode label bottom-right."""
        labels = {self.SHADED: "⬛ Shaded",
                  self.WIREFRAME: "⬡ Wireframe",
                  self.SHADED_EDGES: "◈ Shaded + Edges"}
        c.create_text(w-10, h-10, text=labels[self._mode],
                      fill="#334455", anchor="se",
                      font=("Segoe UI", 9))


# ─────────────────────────────────────────────────────────────────────────────
# Main App
# ─────────────────────────────────────────────────────────────────────────────

class App(ctk.CTk):

    W, H = 1100, 740

    def __init__(self) -> None:
        super().__init__()
        self.title("Path IFC to DXF")
        self.iconbitmap(os.path.join(os.path.dirname(__file__), "P.ico"))
        self.geometry(f"{self.W}x{self.H}")
        self.minsize(860, 600)

        self._ifc_path  = ctk.StringVar()
        self._out_dir   = ctk.StringVar()   # output FOLDER, not a single file
        self._search    = ctk.StringVar()
        self._search.trace_add("write", lambda *_: self._apply_filter())

        self._ifc_model  = None
        self._all_rows: list[dict] = []
        self._engine: ConversionEngine | None = None
        self._checked: set[str] = set()   # GUIDs that are checked

        self._style_tree()
        self._build_ui()

    def _style_tree(self) -> None:
        s = ttk.Style(self)
        s.theme_use("default")
        s.configure("T.Treeview",
            background=_BG_TABLE, foreground=_FG_TABLE,
            fieldbackground=_BG_TABLE, rowheight=32, font=_FONT_TABLE,
            borderwidth=0, relief="flat")
        s.configure("T.Treeview.Heading",
            background=_HDG_BG, foreground=_HDG_FG,
            font=_FONT_HDG, relief="flat", borderwidth=0)
        s.map("T.Treeview",
            background=[("selected", _SEL_BG)],
            foreground=[("selected", "#ffffff")])

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color=_BG_HEADER, corner_radius=0, height=58)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="IFC  to  DXF",
                     font=ctk.CTkFont(size=21, weight="bold"),
                     text_color=_ACCENT).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(hdr, text="Made by Path",
                     font=ctk.CTkFont(size=10), text_color="#8B8B8B"
                     ).place(relx=0.99, rely=0.82, anchor="se")

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=18, pady=10)

        # ── File rows ─────────────────────────────────────────────────
        r1 = ctk.CTkFrame(wrap, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="IFC File", font=ctk.CTkFont(size=13, weight="bold"),
                     width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(r1, textvariable=self._ifc_path, height=34,
                     font=ctk.CTkFont(size=12)).pack(
            side="left", fill="x", expand=True, padx=(8, 8))
        ctk.CTkButton(r1, text="Browse", width=80, height=34,
                      command=self._browse_ifc).pack(side="left", padx=(0, 6))
        self._scan_btn = ctk.CTkButton(
            r1, text="▶  Scan IFC", width=110, height=34,
            fg_color=_ACCENT, hover_color=_ACCENT_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._scan)
        self._scan_btn.pack(side="left")

        r2 = ctk.CTkFrame(wrap, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="Output Folder", font=ctk.CTkFont(size=13, weight="bold"),
                     width=110, anchor="w").pack(side="left")
        ctk.CTkEntry(r2, textvariable=self._out_dir, height=34,
                     placeholder_text="Folder where  {Tag}.dxf  files will be saved…",
                     font=ctk.CTkFont(size=12)).pack(
            side="left", fill="x", expand=True, padx=(8, 8))
        ctk.CTkButton(r2, text="Browse", width=80, height=34,
                      command=self._browse_outdir).pack(side="left")

        self._div(wrap)

        # ── Split: table (left) + properties (right) ──────────────────
        split = ctk.CTkFrame(wrap, fg_color="transparent")
        split.pack(fill="both", expand=True)
        split.columnconfigure(0, weight=6)
        split.columnconfigure(1, weight=0)
        split.columnconfigure(2, weight=4)
        split.rowconfigure(0, weight=1)

        left = ctk.CTkFrame(split, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # Search row
        ctrl = ctk.CTkFrame(left, fg_color="transparent")
        ctrl.pack(fill="x", pady=(0, 3))
        ctk.CTkLabel(ctrl, text="Search:", font=ctk.CTkFont(size=12)
                     ).pack(side="left")
        ctk.CTkEntry(ctrl, textvariable=self._search,
                     placeholder_text="Tag, prefix, name, class, material…",
                     height=28, font=ctk.CTkFont(size=12)
                     ).pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkButton(ctrl, text="All", width=50, height=28,
                      command=self._check_all).pack(side="left", padx=(0, 4))
        ctk.CTkButton(ctrl, text="None", width=54, height=28,
                      fg_color="#3a3a3a", hover_color="#222",
                      command=self._check_none).pack(side="left", padx=(0, 4))
        self._count_lbl = ctk.CTkLabel(ctrl, text="0 / 0",
                                       font=ctk.CTkFont(size=12),
                                       text_color="gray")
        self._count_lbl.pack(side="right")

        # Action buttons row
        acts = ctk.CTkFrame(left, fg_color="transparent")
        acts.pack(fill="x", pady=(0, 6))
        self._prev_btn = ctk.CTkButton(
            acts, text="👁 Preview", width=90, height=28,
            fg_color="#1a3a2a", hover_color="#0a2a1a",
            state="disabled",
            command=self._preview_selected)
        self._prev_btn.pack(side="left", padx=(0, 4))
        ctk.CTkButton(acts, text="📋 Copy List", width=100, height=28,
                      fg_color="#2a2a4a", hover_color="#1a1a3a",
                      command=self._copy_checked).pack(side="left", padx=(0, 4))
        ctk.CTkButton(acts, text="📥 Paste & Select", width=140, height=28,
                      fg_color="#2a3a2a", hover_color="#1a2a1a",
                      command=self._paste_select).pack(side="left")

        # Treeview
        tf = ctk.CTkFrame(left, fg_color=_BG_TABLE, corner_radius=6)
        tf.pack(fill="both", expand=True)
        cols = ("check", "tag", "name", "ifc_class", "type_name", "prefix", "parts")
        self._tree = ttk.Treeview(tf, columns=cols, show="headings",
                                  selectmode="browse", style="T.Treeview")
        for col, hdr_txt, w, stretch in [
            ("check",     "",             44, False),
            ("tag",       "Tag / Mark",  150, False),
            ("name",      "Name",        200, True),
            ("ifc_class", "IFC Class",   140, False),
            ("type_name", "Type",        160, True),
            ("prefix",    "Prefix",      140, False),
            ("parts",     "Parts",        54, False),
        ]:
            self._tree.heading(col, text=hdr_txt, anchor="w")
            self._tree.column(col, width=w, minwidth=w, stretch=stretch)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True, padx=2, pady=2)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Button-1>", self._on_click)

        # Sash
        ctk.CTkFrame(split, width=1, fg_color="#2a2a2a"
                     ).grid(row=0, column=1, sticky="ns")

        # Properties panel
        right = ctk.CTkFrame(split, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(right, text="Element Properties",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=_ACCENT, anchor="w").pack(fill="x", pady=(0, 6))
        self._prop_box = ctk.CTkScrollableFrame(right, fg_color="#1a1a1a",
                                                corner_radius=6)
        self._prop_box.pack(fill="both", expand=True)
        ctk.CTkLabel(self._prop_box,
                     text="Select an element\nto see its properties.",
                     font=ctk.CTkFont(size=12), text_color="#446688").pack(pady=40)

        # ── Bottom ────────────────────────────────────────────────────
        self._div(wrap, pady=(8, 4))

        self._status_lbl = ctk.CTkLabel(
            wrap, text="Step 1 — Browse an IFC file (scan runs automatically).",
            font=ctk.CTkFont(size=12), text_color="gray", anchor="w")
        self._status_lbl.pack(fill="x", pady=(0, 4))

        self._progress = ctk.CTkProgressBar(wrap, height=12, corner_radius=4)
        self._progress.set(0)
        self._progress.pack(fill="x")

        btnrow = ctk.CTkFrame(wrap, fg_color="transparent")
        btnrow.pack(fill="x", pady=8)
        self._convert_btn = ctk.CTkButton(
            btnrow, text="▶  Convert Selected  (0)",
            font=ctk.CTkFont(size=14, weight="bold"), height=40,
            fg_color=_ACCENT, hover_color=_ACCENT_DARK, state="disabled",
            command=self._start_conversion)
        self._convert_btn.pack(side="left", expand=True, fill="x", padx=(0, 8))
        self._cancel_btn = ctk.CTkButton(
            btnrow, text="✕  Cancel",
            font=ctk.CTkFont(size=13), height=40,
            fg_color="#3a3a3a", hover_color="#222", state="disabled",
            command=self._cancel_conversion)
        self._cancel_btn.pack(side="left", expand=True, fill="x")

        self._div(wrap, pady=(4, 2))
        ctk.CTkLabel(wrap, text="Log", font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").pack(fill="x")
        self._log_box = ctk.CTkTextbox(wrap, height=80, font=_FONT_MONO, wrap="word")
        self._log_box.pack(fill="x", pady=(2, 0))
        self._log_box.configure(state="disabled")

    @staticmethod
    def _div(parent, pady=6) -> None:
        ctk.CTkFrame(parent, height=1, fg_color="#252525").pack(fill="x", pady=pady)

    # ── File dialogs ──────────────────────────────────────────────────────────

    def _browse_ifc(self) -> None:
        path = filedialog.askopenfilename(
            title="Select IFC File",
            filetypes=[("IFC Files", "*.ifc *.IFC"), ("All Files", "*.*")])
        if path:
            self._ifc_path.set(path)
            if not self._out_dir.get():
                self._out_dir.set(os.path.dirname(path))
            self._scan()

    def _browse_outdir(self) -> None:
        d = filedialog.askdirectory(title="Select Output Folder")
        if d:
            self._out_dir.set(d)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _scan(self) -> None:
        ifc = self._ifc_path.get().strip()
        if not ifc or not os.path.isfile(ifc):
            messagebox.showerror("Not found", "Please select a valid IFC file first.")
            return
        self._scan_btn.configure(state="disabled", text="Scanning…")
        self._progress.set(0)
        self._ifc_model = None
        self._all_rows  = []
        self._checked.clear()
        self._clear_tree()
        self._clear_props()
        self._set_status("Scanning IFC…")

        def _run():
            try:
                model, rows = scan_ifc(
                    ifc,
                    status_cb=lambda t: self.after(0, self._set_status, t),
                    progress_cb=lambda p: self.after(0, self._progress.set, p/100),
                )
                self.after(0, self._on_scan_done, model, rows)
            except Exception as exc:
                self.after(0, self._on_scan_done, None, None, str(exc))

        threading.Thread(target=_run, daemon=True).start()

    def _on_scan_done(self, model, rows, error=None) -> None:
        self._scan_btn.configure(state="normal", text="▶  Scan IFC")
        if error:
            messagebox.showerror("Scan failed", error)
            return
        self._ifc_model = model
        self._all_rows  = rows
        self._populate_tree(rows)
        self._set_status(f"Found {len(rows)} elements — select then Convert.")
        self._log(f"Scanned: {len(rows)} elements.")

    # ── Tree ──────────────────────────────────────────────────────────────────

    def _clear_tree(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)

    def _populate_tree(self, rows: list[dict]) -> None:
        self._clear_tree()
        for r in rows:
            n = r.get("n_parts", 0)
            chk = "☑" if r["guid"] in self._checked else "☐"
            display_mark = r.get("prefix") or r["tag"]
            self._tree.insert("", "end", iid=r["guid"],
                              values=(chk, display_mark, r["name"],
                                      r["ifc_class"], r["type_name"],
                                      r.get("prefix", ""),
                                      f"[{n}]" if n else ""))
        self._update_count()

    def _apply_filter(self) -> None:
        term = self._search.get().strip().lower()
        filtered = [
            r for r in self._all_rows
            if not term
            or term in r["tag"].lower()
            or term in r["name"].lower()
            or term in r["ifc_class"].lower()
            or term in r["type_name"].lower()
            or term in r.get("description", "").lower()
            or term in r.get("predefined_type", "").lower()
            or term in r.get("material", "").lower()
            or term in r.get("prefix", "").lower()
            or term in r.get("reference", "").lower()
        ]
        self._populate_tree(filtered)

    def _on_click(self, event) -> None:
        """Toggle checkbox when the check column is clicked."""
        col = self._tree.identify_column(event.x)
        row = self._tree.identify_row(event.y)
        if row and col == "#1":   # check column
            self._toggle_check(row)

    def _toggle_check(self, guid: str) -> None:
        if guid in self._checked:
            self._checked.discard(guid)
            chk = "☐"
        else:
            self._checked.add(guid)
            chk = "☑"
        vals = list(self._tree.item(guid, "values"))
        vals[0] = chk
        self._tree.item(guid, values=vals)
        self._update_count()

    def _check_all(self) -> None:
        for guid in self._tree.get_children():
            self._checked.add(guid)
            vals = list(self._tree.item(guid, "values"))
            vals[0] = "☑"
            self._tree.item(guid, values=vals)
        self._update_count()

    def _check_none(self) -> None:
        for guid in self._tree.get_children():
            self._checked.discard(guid)
            vals = list(self._tree.item(guid, "values"))
            vals[0] = "☐"
            self._tree.item(guid, values=vals)
        self._update_count()

    def _update_count(self) -> None:
        checked = len(self._checked)
        total   = len(self._tree.get_children())
        self._count_lbl.configure(text=f"{checked} checked / {total} shown")
        self._convert_btn.configure(
            text=f"▶  Convert Checked  ({checked})",
            state="normal" if checked > 0 else "disabled")
        sel = self._tree.selection()
        self._prev_btn.configure(
            state="normal" if len(sel) == 1 else "disabled")

    def _copy_checked(self) -> None:
        """Copy all checked rows to clipboard as TSV (paste-ready for Excel)."""
        rows = [r for r in self._all_rows if r["guid"] in self._checked]
        if not rows:
            messagebox.showinfo("Nothing checked", "Check at least one element first.")
            return
        header = "\t".join(["Tag", "Prefix", "Name", "IFC Class",
                             "Predefined Type", "Type", "Reference", "Material", "Description"])
        lines = [header]
        for r in rows:
            lines.append("\t".join([
                r.get("tag",             ""),
                r.get("prefix",          ""),
                r.get("name",            ""),
                r.get("ifc_class",       ""),
                r.get("predefined_type", ""),
                r.get("type_name",       ""),
                r.get("reference",       ""),
                r.get("material",        ""),
                r.get("description",     ""),
            ]))
        tsv = "\n".join(lines)
        self.clipboard_clear()
        self.clipboard_append(tsv)
        self._set_status(f"Copied {len(rows)} row(s) to clipboard — paste into Excel.")

    def _paste_select(self) -> None:
        """Open a dialog — paste marks/tags, auto-check all matching elements."""
        if not self._all_rows:
            messagebox.showinfo("No data", "Scan an IFC file first.")
            return

        dlg = tk.Toplevel(self)
        dlg.title("Paste & Select")
        dlg.geometry("440x360")
        dlg.configure(bg="#1a1a1a")
        dlg.resizable(True, True)
        dlg.grab_set()

        # ── pack bottom items FIRST so they're never pushed off-screen ──
        btn_row = tk.Frame(dlg, bg="#1a1a1a")
        btn_row.pack(side="bottom", fill="x", padx=14, pady=10)

        result_lbl = tk.Label(dlg, text="", bg="#1a1a1a", fg="#7ab8d4",
                              font=("Segoe UI", 10))
        result_lbl.pack(side="bottom", anchor="w", padx=14)

        first_only_var = tk.BooleanVar(value=False)
        opt_row = tk.Frame(dlg, bg="#1a1a1a")
        opt_row.pack(side="bottom", anchor="w", padx=14, pady=(0, 2))
        tk.Checkbutton(opt_row, text="First match only (skip duplicates)",
                       variable=first_only_var,
                       bg="#1a1a1a", fg="#dce1e7", selectcolor="#111111",
                       activebackground="#1a1a1a", activeforeground="#dce1e7",
                       font=("Segoe UI", 10)).pack(side="left")

        # ── label + text fill remaining top space ─────────────────────
        tk.Label(dlg,
                 text="Paste marks / tags below\n(one per line, or comma / tab / semicolon separated):",
                 bg="#1a1a1a", fg="#dce1e7",
                 font=("Segoe UI", 11), justify="left").pack(anchor="w", padx=14, pady=(14, 6))

        txt = tk.Text(dlg, bg="#111111", fg="#dce1e7",
                      insertbackground="#dce1e7",
                      font=("Consolas", 11), relief="flat", wrap="word")
        txt.pack(fill="both", expand=True, padx=14)

        # Try pre-filling from clipboard
        try:
            clip = self.clipboard_get()
            if clip.strip():
                txt.insert("1.0", clip.strip())
        except Exception:
            pass

        def _apply():
            import re as _re
            raw = txt.get("1.0", "end").strip()
            tokens = {t.strip().lower() for t in _re.split(r"[\n,\t;]+", raw) if t.strip()}
            if not tokens:
                result_lbl.configure(text="Nothing to match.")
                return

            first_only = first_only_var.get()
            seen_tokens: set[str] = set()
            matched = 0
            for r in self._all_rows:
                matched_token = None
                for tok in (r["tag"].lower(),
                            r.get("prefix", "").lower(),
                            r["name"].lower(),
                            r.get("reference", "").lower()):
                    if tok and tok in tokens:
                        matched_token = tok
                        break
                if matched_token is None:
                    continue
                if first_only and matched_token in seen_tokens:
                    continue
                seen_tokens.add(matched_token)
                self._checked.add(r["guid"])
                matched += 1

            self._apply_filter()
            result_lbl.configure(text=f"Matched and checked {matched} element(s).")
            self._update_count()

        tk.Button(btn_row, text="  Apply  ", bg=_ACCENT, fg="#ffffff",
                  activebackground=_ACCENT_DARK, relief="flat",
                  font=("Segoe UI", 11, "bold"), cursor="hand2",
                  command=_apply).pack(side="left", padx=(0, 8), ipady=6, ipadx=12)
        tk.Button(btn_row, text="  Close  ", bg="#333333", fg="#dce1e7",
                  activebackground="#222222", relief="flat",
                  font=("Segoe UI", 11), cursor="hand2",
                  command=dlg.destroy).pack(side="left", ipady=6, ipadx=12)

    # ── Selection → properties ────────────────────────────────────────────────

    def _on_select(self, _=None) -> None:
        self._update_count()
        sel = self._tree.selection()
        if len(sel) == 1:
            threading.Thread(target=self._fetch_props, args=(sel[0],),
                             daemon=True).start()
        else:
            self.after(0, self._clear_props)

    def _fetch_props(self, guid: str) -> None:
        if self._ifc_model is None:
            return
        d = get_element_details(self._ifc_model, guid)
        self.after(0, self._render_props, d)

    def _clear_props(self) -> None:
        for w in self._prop_box.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._prop_box,
                     text="Select an element\nto see its properties.",
                     font=ctk.CTkFont(size=12), text_color="#446688").pack(pady=40)

    def _show_multi(self, count: int) -> None:
        for w in self._prop_box.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._prop_box,
                     text=f"{count} elements selected.",
                     font=ctk.CTkFont(size=12), text_color="#446688").pack(pady=30)

    def _render_props(self, d: dict) -> None:
        for w in self._prop_box.winfo_children():
            w.destroy()

        def row(key, val, kc=_PROP_KEY):
            if not val:
                return
            fr = ctk.CTkFrame(self._prop_box, fg_color="transparent")
            fr.pack(fill="x", pady=1)
            ctk.CTkLabel(fr, text=f"{key}:",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=kc, width=130, anchor="w").pack(side="left")
            ctk.CTkLabel(fr, text=str(val),
                         font=ctk.CTkFont(size=11), text_color=_FG_TABLE,
                         anchor="w", wraplength=220, justify="left"
                         ).pack(side="left", fill="x", expand=True)

        def sec(title):
            ctk.CTkFrame(self._prop_box, height=1, fg_color="#2a3a4a"
                         ).pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(self._prop_box, text=title,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=_PROP_SECT, anchor="w").pack(fill="x")

        sec("IFC Identity")
        row("Tag / Mark",      d.get("tag", ""))
        row("GUID",            d.get("guid", ""))
        row("Name",            d.get("name", ""))
        row("Description",     d.get("description", ""))
        row("IFC Element",     d.get("ifc_class", ""))
        row("Predefined Type", d.get("predefined_type", ""))
        row("Type",            d.get("type_name", ""))
        row("Material",        d.get("material", ""))
        sec("Context")
        row("Phase",  d.get("phase", ""))
        row("Layer",  d.get("layer", ""))
        row("Prefix", d.get("prefix", ""))
        row("Model",  d.get("model_ref", ""))
        row("Detail", d.get("detail", ""))
        for pname, props in sorted(d.get("psets", {}).items()):
            if not isinstance(props, dict):
                continue
            sec(pname)
            for k, v in sorted(props.items()):
                if k == "id":
                    continue
                row(k, str(v) if v is not None else "", kc="#9ab8cc")

    # ── 3-D Preview ───────────────────────────────────────────────────────────

    def _preview_selected(self) -> None:
        sel = self._tree.selection()
        if len(sel) != 1:
            return
        guid = sel[0]
        if self._ifc_model is None:
            messagebox.showinfo("Not scanned", "Scan the IFC file first.")
            return

        # Show a loading window immediately
        loading = tk.Toplevel(self)
        loading.title("Preview — Loading…")
        loading.geometry("400x120")
        loading.configure(bg="#111111")
        tk.Label(loading, text="Extracting geometry…",
                 bg="#111111", fg="#7ab8d4",
                 font=("Segoe UI", 13)).pack(expand=True)
        self.update_idletasks()

        def _run():
            geo = get_preview_geometry(self._ifc_model, guid)
            self.after(0, _open, geo)

        def _open(geo):
            loading.destroy()
            PreviewWindow(self, geo)

        threading.Thread(target=_run, daemon=True).start()

    # ── Conversion ────────────────────────────────────────────────────────────

    def _start_conversion(self) -> None:
        ifc   = self._ifc_path.get().strip()
        outd  = self._out_dir.get().strip()
        guids = list(self._checked)

        if not ifc or not os.path.isfile(ifc):
            messagebox.showerror("Error", "IFC file not found.")
            return
        if not outd:
            messagebox.showerror("Error", "Please choose an output folder.")
            return
        if not guids:
            messagebox.showerror("Error", "Check at least one element.")
            return

        self._convert_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal")
        self._progress.set(0)
        self._log("─" * 52)
        self._log(f"IFC    : {ifc}")
        self._log(f"Folder : {outd}")
        self._log(f"Items  : {len(guids)} → one .dxf file per tag")
        self._log("─" * 52)

        self._engine = ConversionEngine(
            ifc_path    = ifc,
            output_dir  = outd,
            guids       = guids,
            progress_cb = lambda p: self.after(0, self._progress.set, p/100),
            status_cb   = lambda t: self.after(0, self._cb_status, t),
            complete_cb = lambda ok, m: self.after(0, self._cb_complete, ok, m),
        )
        threading.Thread(target=self._engine.run, daemon=True).start()

    def _cancel_conversion(self) -> None:
        if self._engine:
            self._engine.cancel()
        self._cancel_btn.configure(state="disabled")
        self._set_status("Cancelling…")

    def _cb_status(self, text: str) -> None:
        self._set_status(text)
        self._log(text)

    def _cb_complete(self, success: bool, msg: str) -> None:
        self._set_status(msg.split("\n")[0])
        self._log(""); self._log(msg)
        self._convert_btn.configure(state="normal")
        self._cancel_btn.configure(state="disabled")
        if success:
            self._progress.set(1.0)
            messagebox.showinfo("Done", msg)
        else:
            messagebox.showerror("Failed", msg)

    def _set_status(self, text: str) -> None:
        self._status_lbl.configure(text=text)

    def _log(self, text: str) -> None:
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")
