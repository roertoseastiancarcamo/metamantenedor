from flask import Flask, request, redirect, session, url_for, render_template_string, send_file, jsonify
import os
from datetime import date
import sqlite3

# -------------------------------------------------
# MODO BD (Auto: Postgres si hay DATABASE_URL; si no, SQLite)
# -------------------------------------------------
USE_PG = bool(os.environ.get("DATABASE_URL"))
PG_DSN = os.environ.get("DATABASE_URL")

if USE_PG:
    import psycopg
    from psycopg.rows import dict_row

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret")
DB_PATH = os.environ.get("APP_DB", "data.db")  # usado solo si no hay DATABASE_URL


def db():
    """Conexión a la BD (Postgres o SQLite)."""
    if USE_PG:
        return psycopg.connect(PG_DSN, row_factory=dict_row)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql: str) -> str:
    """Compat de placeholders: '?' -> '%s' si estamos en Postgres."""
    return sql.replace('?', '%s') if USE_PG else sql


# -------------------------------------------------
# APP
# -------------------------------------------------
app = Flask(__name__)
app.config['ENV'] = 'production'
app.config['DEBUG'] = False
app.secret_key = APP_SECRET


# -------------------------------------------------
# Datos base
# -------------------------------------------------
CENTROS = [
    ("angostura@multix",  "ANGOSTURA",  "AYSEN"),
    ("cuchi@multix",      "CUCHI",      "AYSEN"),
    ("guapo@multix",      "GUAPO",      "AYSEN"),
    ("marcacci@multix",   "MARCACCI",   "AYSEN"),
    ("mayhew@multix",     "MAYHEW",     "AYSEN"),
    ("pulluche@multix",   "PULLUCHE",   "AYSEN"),
    ("quemada@multix",    "QUEMADA",    "AYSEN"),
    ("soledad@multix",    "SOLEDAD",    "AYSEN"),
    ("wickham@multix",    "WICKHAM",    "AYSEN"),
    ("williams@multix",   "WILLIAMS",   "AYSEN"),
    ("areaysen@multix",   "AREA AYSEN", "AYSEN"),
    ("chalacayec@multix", "CHALACAYEC", "AYSEN"),
    ("ninualac@multix",   "NINUALAC",   "AYSEN"),
]
ADMIN_EMAILS = set(os.environ.get("APP_ADMINS", "rcarcamo@multix").split(","))
AREAS = sorted({a for _, _, a in CENTROS})
CENTRO_NOMBRES = sorted({c for _, c, _ in CENTROS})


# -------------------------------------------------
# INIT DB (dual: Postgres o SQLite)
# -------------------------------------------------
def init_db():
    conn = db()
    cur = conn.cursor()

    if USE_PG:
        # --- Postgres
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                centro TEXT NOT NULL,
                area TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                centro TEXT NOT NULL,
                area TEXT NOT NULL,
                fecha TEXT NOT NULL,
                desayunos INTEGER NOT NULL,
                almuerzos INTEGER NOT NULL,
                cenas INTEGER NOT NULL,
                total INTEGER NOT NULL,
                estado TEXT NOT NULL DEFAULT 'enviado',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(email, fecha)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        cur.execute("""
            INSERT INTO settings(key, value)
            VALUES ('lock_until','')
            ON CONFLICT (key) DO NOTHING;
        """)
        # seed centros
        for email, centro, area in CENTROS:
            cur.execute("""
                INSERT INTO users(email, centro, area)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING;
            """, (email, centro, area))
        # seed admins
        for adm in ADMIN_EMAILS:
            cur.execute("""
                INSERT INTO users(email, centro, area)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING;
            """, (adm.strip().lower(), 'ADMIN', 'SERVICIOS'))

    else:
        # --- SQLite
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                centro TEXT NOT NULL,
                area TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                centro TEXT NOT NULL,
                area TEXT NOT NULL,
                fecha TEXT NOT NULL,
                desayunos INTEGER NOT NULL,
                almuerzos INTEGER NOT NULL,
                cenas INTEGER NOT NULL,
                total INTEGER NOT NULL,
                estado TEXT NOT NULL DEFAULT 'enviado',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(email, fecha)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('lock_until','')")
        for email, centro, area in CENTROS:
            cur.execute("INSERT OR IGNORE INTO users(email, centro, area) VALUES (?,?,?)", (email, centro, area))
        for adm in ADMIN_EMAILS:
            cur.execute("INSERT OR IGNORE INTO users(email, centro, area) VALUES (?,?,?)",
                        (adm.strip().lower(), 'ADMIN', 'SERVICIOS'))

    conn.commit()
    conn.close()


