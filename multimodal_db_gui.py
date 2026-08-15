import os
import sqlite3
import sys
from pathlib import Path
from tkinter import ttk

import numpy as np
from PIL import Image, ImageOps, ImageTk
from tkinter import *
from PIL import Image  # noqa: F811 - tkinter's own Image class shadows PIL's; restore it

try:
    import rasterio
except Exception:
    rasterio = None

try:
    import shapefile as pyshp
except Exception:
    pyshp = None

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except Exception:
    Figure = None
    FigureCanvasTkAgg = None

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "multimodal_base.sqlite"


class MultimodalDBApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Base multimodale agroécologique")
        self.root.geometry("1200x800")
        self.root.minsize(1100, 700)

        self.conn = sqlite3.connect(DB_PATH, timeout=60)
        self.tree_cache = {}
        self.geotiff_band_options = {}
        self._current_geotiff_path = None

        self.topbar = Frame(root, padx=12, pady=10, bg="#f3f5f8")
        self.topbar.pack(fill="x")

        Label(self.topbar, text="Base de données SQLite", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        Label(self.topbar, text=f"Fichier: {DB_PATH}", fg="#4a4a4a").pack(anchor="w")
        Button(self.topbar, text="Fenêtre de présentation", command=self.open_presentation_window, bg="#dfeeff", fg="#123", relief="raised").pack(anchor="e", pady=(6, 0))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.build_overview_tab()
        self.build_climate_tab()
        self.build_soils_tab()
        self.build_agriculture_tab()
        self.build_spectral_tab()
        self.build_geotiff_tab()
        self.build_articles_tab()

        self.refresh_all()

    def open_presentation_window(self):
        PresentationWindow(self.root, self.conn)

    def build_overview_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Vue d'ensemble")

        left = ttk.Frame(frame, padding=10)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="Tables disponibles").pack(anchor="w")
        self.table_listbox = Listbox(left, width=30, height=20, exportselection=False)
        self.table_listbox.pack(fill="y", pady=(5, 10))
        self.table_listbox.bind("<<ListboxSelect>>", self.on_table_select)

        right = ttk.Frame(frame, padding=10)
        right.pack(side="left", fill="both", expand=True)

        ttk.Label(right, text="Statistiques globales").pack(anchor="w")
        self.overview_stats = Text(right, height=28, width=90, wrap="word")
        self.overview_stats.pack(fill="both", expand=True, pady=(5, 0))

        self.overview_tree = ttk.Treeview(right, columns=("colonne", "valeur"), show="headings")
        self.overview_tree.heading("colonne", text="Colonne")
        self.overview_tree.heading("valeur", text="Valeur")
        self.overview_tree.column("colonne", width=220, anchor="w")
        self.overview_tree.column("valeur", width=160, anchor="e")
        self.overview_tree.pack(fill="both", expand=True, pady=(10, 0))

    def build_climate_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Climat")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        self.climate_stats = Text(top, height=8, width=110, wrap="word")
        self.climate_stats.pack(fill="x")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.climate_table = ttk.Treeview(table)
        self.climate_table.pack(fill="both", expand=True)

    def build_soils_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Pédologie")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        self.soils_stats = Text(top, height=8, width=110, wrap="word")
        self.soils_stats.pack(fill="x")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.soils_table = ttk.Treeview(table)
        self.soils_table.pack(fill="both", expand=True)

    def build_agriculture_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Agriculture")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        self.agri_stats = Text(top, height=8, width=110, wrap="word")
        self.agri_stats.pack(fill="x")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.agri_table = ttk.Treeview(table)
        self.agri_table.pack(fill="both", expand=True)

    def build_spectral_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Indices spectraux")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        self.spectral_stats = Text(top, height=8, width=110, wrap="word")
        self.spectral_stats.pack(fill="x")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.spectral_table = ttk.Treeview(table)
        self.spectral_table.pack(fill="both", expand=True)

    def build_geotiff_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Fichiers géospatiaux")

        geo_notebook = ttk.Notebook(frame)
        geo_notebook.pack(fill="both", expand=True)

        self.build_raster_subtab(geo_notebook)
        self.build_vector_subtab(geo_notebook)

    def build_raster_subtab(self, geo_notebook):
        frame = ttk.Frame(geo_notebook)
        geo_notebook.add(frame, text="Raster (GeoTIFF)")

        left = ttk.Frame(frame, padding=10)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Fichiers GeoTIFF").pack(anchor="w")
        self.geotiff_list = Listbox(left, width=34, height=22, exportselection=False)
        self.geotiff_list.pack(fill="y", pady=(5, 0))
        self.geotiff_list.bind("<<ListboxSelect>>", self.on_geotiff_select)

        right = ttk.Frame(frame, padding=10)
        right.pack(side="left", fill="both", expand=True)

        selector_row = ttk.Frame(right)
        selector_row.pack(fill="x", pady=(0, 6))
        ttk.Label(selector_row, text="Indice / bande à afficher:").pack(side="left")
        self.geotiff_index_var = StringVar()
        self.geotiff_index_combo = ttk.Combobox(selector_row, textvariable=self.geotiff_index_var, state="readonly", width=32)
        self.geotiff_index_combo.pack(side="left", padx=(6, 0))
        self.geotiff_index_combo.bind("<<ComboboxSelected>>", self.on_geotiff_index_choice)

        self.geotiff_preview = Label(right, borderwidth=2, relief="solid", bg="white")
        self.geotiff_preview.pack(fill="both", expand=True)

        self.geotiff_info = Text(right, height=8, wrap="word")
        self.geotiff_info.pack(fill="x", pady=(10, 0))

        ttk.Label(right, text="Indices spectraux associés (données tabulaires)").pack(anchor="w", pady=(8, 0))
        self.geotiff_spectral_tree = ttk.Treeview(right, columns=("index_name", "date", "min", "max", "mean"), show="headings", height=5)
        for col, width in (("index_name", 90), ("date", 90), ("min", 90), ("max", 90), ("mean", 90)):
            self.geotiff_spectral_tree.heading(col, text=col)
            self.geotiff_spectral_tree.column(col, width=width, anchor="center")
        self.geotiff_spectral_tree.pack(fill="x", pady=(4, 0))

    def build_vector_subtab(self, geo_notebook):
        frame = ttk.Frame(geo_notebook)
        geo_notebook.add(frame, text="Vecteur (couches géospatiales)")

        left = ttk.Frame(frame, padding=10)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Couches vectorielles").pack(anchor="w")
        self.vector_list = Listbox(left, width=34, height=22, exportselection=False)
        self.vector_list.pack(fill="y", pady=(5, 0))
        self.vector_list.bind("<<ListboxSelect>>", self.on_vector_select)

        right = ttk.Frame(frame, padding=10)
        right.pack(side="left", fill="both", expand=True)
        self.vector_preview_frame = Frame(right, borderwidth=2, relief="solid", bg="white", height=340)
        self.vector_preview_frame.pack(fill="both", expand=True)
        self.vector_preview_label = Label(self.vector_preview_frame, bg="white", text="Sélectionnez une couche")
        self.vector_preview_label.pack(fill="both", expand=True)
        self.vector_canvas_widget = None

        self.vector_info = Text(right, height=10, wrap="word")
        self.vector_info.pack(fill="x", pady=(10, 0))

    def build_articles_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Articles & fichiers")

        top = ttk.Frame(frame)
        top.pack(fill="x", padx=10, pady=10)
        self.articles_stats = Text(top, height=8, width=110, wrap="word")
        self.articles_stats.pack(fill="x")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.articles_table = ttk.Treeview(table)
        self.articles_table.pack(fill="both", expand=True)

    def on_table_select(self, event):
        selection = self.table_listbox.curselection()
        if not selection:
            return
        table_name = self.table_listbox.get(selection[0])
        rows = self.fetch_table(table_name, limit=50)
        self.display_rows_in_tree(self.overview_tree, rows, table_name)

    def on_geotiff_select(self, event):
        selection = self.geotiff_list.curselection()
        if not selection:
            return
        item = self.geotiff_list.get(selection[0])
        geotiff_id = self.geotiff_id_by_label.get(item)
        self.display_geotiff_preview(geotiff_id or item)

    def on_geotiff_index_choice(self, event):
        if not self.geotiff_band_options:
            return
        label = self.geotiff_index_var.get()
        option = self.geotiff_band_options.get(label)
        if option is None or self._current_geotiff_path is None:
            return
        self.render_geotiff_selection(self._current_geotiff_path, option)

    def on_vector_select(self, event):
        selection = self.vector_list.curselection()
        if not selection:
            return
        item = self.vector_list.get(selection[0])
        layer_id = self.vector_id_by_label.get(item)
        self.display_vector_preview(layer_id)

    def fetch_table(self, table_name, limit=100):
        try:
            columns = self.get_columns(table_name)
            query = f"SELECT * FROM \"{table_name}\" LIMIT {limit}"
            result = self.conn.execute(query).fetchall()
            return columns, result
        except Exception as exc:
            print(f"Erreur sur table {table_name}: {exc}")
            return [], []

    def get_columns(self, table_name):
        try:
            cols = self.conn.execute(f"PRAGMA table_info(\"{table_name}\")").fetchall()
            return [c[1] for c in cols]
        except Exception:
            return []

    def display_rows_in_tree(self, tree, rows, title):
        for child in tree.get_children():
            tree.delete(child)

        columns, data = rows
        if not columns:
            return
        tree.configure(columns=columns)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=140, anchor="w")
        for record in data[:30]:
            values = ["" if v is None else str(v) for v in record]
            tree.insert("", "end", values=values)

    def set_table_view(self, tree, columns, rows):
        for child in tree.get_children():
            tree.delete(child)
        if not columns:
            return
        tree["columns"] = columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor="w")
        for row in rows:
            vals = ["" if val is None else str(val) for val in row]
            tree.insert("", "end", values=vals)

    def refresh_all(self):
        self.load_table_list()
        self.load_overview_stats()
        self.load_climate_stats()
        self.load_soils_stats()
        self.load_agriculture_stats()
        self.load_spectral_stats()
        self.load_geotiff_files()
        self.load_vector_layers()
        self.load_articles_stats()

    def load_table_list(self):
        tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        table_names = [row[0] for row in tables]
        self.table_listbox.delete(0, END)
        for name in table_names:
            self.table_listbox.insert(END, name)

    def load_overview_stats(self):
        stats = []
        for table_name, in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            count = self.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            stats.append((table_name, count))

        self.overview_stats.delete(1.0, END)
        self.overview_stats.insert(END, "Résumé de la base multimodale\n\n")
        for name, count in stats:
            self.overview_stats.insert(END, f"- {name}: {count} lignes\n")

        for child in self.overview_tree.get_children():
            self.overview_tree.delete(child)
        self.overview_tree.insert("", "end", values=("Nombre total de tables", str(len(stats))))
        self.overview_tree.insert("", "end", values=("Données climatiques", self.conn.execute("SELECT COUNT(*) FROM climate").fetchone()[0]))
        self.overview_tree.insert("", "end", values=("Données agricoles", self.conn.execute("SELECT COUNT(*) FROM agriculture").fetchone()[0]))
        self.overview_tree.insert("", "end", values=("Articles référencés", self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] if self.table_exists("articles") else 0))
        self.overview_tree.insert("", "end", values=("Fichiers article", self.conn.execute("SELECT COUNT(*) FROM article_files").fetchone()[0] if self.table_exists("article_files") else 0))

    def table_exists(self, table_name):
        result = self.conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()[0]
        return result > 0

    def load_climate_stats(self):
        if not self.table_exists("climate"):
            self.climate_stats.delete(1.0, END)
            self.climate_stats.insert(END, "Table climate absente.")
            return

        rows = self.conn.execute("SELECT COUNT(*), AVG(temperature_c), MIN(temperature_c), MAX(temperature_c), AVG(precipitation_mm), MIN(precipitation_mm), MAX(precipitation_mm) FROM climate").fetchone()
        self.climate_stats.delete(1.0, END)
        self.climate_stats.insert(END, f"Nombre de lignes: {rows[0]}\n")
        self.climate_stats.insert(END, f"Température moyenne: {rows[1] if rows[1] is not None else 'N/A'} °C\n")
        self.climate_stats.insert(END, f"Température min/max: {rows[2] if rows[2] is not None else 'N/A'} / {rows[3] if rows[3] is not None else 'N/A'} °C\n")
        self.climate_stats.insert(END, f"Précipitation moyenne: {rows[4] if rows[4] is not None else 'N/A'} mm\n")
        self.climate_stats.insert(END, f"Précipitation min/max: {rows[5] if rows[5] is not None else 'N/A'} / {rows[6] if rows[6] is not None else 'N/A'} mm")

        columns = ["id", "date", "station_name", "temperature_c", "precipitation_mm", "source", "region"]
        data = self.conn.execute("SELECT id, date, station_name, temperature_c, precipitation_mm, source, region FROM climate ORDER BY id LIMIT 50").fetchall()
        self.set_table_view(self.climate_table, columns, data)

    def load_soils_stats(self):
        if not self.table_exists("soils"):
            self.soils_stats.delete(1.0, END)
            self.soils_stats.insert(END, "Table soils absente.")
            return

        rows = self.conn.execute("SELECT COUNT(*), AVG(organic_matter), MIN(organic_matter), MAX(organic_matter), AVG(ph), MIN(ph), MAX(ph) FROM soils").fetchone()
        self.soils_stats.delete(1.0, END)
        self.soils_stats.insert(END, f"Nombre de lignes: {rows[0]}\n")
        self.soils_stats.insert(END, f"Matière organique moyenne: {rows[1] if rows[1] is not None else 'N/A'}\n")
        self.soils_stats.insert(END, f"pH moyen: {rows[4] if rows[4] is not None else 'N/A'}\n")
        self.soils_stats.insert(END, f"pH min/max: {rows[5] if rows[5] is not None else 'N/A'} / {rows[6] if rows[6] is not None else 'N/A'}")

        columns = ["id", "geom_id", "soil_type", "texture", "organic_matter", "ph", "region", "source"]
        data = self.conn.execute("SELECT id, geom_id, soil_type, texture, organic_matter, ph, region, source FROM soils ORDER BY id LIMIT 50").fetchall()
        self.set_table_view(self.soils_table, columns, data)

    def load_agriculture_stats(self):
        if not self.table_exists("agriculture"):
            self.agri_stats.delete(1.0, END)
            self.agri_stats.insert(END, "Table agriculture absente.")
            return

        rows = self.conn.execute("SELECT COUNT(*), AVG(production_tonnes), MIN(production_tonnes), MAX(production_tonnes), AVG(area_ha), MIN(area_ha), MAX(area_ha) FROM agriculture").fetchone()
        self.agri_stats.delete(1.0, END)
        self.agri_stats.insert(END, f"Nombre de lignes: {rows[0]}\n")
        self.agri_stats.insert(END, f"Production moyenne: {rows[1] if rows[1] is not None else 'N/A'} tonnes\n")
        self.agri_stats.insert(END, f"Production min/max: {rows[2] if rows[2] is not None else 'N/A'} / {rows[3] if rows[3] is not None else 'N/A'} tonnes\n")
        self.agri_stats.insert(END, f"Superficie moyenne: {rows[4] if rows[4] is not None else 'N/A'} ha\n")
        self.agri_stats.insert(END, f"Superficie min/max: {rows[5] if rows[5] is not None else 'N/A'} / {rows[6] if rows[6] is not None else 'N/A'} ha")

        columns = ["id", "year", "crop_name", "production_tonnes", "area_ha", "region", "source"]
        data = self.conn.execute("SELECT id, year, crop_name, production_tonnes, area_ha, region, source FROM agriculture ORDER BY id LIMIT 50").fetchall()
        self.set_table_view(self.agri_table, columns, data)

    def load_spectral_stats(self):
        if not self.table_exists("spectral_indices"):
            self.spectral_stats.delete(1.0, END)
            self.spectral_stats.insert(END, "Table spectral_indices absente.")
            return

        rows = self.conn.execute("SELECT index_name, COUNT(*), AVG(mean_value), MIN(mean_value), MAX(mean_value) FROM spectral_indices GROUP BY index_name ORDER BY index_name").fetchall()
        self.spectral_stats.delete(1.0, END)
        self.spectral_stats.insert(END, "Indices spectraux disponibles\n\n")
        for r in rows:
            self.spectral_stats.insert(END, f"- {r[0]}: {r[1]} valeurs, moyenne={r[2] if r[2] is not None else 'N/A'}, min={r[3] if r[3] is not None else 'N/A'}, max={r[4] if r[4] is not None else 'N/A'}\n")

        columns = ["id", "image_name", "index_name", "date", "min_value", "max_value", "mean_value", "file_path", "region", "source"]
        data = self.conn.execute("SELECT id, image_name, index_name, date, min_value, max_value, mean_value, file_path, region, source FROM spectral_indices ORDER BY id LIMIT 50").fetchall()
        self.set_table_view(self.spectral_table, columns, data)

    def load_geotiff_files(self):
        self.geotiff_list.delete(0, END)
        self.geotiff_id_by_label = {}
        if not self.table_exists("geotiff_catalog"):
            self.geotiff_info.insert(END, "Table geotiff_catalog absente.")
            return

        files = self.conn.execute(
            "SELECT id, file_name, file_path, width, height, crs, bounds, source_root, region, agro_zone, spectral_index, satellite_source, time_period, use_case FROM geotiff_catalog ORDER BY id"
        ).fetchall()
        ordered = []
        for row in files:
            geotiff_id, file_name, file_path, width, height, crs, bounds, source_root, region, agro_zone, spectral_index, satellite_source, time_period, use_case = row
            period_value = time_period or "n/a"
            region_value = region or "Sénégal"
            index_value = spectral_index or "NDVI"
            label = f"{region_value} | {period_value} | {index_value} | {file_name}"
            ordered.append((label, geotiff_id))

        ordered.sort(key=lambda x: x[0].lower())
        for label, geotiff_id in ordered:
            self.geotiff_id_by_label[label] = geotiff_id
            self.geotiff_list.insert(END, label)

        if files:
            self.display_geotiff_preview(files[0][0])

    def display_geotiff_preview(self, geotiff_id):
        if not self.table_exists("geotiff_catalog"):
            return
        if geotiff_id is None:
            return

        record = self.conn.execute(
            "SELECT id, file_name, file_path, width, height, crs, bounds, source_root, region, agro_zone, spectral_index, satellite_source, time_period, use_case FROM geotiff_catalog WHERE id=? LIMIT 1",
            (geotiff_id,),
        ).fetchone()
        if record is None:
            return

        geotiff_id, file_name, file_path, width, height, crs, bounds, source_root, region, agro_zone, spectral_index, satellite_source, time_period, use_case = record
        self.geotiff_info.delete(1.0, END)
        self.geotiff_info.insert(END, f"Nom: {file_name}\n")
        self.geotiff_info.insert(END, f"Région: {region or 'Sénégal'}\n")
        self.geotiff_info.insert(END, f"Zone agro-écologique: {agro_zone or 'Zone agro-écologique du Sénégal'}\n")
        self.geotiff_info.insert(END, f"Indice spectral (catalogue): {spectral_index or 'NDVI'}\n")
        self.geotiff_info.insert(END, f"Satellite/source: {satellite_source or source_root}\n")
        self.geotiff_info.insert(END, f"Période: {time_period or 'non renseignée'}\n")
        self.geotiff_info.insert(END, f"Utilité: {use_case or 'Suivi agroécologique'}\n")
        self.geotiff_info.insert(END, f"Chemin: {file_path}\n")
        self.geotiff_info.insert(END, f"Taille: {width} x {height}\n")
        self.geotiff_info.insert(END, f"CRS: {crs}\n")
        self.geotiff_info.insert(END, f"Bounds: {bounds}\n")
        self.geotiff_info.insert(END, f"Source racine: {source_root}\n")

        self._load_linked_spectral_indices(file_name, file_path)

        self._current_geotiff_path = file_path
        self.geotiff_band_options = self._build_band_options(file_path)
        labels = list(self.geotiff_band_options.keys())
        self.geotiff_index_combo["values"] = labels
        if not labels:
            self.geotiff_index_var.set("")
            self._clear_geotiff_preview("Aperçu indisponible\n(rasterio ou fichier manquant)")
            return

        default_label = labels[0]
        for label, option in self.geotiff_band_options.items():
            if option[0] == "formula" and option[1] == (spectral_index or "").upper():
                default_label = label
                break
        self.geotiff_index_var.set(default_label)
        self.render_geotiff_selection(file_path, self.geotiff_band_options[default_label])

    def _load_linked_spectral_indices(self, file_name, file_path):
        for child in self.geotiff_spectral_tree.get_children():
            self.geotiff_spectral_tree.delete(child)
        if not self.table_exists("spectral_indices"):
            return

        stem = Path(file_name).stem
        rows = self.conn.execute(
            "SELECT index_name, date, min_value, max_value, mean_value FROM spectral_indices "
            "WHERE image_name = ? OR file_path = ? ORDER BY date",
            (stem, file_path),
        ).fetchall()
        for index_name, date, min_value, max_value, mean_value in rows:
            self.geotiff_spectral_tree.insert("", "end", values=(index_name, date, min_value, max_value, mean_value))

    def _clear_geotiff_preview(self, message):
        self.geotiff_preview.configure(image="", text=message)
        self.geotiff_preview.image = None

    BAND_ROLE_TOKENS = {
        "red": {"red", "b04"},
        "green": {"green", "b03"},
        "blue": {"blue", "b02"},
        "nir": {"nir", "b08"},
        "swir1": {"swir1", "b11"},
        "swir2": {"swir2", "b12"},
    }

    INDEX_FORMULAS = {
        "NDVI": ("nir", "red"),
        "NDWI": ("green", "nir"),
        "EVI": ("nir", "red", "blue"),
        "SAVI": ("nir", "red"),
        "NDBI": ("swir1", "nir"),
        "MNDWI": ("green", "swir1"),
    }

    def _detect_band_roles(self, descriptions):
        roles = {}
        for i, desc in enumerate(descriptions or [], start=1):
            if not desc:
                continue
            token = "".join(ch for ch in desc.lower() if ch.isalnum())
            for role, tokens in self.BAND_ROLE_TOKENS.items():
                if token in tokens and role not in roles:
                    roles[role] = i
        return roles

    def _build_band_options(self, file_path):
        options = {}
        if rasterio is None or not file_path or not os.path.exists(file_path):
            return options

        try:
            with rasterio.open(file_path) as src:
                count = src.count
                descriptions = src.descriptions
        except Exception:
            return options

        options["Aperçu automatique (RVB/gris)"] = ("auto", None)
        for i in range(1, count + 1):
            name = descriptions[i - 1] if descriptions and i - 1 < len(descriptions) and descriptions[i - 1] else f"bande {i}"
            options[f"Bande {i} ({name})"] = ("band", i)

        roles = self._detect_band_roles(descriptions)
        for index_name, needed_roles in self.INDEX_FORMULAS.items():
            if all(role in roles for role in needed_roles):
                options[f"Indice: {index_name}"] = ("formula", index_name, roles)

        return options

    def render_geotiff_selection(self, file_path, option):
        if rasterio is None or not file_path or not os.path.exists(file_path):
            self._clear_geotiff_preview("Aperçu indisponible\n(rasterio ou fichier manquant)")
            return

        kind = option[0]
        try:
            with rasterio.open(file_path) as src:
                if kind == "band":
                    band_index = option[1]
                    array = src.read(band_index).astype(np.float32)
                    pil_image = self._normalize_to_gray_image(array)
                elif kind == "formula":
                    index_name = option[1]
                    roles = option[2]
                    bands = {role: src.read(band_idx).astype(np.float32) for role, band_idx in roles.items()}
                    values = self._compute_spectral_index(index_name, bands)
                    pil_image = self._normalize_to_gray_image(values, colorize=True)
                    stats_text = f"Indice {index_name} calculé — min={np.nanmin(values):.3f}, max={np.nanmax(values):.3f}, moyenne={np.nanmean(values):.3f}"
                    self.geotiff_info.insert(END, f"\n{stats_text}\n")
                else:
                    arr = src.read()
                    if arr.size == 0:
                        raise ValueError("Raster vide")
                    if arr.ndim == 3 and arr.shape[0] >= 3:
                        rgb = arr[:3].astype(np.float32)
                        rgb = np.clip(rgb, 0, np.nanmax(rgb))
                        rgb = (rgb - np.nanmin(rgb)) / (np.nanmax(rgb) - np.nanmin(rgb) + 1e-8)
                        rgb = np.nan_to_num(rgb, nan=0.0)
                        rgb = (rgb * 255).astype(np.uint8)
                        rgb = np.moveaxis(rgb, 0, -1)
                        pil_image = Image.fromarray(rgb)
                    else:
                        band = arr[0] if arr.ndim == 3 else arr
                        pil_image = self._normalize_to_gray_image(band.astype(np.float32))

            if pil_image.mode != 'RGB':
                pil_image = ImageOps.autocontrast(pil_image.convert('L')).convert('RGB')
            pil_image = pil_image.resize((600, 400), Image.Resampling.LANCZOS)
            img_tk = ImageTk.PhotoImage(pil_image)
            self.geotiff_preview.configure(image=img_tk, text="")
            self.geotiff_preview.image = img_tk
        except Exception as exc:
            self._clear_geotiff_preview(f"Aperçu non disponible\n{exc}")

    def _normalize_to_gray_image(self, array, colorize=False):
        norm = array.astype(np.float32)
        if norm.size:
            norm = (norm - np.nanmin(norm)) / (np.nanmax(norm) - np.nanmin(norm) + 1e-8)
            norm = np.nan_to_num(norm, nan=0.0)
        norm_u8 = (norm * 255).astype(np.uint8)
        if colorize:
            return Image.fromarray(norm_u8, mode="L").convert("RGB")
        return Image.fromarray(norm_u8)

    def _compute_spectral_index(self, index_name, bands):
        eps = 1e-8
        if index_name == "NDVI":
            nir, red = bands["nir"], bands["red"]
            return (nir - red) / (nir + red + eps)
        if index_name == "NDWI":
            green, nir = bands["green"], bands["nir"]
            return (green - nir) / (green + nir + eps)
        if index_name == "EVI":
            nir, red, blue = bands["nir"], bands["red"], bands["blue"]
            return 2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1 + eps)
        if index_name == "SAVI":
            nir, red = bands["nir"], bands["red"]
            return ((nir - red) / (nir + red + 0.5 + eps)) * 1.5
        if index_name == "NDBI":
            swir1, nir = bands["swir1"], bands["nir"]
            return (swir1 - nir) / (swir1 + nir + eps)
        if index_name == "MNDWI":
            green, swir1 = bands["green"], bands["swir1"]
            return (green - swir1) / (green + swir1 + eps)
        raise ValueError(f"Indice inconnu: {index_name}")

    def load_vector_layers(self):
        self.vector_list.delete(0, END)
        self.vector_id_by_label = {}
        if not self.table_exists("geospatial_layers"):
            self.vector_info.delete(1.0, END)
            self.vector_info.insert(END, "Table geospatial_layers absente.")
            return

        rows = self.conn.execute(
            "SELECT id, layer_name, geometry_type, file_path, crs, region, source FROM geospatial_layers ORDER BY layer_name"
        ).fetchall()

        ordered = []
        for row in rows:
            layer_id, layer_name, geometry_type, file_path, crs, region, source = row
            label = f"{region or 'Sénégal'} | {layer_name} | {source or ''}"
            ordered.append((label, layer_id))

        ordered.sort(key=lambda x: x[0].lower())
        for label, layer_id in ordered:
            self.vector_id_by_label[label] = layer_id
            self.vector_list.insert(END, label)

        if rows:
            self.display_vector_preview(rows[0][0])

    def _index_local_shapefiles(self):
        if hasattr(self, "_shapefile_index"):
            return self._shapefile_index
        index = {}
        skip_dirs = {".venv", ".venv_tf", "__pycache__", ".git", "node_modules"}
        for shp_path in PROJECT_ROOT.rglob("*.shp"):
            if any(part in skip_dirs for part in shp_path.parts):
                continue
            index.setdefault(shp_path.stem.lower(), shp_path)
        self._shapefile_index = index
        return index

    def resolve_vector_source(self, layer_name, file_path):
        """Retourne un objet shapefile.Reader ouvert pour la couche demandée, ou None."""
        if pyshp is None:
            return None

        index = self._index_local_shapefiles()
        local_path = index.get((layer_name or "").lower())
        if local_path and local_path.exists():
            try:
                return pyshp.Reader(str(local_path))
            except Exception:
                pass

        if file_path and file_path.lower().endswith(".zip") and os.path.exists(file_path):
            try:
                with zipfile.ZipFile(file_path) as zf:
                    names = zf.namelist()
                    target = None
                    for name in names:
                        if name.lower().endswith(".shp") and Path(name).stem.lower() == (layer_name or "").lower():
                            target = Path(name).with_suffix("")
                            break
                    if target is not None:
                        shp_bytes = io.BytesIO(zf.read(str(target) + ".shp"))
                        dbf_name = str(target) + ".dbf"
                        dbf_bytes = io.BytesIO(zf.read(dbf_name)) if dbf_name in names else None
                        shx_name = str(target) + ".shx"
                        shx_bytes = io.BytesIO(zf.read(shx_name)) if shx_name in names else None
                        return pyshp.Reader(shp=shp_bytes, dbf=dbf_bytes, shx=shx_bytes)
            except Exception:
                pass
        return None

    def display_vector_preview(self, layer_id):
        if not self.table_exists("geospatial_layers") or layer_id is None:
            return

        record = self.conn.execute(
            "SELECT id, layer_name, geometry_type, file_path, crs, region, source FROM geospatial_layers WHERE id=? LIMIT 1",
            (layer_id,),
        ).fetchone()
        if record is None:
            return

        layer_id, layer_name, geometry_type, file_path, crs, region, source = record
        self.vector_info.delete(1.0, END)
        self.vector_info.insert(END, f"Nom de la couche: {layer_name}\n")
        self.vector_info.insert(END, f"Type de géométrie: {geometry_type}\n")
        self.vector_info.insert(END, f"CRS: {crs}\n")
        self.vector_info.insert(END, f"Région: {region or 'Sénégal'}\n")
        self.vector_info.insert(END, f"Source: {source}\n")
        self.vector_info.insert(END, f"Chemin: {file_path}\n")

        reader = self.resolve_vector_source(layer_name, file_path)
        if reader is None:
            self.vector_info.insert(END, "\nAperçu et attributs indisponibles (fichier introuvable ou pyshp manquant).\n")
            self._clear_vector_canvas("Aperçu indisponible")
            return

        try:
            shapes = reader.shapes()
            fields = [f[0] for f in reader.fields[1:]]
            self.vector_info.insert(END, f"Nombre d'entités: {len(shapes)}\n")
            self.vector_info.insert(END, f"Champs attributaires: {', '.join(fields)}\n")
            if shapes:
                self.vector_info.insert(END, f"Emprise (bbox): {shapes[0].bbox if hasattr(shapes[0], 'bbox') else 'N/A'}\n")
                full_bbox = reader.bbox
                self.vector_info.insert(END, f"Emprise globale: {full_bbox}\n")
        except Exception as exc:
            self.vector_info.insert(END, f"\nErreur de lecture des attributs: {exc}\n")

        self._render_vector_shapes(reader, layer_name)

    def _clear_vector_canvas(self, message=""):
        if self.vector_canvas_widget is not None:
            self.vector_canvas_widget.destroy()
            self.vector_canvas_widget = None
        self.vector_preview_label.pack(fill="both", expand=True)
        self.vector_preview_label.configure(text=message, image="")

    def _render_vector_shapes(self, reader, layer_name):
        if Figure is None or FigureCanvasTkAgg is None:
            self._clear_vector_canvas("matplotlib indisponible pour l'aperçu")
            return

        try:
            shapes = reader.shapes()
            if not shapes:
                self._clear_vector_canvas("Aucune géométrie à afficher")
                return

            figure = Figure(figsize=(5.5, 4), dpi=100)
            ax = figure.add_subplot(111)
            for shape in shapes:
                points = shape.points
                if not points:
                    continue
                parts = list(shape.parts) + [len(points)]
                for i in range(len(parts) - 1):
                    segment = points[parts[i]:parts[i + 1]]
                    if not segment:
                        continue
                    xs = [p[0] for p in segment]
                    ys = [p[1] for p in segment]
                    if shape.shapeType in (1, 11, 21):  # points
                        ax.scatter(xs, ys, s=8, c="#1f6feb")
                    else:
                        ax.plot(xs, ys, linewidth=0.8, color="#1f6feb")
                        if shape.shapeType in (5, 15, 25):  # polygons
                            ax.fill(xs, ys, alpha=0.3, color="#63a4ff")

            ax.set_title(layer_name, fontsize=10)
            ax.set_aspect("equal", adjustable="datalim")
            figure.tight_layout()

            self.vector_preview_label.pack_forget()
            if self.vector_canvas_widget is not None:
                self.vector_canvas_widget.destroy()

            canvas = FigureCanvasTkAgg(figure, master=self.vector_preview_frame)
            canvas.draw()
            self.vector_canvas_widget = canvas.get_tk_widget()
            self.vector_canvas_widget.pack(fill="both", expand=True)
        except Exception as exc:
            self._clear_vector_canvas(f"Aperçu non disponible\n{exc}")

    def load_articles_stats(self):
        if not self.table_exists("articles") or not self.table_exists("article_files"):
            self.articles_stats.delete(1.0, END)
            self.articles_stats.insert(END, "Tables article absentes.")
            return

        total_articles = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        total_files = self.conn.execute("SELECT COUNT(*) FROM article_files").fetchone()[0]
        cat_summary = self.conn.execute("SELECT category, COUNT(*) FROM article_files GROUP BY category ORDER BY COUNT(*) DESC LIMIT 10").fetchall()
        self.articles_stats.delete(1.0, END)
        self.articles_stats.insert(END, f"Articles: {total_articles}\n")
        self.articles_stats.insert(END, f"Fichiers: {total_files}\n\n")
        for category, count in cat_summary:
            self.articles_stats.insert(END, f"- {category}: {count}\n")

        columns = ["id", "article_id", "file_name", "relative_path", "extension", "category", "is_python", "file_size_bytes", "sha256"]
        data = self.conn.execute("SELECT id, article_id, file_name, relative_path, extension, category, is_python, file_size_bytes, sha256 FROM article_files ORDER BY id LIMIT 50").fetchall()
        self.set_table_view(self.articles_table, columns, data)


