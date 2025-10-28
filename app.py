import os
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///data.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Registro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipo = db.Column(db.String(120), nullable=False)
    ubicacion = db.Column(db.String(120), nullable=False)
    prioridad = db.Column(db.String(20), nullable=False, default="Media")
    descripcion = db.Column(db.Text, nullable=False)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

PAGE_HEAD = """
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>METAMANTENEDOR</title>
<style>
  body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f8fb;color:#111827}
  header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#0f172a;color:#fff}
  header a{color:#fff;text-decoration:none;margin-left:12px}
  main{max-width:900px;margin:0 auto;padding:16px}
  .card{background:#fff;padding:16px;border-radius:12px;box-shadow:0 2px 8px #0001}
  label{display:block;margin:8px 0} input,select,textarea,button{width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px}
  button{background:#2563eb;color:#fff;border:0;cursor:pointer}
  table{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px #0001}
  th,td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left} thead{background:#eef2ff}
</style>
<header>
  <strong>METAMANTENEDOR</strong>
  <nav><a href="/form">➕ Nuevo</a><a href="/registros">📋 Registros</a></nav>
</header><main>
"""

PAGE_TAIL = "</main>"

FORM_HTML = PAGE_HEAD + """
<h2>Nuevo registro</h2>
<form method="post" class="card">
  <label>Equipo* <input name="equipo" required></label>
  <label>Ubicación* <input name="ubicacion" required></label>
  <label>Prioridad*
    <select name="prioridad">
      <option>Baja</option><option selected>Media</option><option>Alta</option><option>Crítica</option>
    </select>
  </label>
  <label>Descripción* <textarea name="descripcion" rows="4" required></textarea></label>
  <button>Guardar</button>
</form>
""" + PAGE_TAIL

LIST_HTML_HEAD = PAGE_HEAD + """
<h2>Registros</h2>
<table>
  <thead><tr><th>ID</th><th>Equipo</th><th>Ubicación</th><th>Prioridad</th><th>Creado</th></tr></thead>
  <tbody>
"""

LIST_HTML_TAIL = """
  </tbody>
</table>
""" + PAGE_TAIL

@app.route("/")
def home():
    return redirect(url_for("form"))

@app.route("/form", methods=["GET","POST"])
def form():
    if request.method == "POST":
        r = Registro(
            equipo=request.form["equipo"].strip(),
            ubicacion=request.form["ubicacion"].strip(),
            prioridad=request.form.get("prioridad","Media"),
            descripcion=request.form["descripcion"].strip(),
        )
        db.session.add(r); db.session.commit()
        return redirect(url_for("registros"))
    return render_template_string(FORM_HTML)

@app.route("/registros")
def registros():
    items = Registro.query.order_by(Registro.creado.desc()).all()
    rows = "".join(
        f"<tr><td>{r.id}</td><td>{r.equipo}</td><td>{r.ubicacion}</td>"
        f"<td>{r.prioridad}</td><td>{r.creado.strftime('%Y-%m-%d %H:%M')}</td></tr>"
        for r in items
    )
    if not items:
        rows = '<tr><td colspan="5" style="padding:16px">Aún no hay registros.</td></tr>'
    return render_template_string(LIST_HTML_HEAD + rows + LIST_HTML_TAIL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
