import os
import sqlite3
import sys
import threading
import webbrowser
from contextlib import suppress
from pathlib import Path
from tkinter import ttk

import numpy as np
from PIL import Image, ImageOps, ImageTk
from tkinter import *
from tkinter import messagebox
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
        button_row = Frame(self.topbar, bg="#f3f5f8")
        button_row.pack(anchor="e", pady=(6, 0))
        Button(button_row, text="Interface web", command=self.launch_web_interface, bg="#dfeeff", fg="#123", relief="raised").pack(side="left")
        Button(button_row, text="Fenêtre de présentation", command=self.open_presentation_window, bg="#dfeeff", fg="#123", relief="raised").pack(side="left", padx=(6, 0))

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
        self.current_table = None

        left = ttk.Frame(frame, padding=10)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="Tables disponibles", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.table_listbox = Listbox(left, width=32, height=22, exportselection=False)
        self.table_listbox.pack(fill="y", pady=(5, 10))
        self.table_listbox.bind("<<ListboxSelect>>", self.on_table_select)

        ttk.Label(left, text="Statistiques globales", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.overview_stats = Text(left, height=16, width=32, wrap="word", relief="solid", borderwidth=1)
        self.overview_stats.pack(fill="x", pady=(5, 0))

        right = ttk.Frame(frame, padding=10)
        right.pack(side="left", fill="both", expand=True)

        self.selected_table_var = StringVar(value="Sélectionnez une table à gauche")
        ttk.Label(right, textvariable=self.selected_table_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(8, 4))
        ttk.Button(toolbar, text="Actualiser", command=self.refresh_current_table).pack(side="left")
        ttk.Button(toolbar, text="Ajouter une ligne", command=self.add_row_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Modifier la ligne sélectionnée", command=self.edit_row_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Supprimer la ligne sélectionnée", command=self.delete_selected_row).pack(side="left", padx=(6, 0))

        schema_toolbar = ttk.Frame(right)
        schema_toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(schema_toolbar, text="Nouvelle table", command=self.open_new_table_dialog).pack(side="left")
        ttk.Button(schema_toolbar, text="Modifier la structure", command=self.open_alter_table_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(schema_toolbar, text="Supprimer la table", command=self.drop_current_table).pack(side="left", padx=(6, 0))
        ttk.Button(schema_toolbar, text="Requête SQL", command=self.open_sql_console).pack(side="left", padx=(6, 0))

        tree_container = ttk.Frame(right)
        tree_container.pack(fill="both", expand=True)
        tree_container.rowconfigure(0, weight=1)
        tree_container.columnconfigure(0, weight=1)

        overview_vsb = ttk.Scrollbar(tree_container, orient="vertical")
        overview_hsb = ttk.Scrollbar(tree_container, orient="horizontal")
        self.overview_tree = ttk.Treeview(
            tree_container, show="headings",
            yscrollcommand=overview_vsb.set, xscrollcommand=overview_hsb.set,
        )
        overview_vsb.configure(command=self.overview_tree.yview)
        overview_hsb.configure(command=self.overview_tree.xview)
        self.overview_tree.grid(row=0, column=0, sticky="nsew")
        overview_vsb.grid(row=0, column=1, sticky="ns")
        overview_hsb.grid(row=1, column=0, sticky="ew")
        self.overview_tree.bind("<Double-1>", lambda event: self.edit_row_dialog())

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
        self.current_table = table_name
        self.load_table_data(table_name)

    def load_table_data(self, table_name, limit=500):
        columns = self.get_columns(table_name)
        try:
            rows = self.conn.execute(f'SELECT rowid, * FROM "{table_name}" LIMIT {limit}').fetchall()
            total = self.conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        except Exception as exc:
            messagebox.showerror("Erreur", f"Impossible de lire la table {table_name}:\n{exc}")
            return

        suffix = f" (affichage limité à {limit})" if total > limit else ""
        self.selected_table_var.set(f"{table_name} — {total} ligne(s){suffix}")

        tree = self.overview_tree
        for child in tree.get_children():
            tree.delete(child)
        tree.configure(columns=columns)
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=140, anchor="w")
        for record in rows:
            rowid, *values = record
            display_values = ["" if v is None else str(v) for v in values]
            tree.insert("", "end", iid=str(rowid), values=display_values)

    def refresh_current_table(self):
        if self.current_table:
            self.load_table_data(self.current_table)

    def add_row_dialog(self):
        if not self.current_table:
            messagebox.showinfo("Aucune table", "Sélectionnez d'abord une table dans la liste.")
            return
        columns = [c for c in self.get_columns(self.current_table) if c.lower() != "id"]

        def on_submit(values):
            self.insert_row(self.current_table, values)

        RowFormDialog(self.root, f"Ajouter une ligne — {self.current_table}", columns, on_submit=on_submit)

    def edit_row_dialog(self):
        if not self.current_table:
            return
        selection = self.overview_tree.selection()
        if not selection:
            messagebox.showinfo("Aucune sélection", "Sélectionnez une ligne à modifier.")
            return
        rowid = selection[0]
        columns = [c for c in self.get_columns(self.current_table) if c.lower() != "id"]
        record = self.conn.execute(f'SELECT {", ".join(f"\"{c}\"" for c in columns)} FROM "{self.current_table}" WHERE rowid=?', (rowid,)).fetchone()
        if record is None:
            messagebox.showerror("Erreur", "Ligne introuvable (a-t-elle déjà été supprimée ?).")
            return
        initial_values = dict(zip(columns, record))

        def on_submit(values):
            self.update_row(self.current_table, rowid, values)

        RowFormDialog(self.root, f"Modifier la ligne (id={rowid}) — {self.current_table}", columns, initial_values=initial_values, on_submit=on_submit)

    def delete_selected_row(self):
        if not self.current_table:
            return
        selection = self.overview_tree.selection()
        if not selection:
            messagebox.showinfo("Aucune sélection", "Sélectionnez une ou plusieurs lignes à supprimer.")
            return
        if not messagebox.askyesno("Confirmer la suppression", f"Supprimer {len(selection)} ligne(s) de la table {self.current_table} ?"):
            return
        try:
            for rowid in selection:
                self.conn.execute(f'DELETE FROM "{self.current_table}" WHERE rowid=?', (rowid,))
            self.conn.commit()
        except Exception as exc:
            messagebox.showerror("Erreur", f"Suppression impossible:\n{exc}")
            return
        self.refresh_current_table()
        self.load_overview_stats()

    def insert_row(self, table_name, values):
        columns = list(values.keys())
        coerced = [self._coerce_value(values[col]) for col in columns]
        placeholders = ",".join(["?"] * len(columns))
        col_list = ",".join(f'"{c}"' for c in columns)
        try:
            self.conn.execute(f'INSERT INTO "{table_name}"({col_list}) VALUES({placeholders})', coerced)
            self.conn.commit()
        except Exception as exc:
            messagebox.showerror("Erreur", f"Insertion impossible:\n{exc}")
            return
        self.refresh_current_table()
        self.load_overview_stats()

    def update_row(self, table_name, rowid, values):
        columns = list(values.keys())
        coerced = [self._coerce_value(values[col]) for col in columns]
        set_clause = ",".join(f'"{c}"=?' for c in columns)
        try:
            self.conn.execute(f'UPDATE "{table_name}" SET {set_clause} WHERE rowid=?', (*coerced, rowid))
            self.conn.commit()
        except Exception as exc:
            messagebox.showerror("Erreur", f"Modification impossible:\n{exc}")
            return
        self.refresh_current_table()

    @staticmethod
    def _coerce_value(text):
        if isinstance(text, str):
            text = text.strip()
        if text in ("", None):
            return None
        try:
            return int(text)
        except (TypeError, ValueError):
            pass
        try:
            return float(text)
        except (TypeError, ValueError):
            return text

    def open_new_table_dialog(self):
        def on_submit(table_name, columns):
            if not table_name.isidentifier():
                messagebox.showerror("Erreur", "Nom de table invalide.")
                return
            if not columns:
                messagebox.showerror("Erreur", "Ajoutez au moins une colonne.")
                return
            if not all(name.isidentifier() for name, _ in columns):
                messagebox.showerror("Erreur", "Nom de colonne invalide.")
                return
            if self.table_exists(table_name):
                messagebox.showerror("Erreur", "Une table avec ce nom existe déjà.")
                return
            cols_sql = ", ".join(f'"{name}" {col_type}' for name, col_type in columns)
            try:
                self.conn.execute(f'CREATE TABLE "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')
                self.conn.commit()
            except Exception as exc:
                messagebox.showerror("Erreur", f"Création impossible:\n{exc}")
                return
            self.load_table_list()
            self.load_overview_stats()
            messagebox.showinfo("Succès", f"Table {table_name} créée.")

        CreateTableDialog(self.root, on_submit)

    def drop_current_table(self):
        if not self.current_table:
            messagebox.showinfo("Aucune table", "Sélectionnez d'abord une table dans la liste.")
            return
        table_name = self.current_table
        if not messagebox.askyesno("Confirmer", f"Supprimer DÉFINITIVEMENT la table '{table_name}' et toutes ses données ?"):
            return
        try:
            self.conn.execute(f'DROP TABLE "{table_name}"')
            self.conn.commit()
        except Exception as exc:
            messagebox.showerror("Erreur", f"Suppression impossible:\n{exc}")
            return
        self.current_table = None
        self.selected_table_var.set("Sélectionnez une table à gauche")
        for child in self.overview_tree.get_children():
            self.overview_tree.delete(child)
        self.overview_tree.configure(columns=())
        self.load_table_list()
        self.load_overview_stats()

    def open_alter_table_dialog(self):
        if not self.current_table:
            messagebox.showinfo("Aucune table", "Sélectionnez d'abord une table dans la liste.")
            return
        table_name = self.current_table
        columns = self.get_columns(table_name)

        def on_add_column(col_name, col_type):
            if not col_name.isidentifier():
                messagebox.showerror("Erreur", "Nom de colonne invalide.")
                return
            try:
                self.conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}')
                self.conn.commit()
            except Exception as exc:
                messagebox.showerror("Erreur", f"Ajout impossible:\n{exc}")
                return
            self.refresh_current_table()
            messagebox.showinfo("Succès", f"Colonne {col_name} ajoutée.")

        def on_drop_column(col_name):
            if not col_name:
                return
            if not messagebox.askyesno("Confirmer", f"Supprimer la colonne '{col_name}' ?"):
                return
            try:
                self.conn.execute(f'ALTER TABLE "{table_name}" DROP COLUMN "{col_name}"')
                self.conn.commit()
            except Exception as exc:
                messagebox.showerror("Erreur", f"Suppression impossible:\n{exc}")
                return
            self.refresh_current_table()

        def on_rename_table(new_name):
            if not new_name.isidentifier():
                messagebox.showerror("Erreur", "Nom de table invalide.")
                return
            if self.table_exists(new_name):
                messagebox.showerror("Erreur", "Une table avec ce nom existe déjà.")
                return
            try:
                self.conn.execute(f'ALTER TABLE "{table_name}" RENAME TO "{new_name}"')
                self.conn.commit()
            except Exception as exc:
                messagebox.showerror("Erreur", f"Renommage impossible:\n{exc}")
                return
            self.current_table = new_name
            self.load_table_list()
            self.load_table_data(new_name)

        AlterTableDialog(self.root, table_name, columns, on_add_column, on_drop_column, on_rename_table)

    def open_sql_console(self):
        def on_change():
            self.load_table_list()
            self.load_overview_stats()
            self.refresh_current_table()

        SqlConsoleWindow(self.root, self.conn, on_change=on_change)

    def launch_web_interface(self):
        if getattr(self, "_web_thread", None) and self._web_thread.is_alive():
            webbrowser.open("http://127.0.0.1:5050")
            return
        try:
            from scripts.db_web_admin import app as web_app
        except Exception as exc:
            messagebox.showerror("Erreur", f"Interface web indisponible:\n{exc}")
            return

        def run_server():
            web_app.run(host="127.0.0.1", port=5050, debug=False, use_reloader=False)

        self._web_thread = threading.Thread(target=run_server, daemon=True)
        self._web_thread.start()
        webbrowser.open("http://127.0.0.1:5050")

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

    def get_columns(self, table_name):
        try:
            cols = self.conn.execute(f"PRAGMA table_info(\"{table_name}\")").fetchall()
            return [c[1] for c in cols]
        except Exception:
            return []

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
        self.overview_stats.insert(END, f"Tables: {len(stats)}\n")
        self.overview_stats.insert(END, f"Lignes totales: {sum(count for _, count in stats)}\n\n")
        for name, count in stats:
            self.overview_stats.insert(END, f"- {name}: {count} lignes\n")

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

        default_label = next(
            (label for label, option in self.geotiff_band_options.items()
             if option[0] == "formula" and option[1] == (spectral_index or "").upper()),
            labels[0],
        )
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
                pil_image = self._build_geotiff_preview_image(src, kind, option)

            if pil_image.mode != 'RGB':
                pil_image = ImageOps.autocontrast(pil_image.convert('L')).convert('RGB')
            pil_image = pil_image.resize((600, 400), Image.Resampling.LANCZOS)
            img_tk = ImageTk.PhotoImage(pil_image)
            self.geotiff_preview.configure(image=img_tk, text="")
            self.geotiff_preview.image = img_tk
        except Exception as exc:
            self._clear_geotiff_preview(f"Aperçu non disponible\n{exc}")

    def _build_geotiff_preview_image(self, src, kind, option):
        if kind == "band":
            band_index = option[1]
            array = src.read(band_index).astype(np.float32)
            return self._normalize_to_gray_image(array)

        if kind == "formula":
            index_name = option[1]
            roles = option[2]
            bands = {role: src.read(band_idx).astype(np.float32) for role, band_idx in roles.items()}
            values = self._compute_spectral_index(index_name, bands)
            pil_image = self._normalize_to_gray_image(values, colorize=True)
            stats_text = f"Indice {index_name} calculé — min={np.nanmin(values):.3f}, max={np.nanmax(values):.3f}, moyenne={np.nanmean(values):.3f}"
            self.geotiff_info.insert(END, f"\n{stats_text}\n")
            return pil_image

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
            return Image.fromarray(rgb)

        band = arr[0] if arr.ndim == 3 else arr
        return self._normalize_to_gray_image(band.astype(np.float32))

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
            if not any(part in skip_dirs for part in shp_path.parts):
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
            with suppress(Exception):
                return pyshp.Reader(str(local_path))

        if file_path and file_path.lower().endswith(".zip") and os.path.exists(file_path):
            try:
                with zipfile.ZipFile(file_path) as zf:
                    names = zf.namelist()
                    target = next(
                        (
                            Path(name).with_suffix("") for name in names
                            if name.lower().endswith(".shp") and Path(name).stem.lower() == (layer_name or "").lower()
                        ),
                        None,
                    )
                    if target is not None:
                        shp_bytes = io.BytesIO(zf.read(f"{target}.shp"))
                        dbf_name = f"{target}.dbf"
                        dbf_bytes = io.BytesIO(zf.read(dbf_name)) if dbf_name in names else None
                        shx_name = f"{target}.shx"
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