with app.app_context():
    if not USE_PG and os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()


# -------------------------------------------------
# Templates base
# -------------------------------------------------
BASE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{ title or 'Dotación Comedor Diario' }}</title>
  <style>
    :root{--brand:#1e3a8a;--brand-2:#0ea5e9;--bg:#f7f8fb;--text:#0f172a;--muted:#64748b}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;margin:0;background:var(--bg);color:#0f172a;font-size:14px}
    header{display:flex;justify-content:space-between;align-items:center;padding:28px;background:var(--brand);color:#fff}
    main{max-width:1360px;margin:24px auto;padding:0 20px}
    a{color:#0ea5e9;text-decoration:none}
    a:hover{text-decoration:underline}
    .card{background:#fff;border-radius:14px;box-shadow:0 2px 10px rgba(2,6,23,.06);padding:18px;margin-bottom:16px}
    input,select,button{font-size:14px;padding:8px 10px;border-radius:10px;border:1px solid #e5e7eb}
    input[type=date]{padding:6px 8px} label{display:block;margin:8px 0 6px;font-weight:600}
    .row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .actions{display:flex;gap:10px;margin-top:12px}
    .ok{background:var(--brand);color:#fff;border:none}.warn{background:var(--brand-2);color:#fff;border:none}.danger{background:#ef4444;color:#fff;border:none}
    table{width:100%;border-collapse:collapse} th,td{padding:8px;border-bottom:1px solid #eef2f7;text-align:left;white-space:nowrap}
    thead th{background:#f0f4ff}.badge{padding:3px 7px;border-radius:999px;font-size:11px}
    .b-enviado{background:#dbeafe}.b-aprobado{background:#dcfce7}.b-observado{background:#fee2e2}
    .xscroll{overflow-x:auto}.minw{min-width:1280px}.muted{color:#64748b}.si{color:#dc2626;font-weight:600}.today{outline:2px solid #ef4444; outline-offset:-2px; border-radius:4px}
    .cell-edit{display:flex;gap:6px;align-items:center}
    .small{font-size:12px;padding:4px 8px;border-radius:8px}
    .note{font-size:12px;color:#64748b}
  </style>
</head>
<body>
<header>
  <strong>Registro de platos preparados Multi-X</strong>
  <div>
    {% if session.get('email') %}
      {{ session.email }} — {{ session.centro }} ({{ session.area }})
      <a style="margin-left:12px;color:#fff" href="{{ url_for('logout') }}">Salir</a>
    {% endif %}
  </div>
</header>
<main>{{ content|safe }}</main>
</body>
</html>
"""

LOGIN_TPL = """
<div class="card">
  <h2>Ingresar</h2>
  <p>Escribe tu <strong>correo corporativo</strong>. No requiere clave.</p>
  {% if error %}<p style="color:#b91c1c">{{ error }}</p>{% endif %}
  <form method="post">
    <label>Correo</label>
    <input type="email" name="email" placeholder="usuario@multix" required style="width:100%"/>
    <div class="actions"><button class="ok" type="submit">Entrar</button></div>
  </form>
</div>
"""

FORM_TPL = """
<div class="card">
  <h2>Carga diaria</h2>
  {% if lock_until %}
    <p style="background:#fff3cd;border:1px solid #ffe58f;color:#7a5d00;padding:10px;border-radius:8px">
    Bloqueado hasta: <strong>{{ lock_until }}</strong>. | <strong>Liberado desde:</strong> {{ unlock_from or '—' }}.</p>
  {% endif %}
  <form method="post">
    <div class="row2">
      <div><label>Centro</label><input value="{{ session.centro }}" disabled/></div>
      <div><label>Área</label><input value="{{ session.area }}" disabled/></div>
    </div>
    <div class="row2">
      <div><label>Fecha</label><input type="date" name="fecha" value="{{ selected_fecha or '' }}" required/></div>
      <div><label>Total (auto)</label><input value="{{ datos.total or 0 }}" disabled/></div>
    </div>
    <div class="row">
      <div><label>Desayunos</label><input type="number" min="0" name="desayunos" value="{{ datos.desayunos or 0 }}" required/></div>
      <div><label>Almuerzos</label><input type="number" min="0" name="almuerzos" value="{{ datos.almuerzos or 0 }}" required/></div>
      <div><label>Cenas</label><input type="number" min="0" name="cenas" value="{{ datos.cenas or 0 }}" required/></div>
    </div>
    {% if error %}<p style="color:#b91c1c">{{ error }}</p>{% endif %}
    {% if ok %}<p style="color:#166534">{{ ok }}</p>{% endif %}
    <div class="actions">
      <button class="ok" type="submit">Enviar</button>
      <a class="warn" style="text-decoration:none;padding:10px 12px;border-radius:10px" href="{{ url_for('historial') }}">Historial</a>
    </div>
  </form>
</div>

<div class="card xscroll">
  <h3 style="margin-top:0;text-align:center">{{ month_label }}</h3>
  {% if blocks %}
    {% for b in blocks %}
      <div class="minw" style="margin-bottom:12px">
        <table>
          <thead>
            <tr>
              <th>Área</th><th>Centro</th><th>Servicio</th>
              {% for d in month_days %}<th class="{% if d==today_day %}today{% endif %}">{{ d }}</th>{% endfor %}
            </tr>
          </thead>
          <tbody>
            <tr><td rowspan="3">{{ b.area }}</td><td rowspan="3">{{ b.centro }}</td>
              <td><strong>Desayuno</strong></td>
              {% for d, v in b.des %}<td class="{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}">{{ v }}</td>{% endfor %}
            </tr>
            <tr><td><strong>Almuerzo</strong></td>
              {% for d, v in b.alm %}<td class="{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}">{{ v }}</td>{% endfor %}
            </tr>
            <tr><td><strong>Cena</strong></td>
              {% for d, v in b.cen %}<td class="{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}">{{ v }}</td>{% endfor %}
            </tr>
          </tbody>
        </table>
      </div>
    {% endfor %}
  {% else %}
    <p class="muted" style="text-align:center">No hay centros para mostrar con los filtros actuales.</p>
  {% endif %}
  <p style="margin-top:8px;color:#6b7280">
    <strong>Leyenda:</strong> SI = sin información, - = futuro |
    <strong>Bloqueado hasta:</strong> {{ lock_until or '—' }} |
    <strong>Liberado desde:</strong> {{ unlock_from or '—' }}
  </p>
</div>
"""

# --- ADMIN resumido: una fila "Dotación" por centro (promedio almuerzo/cena) + link al detalle ---
ADMIN_TPL = """
<div class="card" style="display:grid;grid-template-columns:1fr 340px;gap:16px;align-items:start">
  <div>
    <h2 style="margin-top:0">Tablero (Admin/Servicios)</h2>
    <form method="get" id="filtros" class="row2" style="align-items:end">
      <div>
        <label>Área</label>
        <select name="area" onchange="this.form.submit()">
          <option value="">Todas</option>
          {% for a in AREAS %}<option value="{{a}}" {% if a==area %}selected{% endif %}>{{a}}</option>{% endfor %}
        </select>
      </div>
      <div>
        <label>Centro</label>
        <select name="centro" onchange="this.form.submit()">
          <option value="">Todos</option>
          {% for c in CENTROS_OPT %}<option value="{{c}}" {% if c==centro %}selected{% endif %}>{{c}}</option>{% endfor %}
        </select>
      </div>
      <div class="actions" style="margin:0">
        <a class="warn" style="text-decoration:none;padding:8px 10px;border-radius:10px;height:36px;display:inline-flex;align-items:center" href="{{ url_for('export_csv', area=area, centro=centro) }}">Descargar Datos</a>
      </div>
    </form>
  </div>
  <div class="card">
    <h3 style="margin-top:0">Bloquear hasta</h3>
    <form method="post" action="{{ url_for('admin_lock') }}">
      <label>Fecha límite (inclusive)</label>
      <input type="date" name="lock_until"/>
      <div class="actions" style="margin-top:10px">
        <button class="danger" type="submit">Guardar</button>
        <a href="{{ url_for('admin_lock_clear') }}" class="warn" style="text-decoration:none;padding:10px 12px;border-radius:10px">Quitar bloqueo</a>
      </div>
      <p class="muted">Actualmente bloqueado hasta: <strong>{{ lock_until or '—' }}</strong><br>Liberado desde: <strong>{{ unlock_from or '—' }}</strong></p>
    </form>
  </div>
</div>

<div class="card xscroll" style="overflow-x:auto">
  <h3 style="margin-top:0;text-align:center">{{ month_label }}</h3>
  <div class="minw" style="min-width:1280px">
    <table style="table-layout:fixed">
      <colgroup>
        <col style="width:120px"/><col style="width:140px"/><col style="width:120px"/>
        {% for d in month_days %}<col style="width:40px"/>{% endfor %}
      </colgroup>
      <thead>
        <tr><th>Área</th><th>Centro</th><th>Servicio</th>
          {% for d in month_days %}<th class="{% if d==today_day %}today{% endif %}">{{ d }}</th>{% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for b in blocks %}
          <tr>
            <td>{{ b.area }}</td>
            <td><a href="{{ url_for('admin_centro', c=b.centro) }}">{{ b.centro }}</a></td>
            <td><strong>Dotación</strong></td>
            {% for d, v in b.dot %}
              <td class="{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}">{{ v }}</td>
            {% endfor %}
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p class="note">Tip: haz clic en el nombre del centro para abrir el detalle editable.</p>
</div>
"""

# --- Detalle editable por centro ---
DETAIL_TPL = """
<div class="card">
  <h2 style="margin-top:0">Detalle — {{ centro }}</h2>
  <p class="note">Haz clic en un valor para editarlo. Escribe el número y pulsa <strong>OK</strong> para guardar.</p>
  <div class="xscroll">
    <div class="minw" style="min-width:1280px">
      <table style="table-layout:fixed">
        <colgroup>
          <col style="width:120px"/><col style="width:140px"/>
          {% for d in month_days %}<col style="width:40px"/>{% endfor %}
        </colgroup>
        <thead>
          <tr><th>Área</th><th>Servicio</th>
            {% for d in month_days %}<th class="{% if d==today_day %}today{% endif %}">{{ d }}</th>{% endfor %}
          </tr>
        </thead>
        <tbody>
          {% for svc in ['Desayuno','Almuerzo','Cena'] %}
            <tr>
              {% if loop.index == 1 %}<td rowspan="3">{{ area }}</td>{% endif %}
              <td><strong>{{ svc }}</strong></td>
              {% set key = 'des' if svc=='Desayuno' else ('alm' if svc=='Almuerzo' else 'cen') %}
              {% for d, v in rows[key] %}
                <td class="{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}">
                  {% if v in ['SI','-'] %}
                    {{ v }}
                  {% else %}
                    <span class="cell" data-dia="{{ d }}" data-campo="{{ 'desayunos' if key=='des' else ('almuerzos' if key=='alm' else 'cenas') }}">{{ v }}</span>
                    <span class="editor" style="display:none">
                      <input class="small val" type="number" min="0" value="{{ v }}" style="width:68px">
                      <button class="small okbtn">OK</button>
                    </span>
                    <span class="status small" style="display:none">✔️</span>
                  {% endif %}
                </td>
              {% endfor %}
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  <div class="actions"><a class="warn" href="{{ url_for('admin') }}">← Volver</a></div>
</div>

<script>
document.querySelectorAll('span.cell').forEach(function(el){
  el.addEventListener('click', function(){
    const td = el.parentElement;
    td.querySelector('.cell').style.display='none';
    td.querySelector('.editor').style.display='inline-flex';
    td.querySelector('.status').style.display='none';
    td.querySelector('.val').focus();
  });
});

document.querySelectorAll('.okbtn').forEach(function(btn){
  btn.addEventListener('click', async function(e){
    e.preventDefault();
    const td = btn.closest('td');
    const cell = td.querySelector('.cell');
    const editor = td.querySelector('.editor');
    const status = td.querySelector('.status');
    const val = parseInt(td.querySelector('.val').value || '0');
    const dia = cell.getAttribute('data-dia');
    const campo = cell.getAttribute('data-campo');

    const payload = {
      centro: "{{ centro }}",
      fecha: "{{ year }}-{{ '%02d' % month }}-{{ '%02d' % 1 }}".replace('-01', '-' + ('00'+dia).slice(-2)), // yyyy-mm-dd del día del mes actual
      campo: campo,
      valor: val
    };

    try{
      const r = await fetch("{{ url_for('admin_update') }}", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(payload)
      });
      const j = await r.json();
      if(j.ok){
        cell.textContent = val;
        editor.style.display='none';
        cell.style.display='inline';
        status.style.display='inline';
        setTimeout(()=>{ status.style.display='none'; }, 1200);
      }else{
        alert("Error: " + (j.error||"no se pudo guardar"));
      }
    }catch(err){
      alert("Error de red");
    }
  });
});
</script>
"""

# -------------------------------------------------
# Helper render
# -------------------------------------------------
def render_page(inner_tpl, **ctx):
    inner = render_template_string(inner_tpl, **ctx)
    return render_template_string(BASE, content=inner, **ctx)


# -------------------------------------------------
# Admin lock routes
# -------------------------------------------------
@app.route('/admin/lock', methods=['POST'])
def admin_lock():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    lock_until = (request.form.get('lock_until') or '').strip()
    conn = db(); cur = conn.cursor()
    cur.execute(q("UPDATE settings SET value=? WHERE key='lock_until'"), (lock_until,))
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/lock/clear')
def admin_lock_clear():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    conn = db(); cur = conn.cursor()
    cur.execute(q("UPDATE settings SET value='' WHERE key='lock_until'"))
    conn.commit(); conn.close()
    return redirect(url_for('admin'))


# -------------------------------------------------
# Rutas principales
# -------------------------------------------------
@app.route('/', methods=['GET'])
def root():
    if session.get('email'):
        return redirect(url_for('formulario'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        conn = db(); cur = conn.cursor()
        cur.execute(q('SELECT * FROM users WHERE email=?'), (email,))
        u = cur.fetchone(); conn.close()
        if not u:
            return render_page(LOGIN_TPL, title='Ingresar', error='Correo no habilitado. Solicita a Servicios/TI el alta de tu centro.')
        session['email'] = u['email']
        session['centro'] = u['centro']
        session['area'] = u['area']
        session['user_id'] = u['id']
        if session['email'] in ADMIN_EMAILS:
            return redirect(url_for('admin'))
        return redirect(url_for('formulario'))
    return render_page(LOGIN_TPL, title='Ingresar', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/healthz')
def healthz():
    return jsonify(status="ok"), 200

def require_login():
    if not session.get('email'):
        return redirect(url_for('login'))


@app.route('/form', methods=['GET', 'POST'])
def formulario():
    if require_login():
        return require_login()
    from datetime import datetime, timedelta
    today = date.today()
    first_day = today.replace(day=1)
    next_month = first_day.replace(year=first_day.year + 1, month=1) if first_day.month == 12 else first_day.replace(month=first_day.month + 1)
    last_day = (next_month - timedelta(days=1)).day

    msg_ok = msg_err = None
    datos = {"desayunos":0, "almuerzos":0, "cenas":0, "total":0}
    selected_fecha = ''

    conn = db(); cur = conn.cursor()
    cur.execute(q("SELECT value FROM settings WHERE key='lock_until'"))
    row = cur.fetchone(); lock_until = (row['value'] or '').strip() if row else ''
    unlock_from = ''
    if lock_until:
        try:
            unlock_from = (datetime.fromisoformat(lock_until).date() + timedelta(days=1)).isoformat()
        except Exception:
            unlock_from = ''

    if request.method == 'POST':
        fecha = (request.form.get('fecha') or '').strip()
        selected_fecha = fecha
        if not fecha:
            msg_err = 'Selecciona una fecha.'
        elif lock_until and fecha <= lock_until:
            msg_err = f'Fecha bloqueada por administración (<= {lock_until}).'
        else:
            try:
                des = int(request.form.get('desayunos') or 0)
                alm = int(request.form.get('almuerzos') or 0)
                cen = int(request.form.get('cenas') or 0)
            except ValueError:
                des = alm = cen = -1
            if min(des, alm, cen) < 0:
                msg_err = 'Valores inválidos. Usa números enteros >= 0.'
            else:
                total = des + alm + cen
                cur2 = db().cursor()
                cur2.execute(q('SELECT 1 FROM reports WHERE email=? AND fecha=?'), (session['email'], fecha))
                exists = cur2.fetchone() is not None
                if exists:
                    msg_err = 'Ese día ya está cargado. Si necesitas corregirlo, contacta a Servicios.'
                else:
                    conn2 = db(); c2 = conn2.cursor()
                    c2.execute(q("""
                        INSERT INTO reports(user_id, email, centro, area, fecha, desayunos, almuerzos, cenas, total)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """), (session['user_id'], session['email'], session['centro'], session['area'], fecha, des, alm, cen, total))
                    conn2.commit(); conn2.close()
                    msg_ok = 'Registro enviado.'
                    datos = {"desayunos":des, "almuerzos":alm, "cenas":cen, "total":total}
                    selected_fecha = ''

    cur.execute(q('SELECT fecha, desayunos, almuerzos, cenas FROM reports WHERE email=? AND fecha BETWEEN ? AND ? ORDER BY fecha'),
                (session['email'], first_day.isoformat(), today.replace(day=last_day).isoformat()))
    rows = cur.fetchall(); conn.close()
    day_map = {int(r['fecha'].split('-')[-1]): (r['desayunos'], r['almuerzos'], r['cenas']) for r in rows}
    month_days = list(range(1, last_day+1)); today_day = today.day

    def val_for(d, idx):
        if d > today_day:
            return '-'
        return day_map[d][idx] if d in day_map else 'SI'

    row_des = [val_for(d,0) for d in month_days]
    row_alm = [val_for(d,1) for d in month_days]
    row_cen = [val_for(d,2) for d in month_days]
    meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    month_label = f"{meses[today.month-1]} {today.year}"

    blocks = [{
        'centro': session['centro'], 'area': session['area'],
        'des': list(zip(month_days, row_des)),
        'alm': list(zip(month_days, row_alm)),
        'cen': list(zip(month_days, row_cen)),
    }]

    return render_page(
        FORM_TPL, title='Carga diaria', hoy=today.isoformat(), datos=datos, ok=msg_ok, error=msg_err,
        lock_until=lock_until, selected_fecha=selected_fecha, month_days=month_days, month_label=month_label,
        today_day=today_day, unlock_from=unlock_from, blocks=blocks
    )


@app.route('/historial')
def historial():
    if require_login():
        return require_login()
    conn = db(); cur = conn.cursor()
    cur.execute(q('SELECT * FROM reports WHERE email=? ORDER BY fecha DESC'), (session['email'],))
    rows = cur.fetchall(); conn.close()
    return render_page(LOGIN_TPL.replace("Ingresar","Historial").replace("</form>",""), title='Historial', rows=rows)  # simple


# -------------------------------------------------
# ADMIN (resumen con link al detalle)
# -------------------------------------------------
@app.route('/admin')
def admin():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    area = (request.args.get('area') or '').strip()
    centro = (request.args.get('centro') or '').strip()

    conn = db(); cur = conn.cursor()
    cur.execute(q("SELECT value FROM settings WHERE key='lock_until'"))
    srow = cur.fetchone(); lock_until = (srow['value'] or '').strip() if srow else ''
    from datetime import datetime, timedelta
    unlock_from = ''
    if lock_until:
        try:
            unlock_from = (datetime.fromisoformat(lock_until).date() + timedelta(days=1)).isoformat()
        except Exception:
            unlock_from = ''

    today = date.today()
    first_day = today.replace(day=1)
    next_month = first_day.replace(year=first_day.year+1, month=1) if first_day.month == 12 else first_day.replace(month=first_day.month+1)
    last_day = (next_month - timedelta(days=1)).day
    month_days = list(range(1, last_day+1))
    meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    month_label = f"{meses[today.month-1]} {today.year}"
    today_day = today.day

    if area:
        cur.execute(q("SELECT centro FROM users WHERE area=? AND centro NOT IN ('ADMIN','AREA AYSEN') ORDER BY centro"), (area,))
    else:
        cur.execute(q("SELECT centro FROM users WHERE centro NOT IN ('ADMIN','AREA AYSEN') ORDER BY centro"))
    centers_all = [r['centro'] for r in cur.fetchall()]
    CENTROS_OPT = centers_all[:]
    centers_to_show = [c for c in centers_all if (not centro or c == centro)]

    def build_block(cname: str):
        cur.execute(q('SELECT fecha, desayunos, almuerzos, cenas, area FROM reports WHERE centro=? AND fecha BETWEEN ? AND ? ORDER BY fecha'),
                    (cname, first_day.isoformat(), today.replace(day=last_day).isoformat()))
        rws = cur.fetchall()
        if rws:
            carea = rws[0]['area']
        else:
            cur.execute(q('SELECT area FROM users WHERE centro=? LIMIT 1'), (cname,))
            urow = cur.fetchone(); carea = (urow['area'] if urow else '')
        dmap = {int(r['fecha'].split('-')[-1]): (r['desayunos'], r['almuerzos'], r['cenas']) for r in rws}

        def dot_val(d):
            if d > today_day:
                return '-'
            if d in dmap:
                _, alm, cen = dmap[d]
                return round((alm + cen)/2)
            return 'SI'

        row_dot = [dot_val(d) for d in month_days]
        return {'centro': cname, 'area': carea, 'dot': list(zip(month_days, row_dot))}

    blocks = [build_block(c) for c in centers_to_show]
    conn.close()

    return render_page(ADMIN_TPL, title='Tablero', AREAS=AREAS, area=area, centro=centro, CENTROS_OPT=CENTROS_OPT,
        lock_until=lock_until, unlock_from=unlock_from, month_days=month_days, month_label=month_label,
        today_day=today_day, blocks=blocks
    )


# -------------------------------------------------
# ADMIN — Detalle editable por centro
# -------------------------------------------------
@app.route('/admin/centro')
def admin_centro():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    centro = (request.args.get('c') or '').strip()
    if not centro:
        return redirect(url_for('admin'))

    conn = db(); cur = conn.cursor()
    # área
    cur.execute(q('SELECT area FROM users WHERE centro=? LIMIT 1'), (centro,))
    u = cur.fetchone()
    area = u['area'] if u else ''

    today = date.today()
    first_day = today.replace(day=1)
    next_month = first_day.replace(year=first_day.year+1, month=1) if first_day.month == 12 else first_day.replace(month=first_day.month+1)
    last_day = (next_month - __import__('datetime').timedelta(days=1)).day
    month_days = list(range(1, last_day+1))
    today_day = today.day
    year, month = today.year, today.month

    cur.execute(q('SELECT fecha, desayunos, almuerzos, cenas FROM reports WHERE centro=? AND fecha BETWEEN ? AND ? ORDER BY fecha'),
                (centro, first_day.isoformat(), today.replace(day=last_day).isoformat()))
    rws = cur.fetchall(); conn.close()
    dmap = {int(r['fecha'].split('-')[-1]): (r['desayunos'], r['almuerzos'], r['cenas']) for r in rws}

    def val_for(d, idx):
        if d > today_day:
            return '-'
        return dmap[d][idx] if d in dmap else 'SI'

    row_des = [val_for(d,0) for d in month_days]
    row_alm = [val_for(d,1) for d in month_days]
    row_cen = [val_for(d,2) for d in month_days]

    return render_page(
        DETAIL_TPL, title=f'Detalle {centro}', centro=centro, area=area,
        month_days=month_days, today_day=today_day,
        rows={'des': list(zip(month_days, row_des)),
              'alm': list(zip(month_days, row_alm)),
              'cen': list(zip(month_days, row_cen))},
        year=year, month=month
    )


# -------------------------------------------------
# ADMIN — API update (guardar edición inmediata)
# -------------------------------------------------
@app.post('/admin/update')
def admin_update():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return jsonify(ok=False, error="no_auth"), 403
    data = request.get_json(force=True, silent=True) or {}
    centro = (data.get('centro') or '').strip()
    fecha  = (data.get('fecha') or '').strip()
    campo  = (data.get('campo') or '').strip()   # desayunos | almuerzos | cenas
    try:
        valor = int(data.get('valor'))
        if valor < 0: raise ValueError
    except Exception:
        return jsonify(ok=False, error="valor_invalido"), 400

    if campo not in ('desayunos','almuerzos','cenas') or not centro or not fecha:
        return jsonify(ok=False, error="payload_invalido"), 400

    conn = db(); cur = conn.cursor()
    # Buscar un user de ese centro para llenar user_id/email/area
    cur.execute(q('SELECT id, email, area FROM users WHERE centro=? LIMIT 1'), (centro,))
    u = cur.fetchone()
    if not u:
        conn.close()
        return jsonify(ok=False, error="centro_no_configurado"), 400

    # ¿Existe report para ese centro-fecha?
    cur.execute(q('SELECT id, desayunos, almuerzos, cenas FROM reports WHERE centro=? AND fecha=? LIMIT 1'), (centro, fecha))
    r = cur.fetchone()

    if r:
        # update campo y total
        des, alm, cen = r['desayunos'], r['almuerzos'], r['cenas']
        if campo == 'desayunos': des = valor
        elif campo == 'almuerzos': alm = valor
        else: cen = valor
        total = des + alm + cen
        cur.execute(q(f'UPDATE reports SET {campo}=?, total=?, updated_at=CURRENT_TIMESTAMP WHERE id=?'),
                    (valor, total, r['id']))
    else:
        # insert con ceros excepto campo editado
        des = valor if campo == 'desayunos' else 0
        alm = valor if campo == 'almuerzos' else 0
        cen = valor if campo == 'cenas' else 0
        total = des + alm + cen
        cur.execute(q("""
            INSERT INTO reports(user_id, email, centro, area, fecha, desayunos, almuerzos, cenas, total)
            VALUES (?,?,?,?,?,?,?,?,?)
        """), (u['id'], u['email'], centro, u['area'], fecha, des, alm, cen, total))

    conn.commit(); conn.close()
    return jsonify(ok=True)


# -------------------------------------------------
# CSV export (modificado sin microsegundos)
# -------------------------------------------------
@app.route('/export.csv')
def export_csv():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    area = (request.args.get('area') or '').strip()
    centro = (request.args.get('centro') or '').strip()
    desde = (request.args.get('desde') or '').strip()
    hasta = (request.args.get('hasta') or '').strip()

    conn = db(); cur = conn.cursor()
    params = []
    where = []
    if area:
        where.append('area = ?'); params.append(area)
    if centro:
        where.append('centro = ?'); params.append(centro)
    if desde:
        where.append('fecha >= ?'); params.append(desde)
    if hasta:
        where.append('fecha <= ?'); params.append(hasta)

    sql = 'SELECT id, email, area, centro, fecha, desayunos, almuerzos, cenas, total, updated_at FROM reports'
    if where: sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY fecha DESC, centro'
    cur.execute(q(sql), params)
    rows = cur.fetchall(); conn.close()

    import io, csv
    from datetime import datetime

    def _fmt_ts(v):
        try:
            if hasattr(v, "strftime"):
                return v.strftime("%Y-%m-%d %H:%M:%S")
            v2 = str(v).replace("Z", "")
            return datetime.fromisoformat(v2).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(v)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(["id","usuario_carga","area","centro","fecha","nro_desayuno","nro_almuerzo","nro_cena","total","modificado"])
    for r in rows:
        w.writerow([
            r["id"], r["email"], r["area"], r["centro"], r["fecha"],
            r["desayunos"], r["almuerzos"], r["cenas"], r["total"],
            _fmt_ts(r["updated_at"])
        ])

    import io as iob
    mem = iob.BytesIO(buf.getvalue().encode('utf-8-sig')); mem.seek(0)
    name = f"dotacion_{(desde or 'ini')}_{(hasta or 'fin')}.csv"
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=name)


# -------------------------------------------------
# Self-tests (no-op)
# -------------------------------------------------
def run_self_tests():
    pass

def run_server():
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=False)

if __name__ == '__main__':
    app.jinja_env.globals['BASE'] = BASE
    run_server()

