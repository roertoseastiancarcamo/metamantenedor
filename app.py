import os
from datetime import datetime
from flask import Flask, request, redirect, url_for, render_template_string
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Registro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    equipo = db.Column(db.String(120), nullable=False)
    ubicacion = db.Column(db.String(120), nullable=False)
    prioridad = db.Column(db.String(20), nullable=False, default='Media')
    descripcion = db.Column(db.Text, nullable=False)
    creado = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

BASE = (
    '<!doctype html><meta charset="utf-8">'
    '<title>METAMANTENEDOR</title>'
    '<nav><a href="/form">➕ Nuevo</a> | <a href="/registros">📋 Registros</a></nav>'
    '{% block body %}{% endblock %}'
)

FORM = (
    '{% extends base %}'
    '{% block body %}'
    '<h2>Nuevo registro</h2>'
    '<form method="post">'
    '<label>Equipo* <input name="equipo" required></label><br>'
    '<label>Ubicación* <input name="ubicacion" required></label><br>'
    '<label>Prioridad* <select name="prioridad">'
    '<option>Baja</option><option selected>Media</option><option>Alta</option><option>Crítica</option>'
    '</select></label><br>'
    '<label>Descripción* <textarea name="descripcion" rows="4" required></textarea></label><br>'
    '<button>Guardar</button>'
    '</form>'
    '{% endblock %}'
)

LISTA = (
    '{% extends base %}'
    '{% block body %}'
    '<h2>Registros</h2>'
    '<table border=1 cellpadding=6>'
    '<tr><th>ID</th><th>Equipo</th><th>Ubicación</th><th>Prioridad</th><th>Creado</th></tr>'
    '{% for r in items %}'
    '<tr><td>{{r.id}}</td><td>{{r.equipo}}</td><td>{{r.ubicacion}}</td><td>{{r.prioridad}}</td><td>{{r.creado.strftime("%Y-%m-%d %H:%M")}}</td></tr>'
    '{% endfor %}'
    '</table>'
    '{% if not items %}<p>Aún no hay registros.</p>{% endif %}'
    '{% endblock %}'
)

from jinja2 import DictLoader
app.jinja_loader = DictLoader({'base.html': BASE, 'form.html': FORM, 'list.html': LISTA})

@app.route('/')
def home():
    return redirect(url_for('form'))

@app.route('/form', methods=['GET','POST'])
def form():
    if request.method == 'POST':
        r = Registro(
            equipo=request.form['equipo'].strip(),
            ubicacion=request.form['ubicacion'].strip(),
            prioridad=request.form.get('prioridad','Media'),
            descripcion=request.form['descripcion'].strip(),
        )
        db.session.add(r)
        db.session.commit()
        return redirect(url_for('registros'))
    return render_template_string(FORM, base=BASE)

@app.route('/registros')
def registros():
    items = Registro.query.order_by(Registro.creado.desc()).all()
    return render_template_string(LISTA, base=BASE, items=items)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)), debug=True)