class RowFormDialog(Toplevel):
    """Formulaire générique pour ajouter ou modifier une ligne d'une table."""

    def __init__(self, master, title, columns, initial_values=None, on_submit=None):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.on_submit = on_submit
        self.entries = {}
        initial_values = initial_values or {}

        fields_frame = ttk.Frame(self, padding=14)
        fields_frame.pack(fill="both", expand=True)
        for row_idx, column in enumerate(columns):
            ttk.Label(fields_frame, text=column).grid(row=row_idx, column=0, sticky="w", padx=(0, 10), pady=4)
            entry = Entry(fields_frame, width=42)
            value = initial_values.get(column)
            if value is not None:
                entry.insert(0, str(value))
            entry.grid(row=row_idx, column=1, pady=4)
            self.entries[column] = entry

        button_row = ttk.Frame(self, padding=(14, 0, 14, 14))
        button_row.pack(fill="x")
        ttk.Button(button_row, text="Enregistrer", command=self._submit).pack(side="right")
        ttk.Button(button_row, text="Annuler", command=self.destroy).pack(side="right", padx=(0, 8))

        self.transient(master)
        self.grab_set()

    def _submit(self):
        values = {column: entry.get() for column, entry in self.entries.items()}
        if self.on_submit:
            self.on_submit(values)
        self.destroy()