class PresentationWindow:
    def __init__(self, master, conn):
        self.window = Toplevel(master)
        self.window.title("Présentation du jeu de données")
        self.window.geometry("900x620")
        self.window.minsize(800, 500)
        self.conn = conn

        self.build_ui()
        self.refresh()

    def build_ui(self):
        main = Frame(self.window, padx=18, pady=18)
        main.pack(fill="both", expand=True)

        title = Label(main, text="Présentation du jeu de données", font=("Segoe UI", 16, "bold"), anchor="w")
        title.pack(fill="x", pady=(0, 10))

        subtitle = Label(main, text="Base multimodale agroécologique – Sénégal", fg="#3f4a5f", font=("Segoe UI", 11))
        subtitle.pack(fill="x", pady=(0, 12))

        self.summary_text = Text(main, height=10, width=110, wrap="word", bg="#f7f9fc", relief="solid", borderwidth=1)
        self.summary_text.pack(fill="x", pady=(0, 12))

        self.table_tree = ttk.Treeview(main, columns=("table", "lignes", "description"), show="headings")
        self.table_tree.heading("table", text="Table")
        self.table_tree.heading("lignes", text="Lignes")
        self.table_tree.heading("description", text="Description")
        self.table_tree.column("table", width=220, anchor="w")
        self.table_tree.column("lignes", width=110, anchor="e")
        self.table_tree.column("description", width=500, anchor="w")
        self.table_tree.pack(fill="both", expand=True)

    def refresh(self):
        tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        table_names = [row[0] for row in tables]
        total_rows = 0
        rows = []
        descriptions = {
            "agriculture": "Productions agricoles et superficies par culture",
            "climate": "Données climatiques et pluviométrie / température",
            "soils": "Caractéristiques pédologiques",
            "spectral_indices": "Indices spectrales calculés ou importés",
            "water_points": "Points d'eau pastoraux",
            "millet_yields": "Rendements en mil et indicateurs climatiques",
            "livestock_units": "Unités pastorales géoréférencées",
            "metadata": "Métadonnées des sources",
            "geospatial_layers": "Couches vectorielles et géospatiales",
            "remote_sensing": "Métadonnées produits de télédétection",
            "articles": "Articles scientifiques indexés",
            "article_files": "Fichiers associés aux articles",
        }

        for name in table_names:
            count = self.conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            total_rows += count
            rows.append((name, count, descriptions.get(name, "Données de la base")))

        self.summary_text.delete(1.0, END)
        self.summary_text.insert(END, f"Nombre total de tables: {len(table_names)}\n")
        self.summary_text.insert(END, f"Nombre total de lignes: {total_rows}\n\n")
        self.summary_text.insert(END, "Tables principales:\n")
        for name, count, _ in rows[:10]:
            self.summary_text.insert(END, f"- {name}: {count} lignes\n")
        self.summary_text.configure(state="disabled")

        for child in self.table_tree.get_children():
            self.table_tree.delete(child)

        for table_name, count, desc in rows:
            self.table_tree.insert("", "end", values=(table_name, count, desc))


def main():
    root = Tk()
    app = MultimodalDBApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Interface fermée proprement.")
        root.destroy()


if __name__ == "__main__":
    main()
