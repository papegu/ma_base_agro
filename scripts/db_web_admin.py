"""Interface web (Flask) pour administrer la base multimodal_base.sqlite depuis un navigateur.

Lancement:
    .venv\\Scripts\\python.exe scripts\\db_web_admin.py
Puis ouvrir http://127.0.0.1:5050 dans un navigateur et se connecter avec les
identifiants définis dans config/sqlite_auth.py.
"""
import hmac
import re
import secrets
import sqlite3
import sys
from functools import wraps
from pathlib import Path

from flask import Flask, abort, redirect, render_template_string, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.sqlite_auth import SQLITE_DB_PASSWORD, SQLITE_DB_PATH, SQLITE_DB_USER  # noqa: E402

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_COLUMN_TYPES = {"TEXT", "INTEGER", "REAL", "BLOB", "NUMERIC"}
PAGE_SIZE = 50

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


# --- Sécurité : session, CSRF, connexion --------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


def check_csrf():
    token = session.get("_csrf_token")
    submitted = request.form.get("csrf_token", "")
    if not token or not hmac.compare_digest(token, submitted):
        abort(400, "Jeton CSRF invalide ou manquant.")


def get_db_path():
    return session.get("db_path", str(SQLITE_DB_PATH))


def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def get_connection_for_path(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_admin_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def authenticate(conn, username, password):
    """Vérifie les identifiants contre le compte historique (config) et la table admin_users."""
    username_bytes = username.encode("utf-8", "replace")
    password_bytes = password.encode("utf-8", "replace")
    if hmac.compare_digest(username_bytes, SQLITE_DB_USER.encode("utf-8")) and hmac.compare_digest(
        password_bytes, SQLITE_DB_PASSWORD.encode("utf-8")
    ):
        return True
    ensure_admin_table(conn)
    row = conn.execute("SELECT password_hash FROM admin_users WHERE username=?", (username,)).fetchone()
    return bool(row) and check_password_hash(row["password_hash"], password)


def valid_identifier(name):
    return bool(name) and bool(IDENTIFIER_RE.match(name))


def table_exists(conn, table_name):
    row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return row[0] > 0


def list_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    return [r[0] for r in rows]


def get_columns(conn, table_name):
    return [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()]


# --- Gabarit HTML partagé ------------------------------------------------------------------

BASE_TEMPLATE = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{{ title }} — Base multimodale agroécologique</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: #f3f5f8; color: #1a1a1a; }
  header { background: #0f1f33; color: white; padding: 14px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 1px 4px rgba(0,0,0,0.2); }
  header .brand { font-weight: 600; margin-right: 22px; }
  header nav { display: inline; }
  header nav a { color: #dfeeff; margin-right: 18px; text-decoration: none; font-size: 0.92em; }
  header nav a:hover, header .logout a:hover { text-decoration: underline; }
  header .logout a { color: #ffb4b4; text-decoration: none; font-size: 0.9em; }
  main { padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 1.35em; margin-top: 0; }
  h3 { margin: 16px 0 6px; }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; background: white; }
  th, td { border: 1px solid #e2e6ec; padding: 8px 10px; font-size: 0.88em; text-align: left; white-space: nowrap; }
  th { background: #eef2f8; }
  tr:nth-child(even) td { background: #fafbfd; }
  tr:hover td { background: #f0f6ff; }
  .card { background: white; border-radius: 8px; padding: 20px; margin-bottom: 18px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
  .btn { display: inline-block; padding: 7px 14px; border-radius: 5px; border: 1px solid #123; background: #dfeeff; color: #123; text-decoration: none; cursor: pointer; font-size: 0.85em; transition: background 0.15s ease; }
  .btn:hover { background: #c7e0ff; }
  .btn-danger { background: #ffe1e1; border-color: #b00020; color: #b00020; }
  .btn-danger:hover { background: #ffcccc; }
  .btn-primary { background: #123; color: white; }
  .btn-primary:hover { background: #1f3a5c; }
  .actions-bar { margin-bottom: 14px; }
  .actions-bar > * { margin-right: 8px; }
  label { display: block; margin: 12px 0 4px; font-weight: 600; font-size: 0.88em; color: #333; }
  input[type=text], input[type=password], select, textarea {
    display: block; padding: 8px 10px; width: 100%; max-width: 380px;
    border: 1px solid #ccd3dc; border-radius: 5px; font-size: 0.92em; margin-bottom: 6px; background: white;
  }
  input[type=text]:focus, input[type=password]:focus, select:focus, textarea:focus { outline: 2px solid #7fb2ff; border-color: #7fb2ff; }
  textarea { width: 100%; max-width: 100%; height: 160px; font-family: Consolas, monospace; }
  .flash-error { background: #ffe1e1; color: #b00020; padding: 10px 14px; border-radius: 5px; margin-bottom: 14px; }
  .flash-ok { background: #e1ffe4; color: #1a6b2a; padding: 10px 14px; border-radius: 5px; margin-bottom: 14px; }
  form.inline { display: inline; }
  .inline-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .inline-form input[type=text], .inline-form select { display: inline-block; width: auto; margin-bottom: 0; }
  .pagination { margin: 10px 0; font-size: 0.9em; }
  .pagination a { margin-right: 10px; }
</style>
</head>
<body>
{% if session.get('authenticated') %}
<header>
  <div><span class="brand">Base multimodale agroécologique</span>
  <nav><a href="{{ url_for('dashboard') }}">Tableau de bord</a><a href="{{ url_for('new_table') }}">Nouvelle table</a><a href="{{ url_for('query_console') }}">Requête SQL</a></nav></div>
  <div class="logout"><a href="{{ url_for('logout') }}">Déconnexion</a></div>
</header>
{% endif %}
<main>
{% if error %}<div class="flash-error">{{ error }}</div>{% endif %}
{% if message %}<div class="flash-ok">{{ message }}</div>{% endif %}
{{ body|safe }}
</main>
</body>
</html>
"""


def render_page(title, body_html, error=None, message=None):
    return render_template_string(BASE_TEMPLATE, title=title, body=body_html, error=error, message=message)


# --- Authentification ------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        db_path = request.form.get("db_path", "").strip() or str(SQLITE_DB_PATH)
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not Path(db_path).exists():
            error = "Base de données introuvable à ce chemin."
        else:
            conn = get_connection_for_path(db_path)
            try:
                ok = authenticate(conn, username, password)
            finally:
                conn.close()
            if ok:
                session["authenticated"] = True
                session["db_path"] = db_path
                next_url = request.args.get("next") or url_for("dashboard")
                return redirect(next_url)
            error = "Identifiants invalides."

    body = f"""
    <div class="card" style="max-width:420px;margin:60px auto;">
      <h1>Connexion à la base</h1>
      <form method="post">
        <label for="db_path">Chemin de la base SQLite</label>
        <input type="text" id="db_path" name="db_path" value="{SQLITE_DB_PATH}">
        <label for="username">Utilisateur</label>
        <input type="text" id="username" name="username" autocomplete="username">
        <label for="password">Mot de passe</label>
        <input type="password" id="password" name="password" autocomplete="current-password">
        <button class="btn btn-primary" type="submit" style="margin-top:10px;">Se connecter</button>
      </form>
      <p style="text-align:center;margin-top:16px;font-size:0.9em;">
        Pas encore de compte administrateur ? <a href="{url_for('register')}">Créer un compte</a>
      </p>
    </div>
    """
    return render_page("Connexion", body, error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    message = None
    if request.method == "POST":
        check_csrf()
        db_path = request.form.get("db_path", "").strip() or str(SQLITE_DB_PATH)
        new_username = request.form.get("username", "").strip()
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        master_key = request.form.get("master_key", "")

        if not Path(db_path).exists():
            error = "Base de données introuvable à ce chemin."
        elif len(new_username) < 3:
            error = "Nom d'utilisateur invalide (3 caractères minimum)."
        elif len(new_password) < 8:
            error = "Le mot de passe doit contenir au moins 8 caractères."
        elif new_password != confirm_password:
            error = "Les mots de passe ne correspondent pas."
        elif not hmac.compare_digest(master_key.encode("utf-8", "replace"), SQLITE_DB_PASSWORD.encode("utf-8")):
            error = "Clé maître invalide. Elle correspond au mot de passe administrateur défini dans config/sqlite_auth.py."
        else:
            conn = get_connection_for_path(db_path)
            try:
                ensure_admin_table(conn)
                already_exists = conn.execute("SELECT 1 FROM admin_users WHERE username=?", (new_username,)).fetchone()
                is_legacy_name = hmac.compare_digest(new_username.encode("utf-8", "replace"), SQLITE_DB_USER.encode("utf-8"))
                if already_exists or is_legacy_name:
                    error = "Ce nom d'utilisateur est déjà utilisé."
                else:
                    conn.execute(
                        "INSERT INTO admin_users(username, password_hash) VALUES(?, ?)",
                        (new_username, generate_password_hash(new_password)),
                    )
                    conn.commit()
                    message = f"Compte administrateur '{new_username}' créé. Vous pouvez maintenant vous connecter."
            finally:
                conn.close()

    body = f"""
    <div class="card" style="max-width:440px;margin:40px auto;">
      <h1>Créer un compte administrateur</h1>
      <p style="font-size:0.88em;color:#555;">La clé maître correspond au mot de passe défini dans <code>config/sqlite_auth.py</code>.</p>
      <form method="post">
        <input type="hidden" name="csrf_token" value="{get_csrf_token()}">
        <label for="db_path">Chemin de la base SQLite</label>
        <input type="text" id="db_path" name="db_path" value="{SQLITE_DB_PATH}">
        <label for="username">Nouveau nom d'utilisateur</label>
        <input type="text" id="username" name="username" autocomplete="username">
        <label for="password">Mot de passe (8 caractères minimum)</label>
        <input type="password" id="password" name="password" autocomplete="new-password">
        <label for="confirm_password">Confirmer le mot de passe</label>
        <input type="password" id="confirm_password" name="confirm_password" autocomplete="new-password">
        <label for="master_key">Clé maître (mot de passe administrateur principal)</label>
        <input type="password" id="master_key" name="master_key">
        <button class="btn btn-primary" type="submit" style="margin-top:10px;">Créer le compte</button>
      </form>
      <p style="text-align:center;margin-top:16px;font-size:0.9em;"><a href="{url_for('login')}">Retour à la connexion</a></p>
    </div>
    """
    return render_page("Créer un compte", body, error=error, message=message)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Tableau de bord ------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    conn = get_connection()
    try:
        tables = list_tables(conn)
        rows = [(name, conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]) for name in tables]
    finally:
        conn.close()

    items = "".join(
        f'<tr><td><a href="{url_for("view_table", table_name=name)}">{name}</a></td>'
        f'<td>{count}</td></tr>'
        for name, count in rows
    )
    body = f"""
    <div class="card">
      <h1>Base : {get_db_path()}</h1>
      <p>{len(rows)} table(s), {sum(c for _, c in rows)} ligne(s) au total.</p>
      <div class="table-wrap"><table><tr><th>Table</th><th>Lignes</th></tr>{items}</table></div>
    </div>
    """
    return render_page("Tableau de bord", body)


# --- Vue / CRUD sur une table -----------------------------------------------------------

@app.route("/table/<table_name>")
@login_required
def view_table(table_name):
    conn = get_connection()
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)
        page = max(int(request.args.get("page", 1)), 1)
        offset = (page - 1) * PAGE_SIZE
        columns = get_columns(conn, table_name)
        total = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        rows = conn.execute(f'SELECT rowid AS "__rowid__", * FROM "{table_name}" LIMIT ? OFFSET ?', (PAGE_SIZE, offset)).fetchall()
    finally:
        conn.close()

    header_html = "".join(f"<th>{c}</th>" for c in columns) + "<th>Actions</th>"
    body_rows = []
    for row in rows:
        rowid = row["__rowid__"]
        cells = "".join(f"<td>{'' if row[c] is None else row[c]}</td>" for c in columns)
        actions = (
            f'<a class="btn" href="{url_for("edit_row", table_name=table_name, rowid=rowid)}">Modifier</a> '
            f'<form class="inline" method="post" action="{url_for("delete_row", table_name=table_name, rowid=rowid)}" '
            f'onsubmit="return confirm(\'Supprimer cette ligne ?\');">'
            f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">'
            f'<button class="btn btn-danger" type="submit">Supprimer</button></form>'
        )
        body_rows.append(f"<tr>{cells}<td>{actions}</td></tr>")

    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    pagination = f'<div class="pagination">Page {page}/{total_pages} — {total} ligne(s) — '
    if page > 1:
        pagination += f'<a href="{url_for("view_table", table_name=table_name, page=page - 1)}">← Précédent</a>'
    if page < total_pages:
        pagination += f'<a href="{url_for("view_table", table_name=table_name, page=page + 1)}">Suivant →</a>'
    pagination += "</div>"

    body = f"""
    <div class="card">
      <h1>Table : {table_name}</h1>
      <div class="actions-bar">
        <a class="btn btn-primary" href="{url_for('add_row', table_name=table_name)}">Ajouter une ligne</a>
        <a class="btn" href="{url_for('alter_table', table_name=table_name)}">Modifier la structure</a>
        <form class="inline" method="post" action="{url_for('drop_table', table_name=table_name)}"
              onsubmit="return confirm('Supprimer DÉFINITIVEMENT la table {table_name} et toutes ses données ?');">
          <input type="hidden" name="csrf_token" value="{get_csrf_token()}">
          <button class="btn btn-danger" type="submit">Supprimer la table</button>
        </form>
      </div>
      {pagination}
      <div class="table-wrap"><table><tr>{header_html}</tr>{"".join(body_rows)}</table></div>
    </div>
    """
    return render_page(f"Table {table_name}", body)


def _row_form(table_name, columns, values, action_url):
    fields = "".join(
        f'<label for="{col}">{col}</label><input type="text" id="{col}" name="{col}" value="{"" if values.get(col) is None else values.get(col)}">'
        for col in columns
    )
    return f"""
    <div class="card" style="max-width:520px;">
      <h1>{action_url[1]}</h1>
      <form method="post">
        <input type="hidden" name="csrf_token" value="{get_csrf_token()}">
        {fields}
        <div class="actions-bar" style="margin-top:14px;">
          <button class="btn btn-primary" type="submit">Enregistrer</button>
          <a class="btn" href="{url_for('view_table', table_name=table_name)}">Annuler</a>
        </div>
      </form>
    </div>
    """


def _coerce_value(text):
    if text is None:
        return None
    text = text.strip()
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


@app.route("/table/<table_name>/add", methods=["GET", "POST"])
@login_required
def add_row(table_name):
    conn = get_connection()
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)
        columns = [c for c in get_columns(conn, table_name) if c.lower() != "id"]

        error = None
        if request.method == "POST":
            check_csrf()
            values = {col: _coerce_value(request.form.get(col)) for col in columns}
            col_list = ",".join(f'"{c}"' for c in columns)
            placeholders = ",".join(["?"] * len(columns))
            try:
                conn.execute(f'INSERT INTO "{table_name}"({col_list}) VALUES({placeholders})', list(values.values()))
                conn.commit()
                return redirect(url_for("view_table", table_name=table_name))
            except Exception as exc:
                error = f"Insertion impossible : {exc}"

        body = _row_form(table_name, columns, {}, ("add", f"Ajouter une ligne — {table_name}"))
    finally:
        conn.close()
    return render_page(f"Ajouter — {table_name}", body, error=error if request.method == "POST" else None)


@app.route("/table/<table_name>/edit/<int:rowid>", methods=["GET", "POST"])
@login_required
def edit_row(table_name, rowid):
    conn = get_connection()
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)
        columns = [c for c in get_columns(conn, table_name) if c.lower() != "id"]

        error = None
        if request.method == "POST":
            check_csrf()
            values = {col: _coerce_value(request.form.get(col)) for col in columns}
            set_clause = ",".join(f'"{c}"=?' for c in columns)
            try:
                conn.execute(f'UPDATE "{table_name}" SET {set_clause} WHERE rowid=?', (*values.values(), rowid))
                conn.commit()
                return redirect(url_for("view_table", table_name=table_name))
            except Exception as exc:
                error = f"Modification impossible : {exc}"

        record = conn.execute(f'SELECT {", ".join(f"""\"{c}\"""" for c in columns)} FROM "{table_name}" WHERE rowid=?', (rowid,)).fetchone()
        if record is None:
            abort(404)
        current_values = dict(zip(columns, record))
        body = _row_form(table_name, columns, current_values, ("edit", f"Modifier la ligne (id={rowid}) — {table_name}"))
    finally:
        conn.close()
    return render_page(f"Modifier — {table_name}", body, error=error if request.method == "POST" else None)


@app.route("/table/<table_name>/delete/<int:rowid>", methods=["POST"])
@login_required
def delete_row(table_name, rowid):
    check_csrf()
    conn = get_connection()
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)
        conn.execute(f'DELETE FROM "{table_name}" WHERE rowid=?', (rowid,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("view_table", table_name=table_name))


# --- Gestion du schéma : créer / supprimer / modifier une table --------------------------

@app.route("/table/new", methods=["GET", "POST"])
@login_required
def new_table():
    error = None
    if request.method == "POST":
        check_csrf()
        table_name = request.form.get("table_name", "").strip()
        col_names = request.form.getlist("col_name")
        col_types = request.form.getlist("col_type")
        columns = [(n.strip(), t.strip().upper()) for n, t in zip(col_names, col_types) if n.strip()]

        if not valid_identifier(table_name):
            error = "Nom de table invalide (lettres, chiffres, underscore, ne commence pas par un chiffre)."
        elif not columns:
            error = "Ajoutez au moins une colonne."
        elif not all(valid_identifier(n) for n, _ in columns):
            error = "Nom de colonne invalide."
        elif not all(t in ALLOWED_COLUMN_TYPES for _, t in columns):
            error = f"Type de colonne non supporté (autorisés: {', '.join(sorted(ALLOWED_COLUMN_TYPES))})."
        else:
            conn = get_connection()
            try:
                if table_exists(conn, table_name):
                    error = "Une table avec ce nom existe déjà."
                else:
                    cols_sql = ", ".join(f'"{n}" {t}' for n, t in columns)
                    conn.execute(f'CREATE TABLE "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})')
                    conn.commit()
                    return redirect(url_for("view_table", table_name=table_name))
            except Exception as exc:
                error = f"Création impossible : {exc}"
            finally:
                conn.close()

    rows_html = "".join(
        '<div class="inline-form"><input type="text" name="col_name" placeholder="nom_colonne" style="width:200px;">'
        f'<select name="col_type">{"".join(f"<option>{t}</option>" for t in sorted(ALLOWED_COLUMN_TYPES))}</select></div>'
        for _ in range(8)
    )
    body = f"""
    <div class="card" style="max-width:560px;">
      <h1>Créer une nouvelle table</h1>
      <p>Une colonne <code>id INTEGER PRIMARY KEY AUTOINCREMENT</code> est ajoutée automatiquement.</p>
      <form method="post">
        <input type="hidden" name="csrf_token" value="{get_csrf_token()}">
        <label>Nom de la table</label>
        <input type="text" name="table_name">
        <h3>Colonnes</h3>
        {rows_html}
        <button class="btn btn-primary" type="submit" style="margin-top:8px;">Créer la table</button>
      </form>
    </div>
    """
    return render_page("Nouvelle table", body, error=error)


@app.route("/table/<table_name>/drop", methods=["POST"])
@login_required
def drop_table(table_name):
    check_csrf()
    conn = get_connection()
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)
        conn.execute(f'DROP TABLE "{table_name}"')
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("dashboard"))


@app.route("/table/<table_name>/alter", methods=["GET", "POST"])
@login_required
def alter_table(table_name):
    conn = get_connection()
    error = None
    message = None
    try:
        if not valid_identifier(table_name) or not table_exists(conn, table_name):
            abort(404)

        if request.method == "POST":
            check_csrf()
            action = request.form.get("action")
            try:
                if action == "add_column":
                    col_name = request.form.get("col_name", "").strip()
                    col_type = request.form.get("col_type", "").strip().upper()
                    if not valid_identifier(col_name) or col_type not in ALLOWED_COLUMN_TYPES:
                        raise ValueError("Nom ou type de colonne invalide.")
                    conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}')
                    conn.commit()
                    message = f"Colonne {col_name} ajoutée."
                elif action == "drop_column":
                    col_name = request.form.get("col_name", "").strip()
                    if col_name not in get_columns(conn, table_name):
                        raise ValueError("Colonne inconnue.")
                    conn.execute(f'ALTER TABLE "{table_name}" DROP COLUMN "{col_name}"')
                    conn.commit()
                    message = f"Colonne {col_name} supprimée."
                elif action == "rename_table":
                    new_name = request.form.get("new_name", "").strip()
                    if not valid_identifier(new_name):
                        raise ValueError("Nom de table invalide.")
                    if table_exists(conn, new_name):
                        raise ValueError("Une table avec ce nom existe déjà.")
                    conn.execute(f'ALTER TABLE "{table_name}" RENAME TO "{new_name}"')
                    conn.commit()
                    return redirect(url_for("view_table", table_name=new_name))
                else:
                    raise ValueError("Action inconnue.")
            except Exception as exc:
                error = str(exc)

        columns = get_columns(conn, table_name)
    finally:
        conn.close()

    col_options = "".join(f"<option>{c}</option>" for c in columns)
    type_options = "".join(f"<option>{t}</option>" for t in sorted(ALLOWED_COLUMN_TYPES))
    csrf = get_csrf_token()
    body = f"""
    <div class="card" style="max-width:560px;">
      <h1>Modifier la structure — {table_name}</h1>
      <h3>Ajouter une colonne</h3>
      <form class="inline-form" method="post">
        <input type="hidden" name="csrf_token" value="{csrf}">
        <input type="hidden" name="action" value="add_column">
        <input type="text" name="col_name" placeholder="nom_colonne">
        <select name="col_type">{type_options}</select>
        <button class="btn btn-primary" type="submit">Ajouter</button>
      </form>
      <h3>Supprimer une colonne</h3>
      <form class="inline-form" method="post">
        <input type="hidden" name="csrf_token" value="{csrf}">
        <input type="hidden" name="action" value="drop_column">
        <select name="col_name">{col_options}</select>
        <button class="btn btn-danger" type="submit" onclick="return confirm('Supprimer cette colonne ?');">Supprimer</button>
      </form>
      <h3>Renommer la table</h3>
      <form class="inline-form" method="post">
        <input type="hidden" name="csrf_token" value="{csrf}">
        <input type="hidden" name="action" value="rename_table">
        <input type="text" name="new_name" placeholder="nouveau_nom">
        <button class="btn btn-primary" type="submit">Renommer</button>
      </form>
      <p><a class="btn" href="{url_for('view_table', table_name=table_name)}">Retour à la table</a></p>
    </div>
    """
    return render_page(f"Structure {table_name}", body, error=error, message=message)


# --- Console SQL libre -------------------------------------------------------------------

@app.route("/query", methods=["GET", "POST"])
@login_required
def query_console():
    error = None
    result_html = ""
    sql_text = request.form.get("sql", "") if request.method == "POST" else ""

    if request.method == "POST":
        check_csrf()
        conn = get_connection()
        try:
            cursor = conn.execute(sql_text)
            if cursor.description:
                cols = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                header_html = "".join(f"<th>{c}</th>" for c in cols)
                body_rows = "".join(
                    "<tr>" + "".join(f"<td>{'' if v is None else v}</td>" for v in row) + "</tr>"
                    for row in rows
                )
                result_html = f'<p>{len(rows)} ligne(s) retournée(s).</p><div class="table-wrap"><table><tr>{header_html}</tr>{body_rows}</table></div>'
            else:
                conn.commit()
                result_html = f'<p>Requête exécutée avec succès ({cursor.rowcount} ligne(s) affectée(s)).</p>'
        except Exception as exc:
            error = f"Erreur SQL : {exc}"
        finally:
            conn.close()

    body = f"""
    <div class="card">
      <h1>Console SQL</h1>
      <p>Exécutez directement des requêtes SQL sur la base (SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP...).</p>
      <form method="post">
        <input type="hidden" name="csrf_token" value="{get_csrf_token()}">
        <textarea name="sql" placeholder="SELECT * FROM climate LIMIT 10;">{sql_text}</textarea><br>
        <button class="btn btn-primary" type="submit">Exécuter</button>
      </form>
    </div>
    <div class="card">{result_html}</div>
    """
    return render_page("Console SQL", body, error=error)


def main():
    print(f"Interface web disponible sur http://127.0.0.1:5050  (base par défaut: {SQLITE_DB_PATH})")
    app.run(host="127.0.0.1", port=5050, debug=False)


if __name__ == "__main__":
    main()