COLUMN_TYPES = ["TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"]


class CreateTableDialog(Toplevel):
    """Formulaire de création d'une nouvelle table (nom + colonnes)."""

    def __init__(self, master, on_submit, max_columns=8):
        super().__init__(master)
        self.title("Créer une nouvelle table")
        self.resizable(False, False)
        self.on_submit = on_submit

        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Nom de la table").grid(row=0, column=0, sticky="w", pady=4)
        self.table_name_entry = Entry(container, width=30)
        self.table_name_entry.grid(row=0, column=1, columnspan=2, pady=4, sticky="w")

        ttk.Label(container, text="Colonnes (id auto-incrémenté ajouté automatiquement)").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(10, 4)
        )

        self.column_rows = []
        for i in range(max_columns):
            name_entry = Entry(container, width=22)
            name_entry.grid(row=2 + i, column=0, pady=2, sticky="w")
            type_var = StringVar(value="TEXT")
            ttk.Combobox(container, textvariable=type_var, state="readonly", width=12, values=COLUMN_TYPES).grid(
                row=2 + i, column=1, pady=2, sticky="w"
            )
            self.column_rows.append((name_entry, type_var))

        button_row = ttk.Frame(self, padding=(14, 0, 14, 14))
        button_row.pack(fill="x")
        ttk.Button(button_row, text="Créer", command=self._submit).pack(side="right")
        ttk.Button(button_row, text="Annuler", command=self.destroy).pack(side="right", padx=(0, 8))

        self.transient(master)
        self.grab_set()

    def _submit(self):
        table_name = self.table_name_entry.get().strip()
        columns = [
            (name_entry.get().strip(), type_var.get())
            for name_entry, type_var in self.column_rows
            if name_entry.get().strip()
        ]
        self.on_submit(table_name, columns)
        self.destroy()


class AlterTableDialog(Toplevel):
    """Fenêtre de modification de structure : ajout/suppression de colonne, renommage de table."""

    def __init__(self, master, table_name, columns, on_add_column, on_drop_column, on_rename_table):
        super().__init__(master)
        self.title(f"Modifier la structure — {table_name}")
        self.resizable(False, False)

        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Ajouter une colonne", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )
        self.add_name_entry = Entry(container, width=20)
        self.add_name_entry.grid(row=1, column=0, sticky="w", pady=2)
        self.add_type_var = StringVar(value="TEXT")
        ttk.Combobox(container, textvariable=self.add_type_var, state="readonly", width=12, values=COLUMN_TYPES).grid(
            row=1, column=1, sticky="w", pady=2
        )
        ttk.Button(
            container, text="Ajouter",
            command=lambda: on_add_column(self.add_name_entry.get().strip(), self.add_type_var.get()),
        ).grid(row=1, column=2, padx=(8, 0))

        ttk.Label(container, text="Supprimer une colonne", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(14, 4)
        )
        self.drop_col_var = StringVar(value=columns[0] if columns else "")
        ttk.Combobox(container, textvariable=self.drop_col_var, state="readonly", width=20, values=columns).grid(
            row=3, column=0, sticky="w", pady=2
        )
        ttk.Button(container, text="Supprimer", command=lambda: on_drop_column(self.drop_col_var.get())).grid(
            row=3, column=2, padx=(8, 0)
        )

        ttk.Label(container, text="Renommer la table", font=("Segoe UI", 10, "bold")).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(14, 4)
        )
        self.rename_entry = Entry(container, width=20)
        self.rename_entry.grid(row=5, column=0, sticky="w", pady=2)
        ttk.Button(container, text="Renommer", command=lambda: on_rename_table(self.rename_entry.get().strip())).grid(
            row=5, column=2, padx=(8, 0)
        )

        ttk.Button(self, text="Fermer", command=self.destroy).pack(pady=(0, 12))
        self.transient(master)
        self.grab_set()


class SqlConsoleWindow(Toplevel):
    """Console d'exécution de requêtes SQL libres sur la base ouverte."""

    def __init__(self, master, conn, on_change=None):
        super().__init__(master)
        self.title("Console SQL")
        self.geometry("800x560")
        self.conn = conn
        self.on_change = on_change

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Requête SQL (SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP...)").pack(anchor="w")
        self.sql_text = Text(top, height=6, wrap="word")
        self.sql_text.pack(fill="x", pady=(4, 6))
        ttk.Button(top, text="Exécuter", command=self.execute_sql).pack(anchor="e")

        result_container = ttk.Frame(self, padding=(10, 0, 10, 10))
        result_container.pack(fill="both", expand=True)
        result_container.rowconfigure(0, weight=1)
        result_container.columnconfigure(0, weight=1)

        vsb = ttk.Scrollbar(result_container, orient="vertical")
        hsb = ttk.Scrollbar(result_container, orient="horizontal")
        self.result_tree = ttk.Treeview(result_container, show="headings", yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.configure(command=self.result_tree.yview)
        hsb.configure(command=self.result_tree.xview)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.status_var = StringVar(value="")
        ttk.Label(self, textvariable=self.status_var, padding=(10, 0, 10, 10)).pack(anchor="w")

        self.transient(master)

    def execute_sql(self):
        sql_text = self.sql_text.get("1.0", END).strip()
        if not sql_text:
            return
        for child in self.result_tree.get_children():
            self.result_tree.delete(child)
        self.result_tree.configure(columns=())
        try:
            cursor = self.conn.execute(sql_text)
            if cursor.description:
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                self.result_tree.configure(columns=columns)
                for col in columns:
                    self.result_tree.heading(col, text=col)
                    self.result_tree.column(col, width=120, anchor="w")
                for row in rows:
                    values = ["" if v is None else str(v) for v in row]
                    self.result_tree.insert("", "end", values=values)
                self.status_var.set(f"{len(rows)} ligne(s) retournée(s).")
            else:
                self.conn.commit()
                self.status_var.set(f"Requête exécutée ({cursor.rowcount} ligne(s) affectée(s)).")
                if self.on_change:
                    self.on_change()
        except Exception as exc:
            messagebox.showerror("Erreur SQL", str(exc))


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
