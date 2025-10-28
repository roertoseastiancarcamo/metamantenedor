# app.py
# MVP: Carga diaria de desayunos, almuerzos y cenas por centro (login por correo)
# Ejecutar con Anaconda (recomendado):
#   conda create -n comedor python=3.11 -y
#   conda activate comedor
#   pip install flask
#   python app.py
# Abrir: http://127.0.0.1:5000

from flask import Flask, request, redirect, session, url_for
from flask import render_template_string, send_file
import sqlite3
import os
from datetime import date

app = Flask(__name__)
# Forzamos modo "producción" para evitar el debugger interno que intenta multiprocessing
app.config['ENV'] = 'production'
app.config['DEBUG'] = False
app.secret_key = os.environ.get("APP_SECRET", "dev-secret")
DB_PATH = os.environ.get("APP_DB", "data.db")

# -----------------------------
# Datos base (puedes editar/expandir)
# -----------------------------
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

# Administrador único (tablero/exportar)
ADMIN_EMAILS = set(os.environ.get("APP_ADMINS", "rcarcamo@multix").split(","))
AREAS = sorted({a for _, _, a in CENTROS})
CENTRO_NOMBRES = sorted({c for _, c, _ in CENTROS})

# -----------------------------
# DB helpers
# -----------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            centro TEXT NOT NULL,
            area TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
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
            UNIQUE(email, fecha),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    # tabla de configuración simple (clave/valor) para bloqueo por fecha
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    # valor por defecto para lock_until (vacío => sin bloqueo)
    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('lock_until', '')")

    # seed users (centros)
    for email, centro, area in CENTROS:
        try:
            cur.execute(
                "INSERT OR IGNORE INTO users(email, centro, area) VALUES (?,?,?)",
                (email, centro, area),
            )
        except Exception:
            pass
    # seed admins como usuarios (ADMIN/SERVICIOS)
    for adm in ADMIN_EMAILS:
        try:
            cur.execute(
                "INSERT OR IGNORE INTO users(email, centro, area) VALUES (?,?,?)",
                (adm.strip().lower(), 'ADMIN', 'SERVICIOS'),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()


# Inicializa la base de datos al arrancar la app (Flask ≥ 3 ya no tiene before_first_request)
with app.app_context():
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()


# -----------------------------
# Templates (inline para mantener 1 archivo)
# -----------------------------
# --- Plantillas ---
# BASE envuelve el contenido en {{ content }}
BASE = """
<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>
  <title>{{ title or 'Dotación Comedor Diario' }}</title>
  <style>
    :root{--brand:#1e3a8a;--brand-2:#0ea5e9;--bg:#f7f8fb;--text:#0f172a;--muted:#64748b}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,sans-serif;margin:0;background:var(--bg);color:var(--text);font-size:14px}
    header{display:flex;justify-content:space-between;align-items:center;padding:28px 28px;background:var(--brand);color:#fff}
    main{max-width:1360px;margin:24px auto;padding:0 20px}
    .card{background:#fff;border-radius:14px;box-shadow:0 2px 10px rgba(2,6,23,.06);padding:18px;margin-bottom:16px}
    input,select,button{font-size:14px;padding:8px 10px;border-radius:10px;border:1px solid #e5e7eb}
    input[type=date]{padding:6px 8px}
    label{display:block;margin:8px 0 6px;font-weight:600}
    .row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    .row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .actions{display:flex;gap:10px;margin-top:12px}
    .ok{background:var(--brand);color:#fff;border:none}
    .warn{background:var(--brand-2);color:#fff;border:none}
    .danger{background:#ef4444;color:#fff;border:none}
    table{width:100%;border-collapse:collapse}
    th,td{padding:8px;border-bottom:1px solid #eef2f7;text-align:left;white-space:nowrap}
    thead th{background:#f0f4ff}
    .badge{padding:3px 7px;border-radius:999px;font-size:11px}
    .b-enviado{background:#dbeafe}
    .b-aprobado{background:#dcfce7}
    .b-observado{background:#fee2e2}
    .xscroll{overflow-x:auto}
    .minw{min-width:1280px}
    .muted{color:var(--muted)}
    .si{color:#dc2626;font-weight:600}
    .today{outline:2px solid #ef4444; outline-offset:-2px; border-radius:4px}
    header strong{font-size:20px;letter-spacing:.2px}
    .logo-fixed{position:fixed;left:16px;bottom:16px;height:40px;opacity:.95}
  </style>
</head>
<body>
<header>
  <div style=\"display:flex;align-items:center;gap:8px\">
    <!-- Logo movido al pie -->
    <strong>Registro de platos preparados Multi‑X</strong>
  </div>
  <div>
    {% if session.get('email') %}
      {{ session.email }} — {{ session.centro }} ({{ session.area }})
      <a style=\"margin-left:12px;color:#fff\" href=\"{{ url_for('logout') }}\">Salir</a>
    {% endif %}
  </div>
</header>
<main>
  {{ content|safe }}
</main>
  <img class=\"logo-fixed\" src=\"{{ url_for('static', filename='logo.png') }}\" alt=\"Multi-X\"/>
</body>
</html>
"""

LOGIN_TPL = """
<div class=\"card\">
  <h2>Ingresar</h2>
  <p>Escribe tu <strong>correo corporativo</strong>. No requiere clave.</p>
  {% if error %}<p style=\"color:#b91c1c\">{{ error }}</p>{% endif %}
  <form method=\"post\">
    <label>Correo</label>
    <input type=\"email\" name=\"email\" placeholder=\"usuario@multix\" required style=\"width:100%\" />
    <div class=\"actions\">
      <button class=\"ok\" type=\"submit\">Entrar</button>
    </div>
  </form>
</div>
"""

FORM_TPL = """
<div class=\"card\">
  <h2>Carga diaria</h2>
  {% if lock_until %}
    <p style=\"background:#fff3cd;border:1px solid #ffe58f;color:#7a5d00;padding:10px;border-radius:8px\">Bloqueado hasta: <strong>{{ lock_until }}</strong>. No se permite cargar fechas anteriores a esa fecha. | <strong>Liberado para editar desde:</strong> {{ unlock_from or '—' }}.</p>
  {% endif %}
  <form method=\"post\">
    <div class=\"row2\"> 
      <div>
        <label>Centro</label>
        <input value=\"{{ session.centro }}\" disabled/>
      </div>
      <div>
        <label>Área</label>
        <input value=\"{{ session.area }}\" disabled/>
      </div>
    </div>
    <div class=\"row2\"> 
      <div>
        <label>Fecha</label>
        <input type=\"date\" name=\"fecha\" value=\"{{ selected_fecha or '' }}\" required />
      </div>
      <div>
        <label>Total (auto)</label>
        <input value=\"{{ datos.total or 0 }}\" disabled/>
      </div>
    </div>
    <div class=\"row\">
      <div>
        <label>Desayunos</label>
        <input type=\"number\" min=\"0\" name=\"desayunos\" value=\"{{ datos.desayunos or 0 }}\" required />
      </div>
      <div>
        <label>Almuerzos</label>
        <input type=\"number\" min=\"0\" name=\"almuerzos\" value=\"{{ datos.almuerzos or 0 }}\" required />
      </div>
      <div>
        <label>Cenas</label>
        <input type=\"number\" min=\"0\" name=\"cenas\" value=\"{{ datos.cenas or 0 }}\" required />
      </div>
    </div>
    {% if error %}<p style=\"color:#b91c1c\">{{ error }}</p>{% endif %}
    {% if ok %}<p style=\"color:#166534\">{{ ok }}</p>{% endif %}
    <div class=\"actions\">
      <button class=\"ok\" type=\"submit\">Enviar</button>
      <a class=\"warn\" style=\"text-decoration:none;padding:10px 12px;border-radius:10px\" href=\"{{ url_for('historial') }}\">Historial</a>
    </div>
  </form>
</div>

{% if ok %}
<script>
  // Alerta simple al guardar correctamente
  setTimeout(function(){
    alert("Registro enviado para {{ session.centro }} el {{ (selected_fecha or '') | e }}");
  }, 10);
</script>
{% endif %}

<div class=\"card xscroll\">
  <h3 style=\"margin-top:0;text-align:center\">{{ month_label }}</h3>
  {% if blocks %}
    {% for b in blocks %}
      <div class=\"minw\" style=\"margin-bottom:12px\">
        <table>
          <thead>
            <tr>
              <th>Área</th>
              <th>Centro</th>
              <th>Servicio</th>
              {% for d in month_days %}<th class=\"{% if d==today_day %}today{% endif %}\">{{ d }}</th>{% endfor %}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td rowspan=\"3\">{{ b.area }}</td>
              <td rowspan=\"3\">{{ b.centro }}</td>
              <td><strong>Desayuno</strong></td>
              {% for d, v in b.des %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
            </tr>
            <tr>
              <td><strong>Almuerzo</strong></td>
              {% for d, v in b.alm %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
            </tr>
            <tr>
              <td><strong>Cena</strong></td>
              {% for d, v in b.cen %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
            </tr>
          </tbody>
        </table>
      </div>
    {% endfor %}
  {% else %}
    <p class=\"muted\" style=\"text-align:center\">No hay centros para mostrar con los filtros actuales.</p>
  {% endif %}
  <p style=\"margin-top:8px;color:#6b7280\"><strong>Leyenda:</strong> SI = sin información, - = futuro &nbsp;|&nbsp; <strong>Bloqueado hasta:</strong> {{ lock_until or '—' }} &nbsp;|&nbsp; <strong>Liberado desde:</strong> {{ unlock_from or '—' }}</p>
</div>
"""

HIST_TPL = """
<div class=\"card\">
  <h2>Historial</h2>
  <table>
    <thead><tr><th>Fecha</th><th>Desayunos</th><th>Almuerzos</th><th>Cenas</th><th>Total</th><th>Estado</th><th>Modificado</th></tr></thead>
    <tbody>
      {% for r in rows %}
        <tr>
          <td>{{ r['fecha'] }}</td>
          <td>{{ r['desayunos'] }}</td>
          <td>{{ r['almuerzos'] }}</td>
          <td>{{ r['cenas'] }}</td>
          <td>{{ r['total'] }}</td>
          <td><span class=\"badge b-{{ r['estado'] }}\">{{ r['estado'] }}</span></td>
          <td>{{ r['updated_at'] }}</td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
"""

ADMIN_TPL = """
<div class=\"card\" style=\"display:grid;grid-template-columns:1fr 340px;gap:16px;align-items:start\">
  <div>
    <h2 style=\"margin-top:0\">Tablero (Admin/Servicios)</h2>
    <form method=\"get\" id=\"filtros\" class=\"row2\" style=\"align-items:end\">
      <div>
        <label>Área</label>
        <select name=\"area\" onchange=\"this.form.submit()\">
          <option value=\"\">Todas</option>
          {% for a in AREAS %}<option value=\"{{a}}\" {% if a==area %}selected{% endif %}>{{a}}</option>{% endfor %}
        </select>
      </div>
      <div>
        <label>Centro</label>
        <select name=\"centro\" onchange=\"this.form.submit()\">
          <option value=\"\">Todos</option>
          {% for c in CENTROS_OPT %}<option value=\"{{c}}\" {% if c==centro %}selected{% endif %}>{{c}}</option>{% endfor %}
        </select>
      </div>
      <div class=\"actions\" style=\"margin:0\">
        <a class=\"warn\" style=\"text-decoration:none;padding:8px 10px;border-radius:10px;height:36px;display:inline-flex;align-items:center\" href=\"{{ url_for('export_csv', area=area, centro=centro) }}\">Descargar Datos</a>
      </div>
    </form>
  </div>
  <div class=\"card\">
    <h3 style=\"margin-top:0\">Bloquear hasta</h3>
    <form method=\"post\" action=\"{{ url_for('admin_lock') }}\">
      <label>Fecha límite (inclusive)</label>
      <input type=\"date\" name=\"lock_until\" />
      <div class=\"actions\" style=\"margin-top:10px\">
        <button class=\"danger\" type=\"submit\">Guardar</button>
        <a href=\"{{ url_for('admin_lock_clear') }}\" class=\"warn\" style=\"text-decoration:none;padding:10px 12px;border-radius:10px\">Quitar bloqueo</a>
      </div>
      <p class=\"muted\">Actualmente bloqueado hasta: <strong>{{ lock_until or '—' }}</strong><br>Liberado desde: <strong>{{ unlock_from or '—' }}</strong></p>
    </form>
  </div>
</div>

<div class=\"card xscroll\" style=\"overflow-x:auto\">
  <h3 style=\"margin-top:0;text-align:center\">{{ month_label }}</h3>
  <div class=\"minw\" style=\"min-width:1280px\">
    <table style=\"table-layout:fixed\">
      <colgroup>
        <col style=\"width:120px\"/>
        <col style=\"width:140px\"/>
        <col style=\"width:120px\"/>
        {% for d in month_days %}<col style=\"width:40px\"/>{% endfor %}
      </colgroup>
      <thead>
        <tr>
          <th>Área</th>
          <th>Centro</th>
          <th>Servicio</th>
          {% for d in month_days %}<th class=\"{% if d==today_day %}today{% endif %}\">{{ d }}</th>{% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for b in blocks %}
          <tr>
            <td rowspan=\"3\">{{ b.area }}</td>
            <td rowspan=\"3\">{{ b.centro }}</td>
            <td><strong>Desayuno</strong></td>
            {% for d, v in b.des %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
          </tr>
          <tr>
            <td><strong>Almuerzo</strong></td>
            {% for d, v in b.alm %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
          </tr>
          <tr>
            <td><strong>Cena</strong></td>
            {% for d, v in b.cen %}<td class=\"{% if v=='SI' %}si{% endif %} {% if d==today_day %}today{% endif %}\">{{ v }}</td>{% endfor %}
          </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  <p style=\"margin-top:8px;color:#6b7280\"><strong>Leyenda:</strong> SI = sin información, - = futuro &nbsp;|&nbsp; <strong>Bloqueado hasta:</strong> {{ lock_until or '—' }} &nbsp;|&nbsp; <strong>Liberado desde:</strong> {{ unlock_from or '—' }}</p>
</div>
"""

# -----------------------------
# Helper para renderizar dentro de BASE
# -----------------------------

def render_page(inner_tpl, **ctx):
    inner = render_template_string(inner_tpl, **ctx)
    return render_template_string(BASE, content=inner, **ctx)

# -----------------------------
# Rutas de administración (bloqueo por fecha)
# -----------------------------

@app.route('/admin/lock', methods=['POST'])
def admin_lock():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    lock_until = (request.form.get('lock_until') or '').strip()
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE settings SET value=? WHERE key='lock_until'", (lock_until,))
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/lock/clear')
def admin_lock_clear():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    conn = db(); cur = conn.cursor()
    cur.execute("UPDATE settings SET value='' WHERE key='lock_until'")
    conn.commit(); conn.close()
    return redirect(url_for('admin'))

# -----------------------------
# Rutas existentes
# -----------------------------

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
        cur.execute('SELECT * FROM users WHERE email=?', (email,))
        u = cur.fetchone()
        conn.close()
        if not u:
            return render_page(LOGIN_TPL, title='Ingresar', error='Correo no habilitado. Solicita a Servicios/TI el alta de tu centro.')
        session['email'] = u['email']
        session['centro'] = u['centro']
        session['area'] = u['area']
        session['user_id'] = u['id']
        # Si es admin, envía directo al tablero
        if session['email'] in ADMIN_EMAILS:
            return redirect(url_for('admin'))
        return redirect(url_for('formulario'))
    return render_page(LOGIN_TPL, title='Ingresar', error=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/health')
def health():
    return 'ok', 200


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
    # último día del mes en curso
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year+1, month=1)
    else:
        next_month = first_day.replace(month=first_day.month+1)
    last_day = (next_month - timedelta(days=1)).day

    msg_ok = msg_err = None
    datos = {"desayunos":0, "almuerzos":0, "cenas":0, "total":0}
    selected_fecha = ''

    # obtener lock_until + unlock_from
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='lock_until'")
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
                cur2.execute('SELECT 1 FROM reports WHERE email=? AND fecha=?', (session['email'], fecha))
                exists = cur2.fetchone() is not None
                if exists:
                    msg_err = 'Ese día ya está cargado. Si necesitas corregirlo, contacta a Servicios.'
                else:
                    conn2 = db(); c2 = conn2.cursor()
                    c2.execute(
                        """
                        INSERT INTO reports(user_id, email, centro, area, fecha, desayunos, almuerzos, cenas, total)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (session['user_id'], session['email'], session['centro'], session['area'], fecha, des, alm, cen, total)
                    )
                    conn2.commit(); conn2.close()
                    msg_ok = 'Registro enviado.'
                    datos = {"desayunos":des, "almuerzos":alm, "cenas":cen, "total":total}
                    selected_fecha = ''

    # construir línea de tiempo del mes en curso para este usuario
    conn = db(); cur = conn.cursor()
    cur.execute('SELECT fecha, desayunos, almuerzos, cenas FROM reports WHERE email=? AND fecha BETWEEN ? AND ? ORDER BY fecha', (
        session['email'], first_day.isoformat(), today.replace(day=last_day).isoformat()
    ))
    rows = cur.fetchall(); conn.close()
    day_map = {int(r['fecha'].split('-')[-1]): (r['desayunos'], r['almuerzos'], r['cenas']) for r in rows}
    month_days = list(range(1, last_day+1))
    today_day = today.day
    def val_for(d, idx):
        if d > today_day:
            return '-'
        return day_map[d][idx] if d in day_map else 'SI'
    row_des = [val_for(d,0) for d in month_days]
    row_alm = [val_for(d,1) for d in month_days]
    row_cen = [val_for(d,2) for d in month_days]
    meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    month_label = f"{meses[today.month-1]} {today.year}"

    # bloque para plantilla (un solo centro: el del usuario)
    blocks = [{
        'centro': session['centro'],
        'area': session['area'],
        'des': list(zip(month_days, row_des)),
        'alm': list(zip(month_days, row_alm)),
        'cen': list(zip(month_days, row_cen)),
    }]

    return render_page(
        FORM_TPL,
        title='Carga diaria',
        hoy=today.isoformat(),
        datos=datos,
        ok=msg_ok,
        error=msg_err,
        lock_until=lock_until,
        selected_fecha=selected_fecha,
        month_days=month_days,
        month_label=month_label,
        today_day=today_day,
        unlock_from=unlock_from,
        blocks=blocks,
    )


@app.route('/historial')
def historial():
    if require_login():
        return require_login()
    conn = db(); cur = conn.cursor()
    cur.execute('SELECT * FROM reports WHERE email=? ORDER BY fecha DESC', (session['email'],))
    rows = cur.fetchall(); conn.close()
    return render_page(HIST_TPL, title='Historial', rows=rows)


@app.route('/admin')
def admin():
    if not session.get('email') or session['email'] not in ADMIN_EMAILS:
        return redirect(url_for('login'))
    area = (request.args.get('area') or '').strip()
    centro = (request.args.get('centro') or '').strip()

    conn = db(); cur = conn.cursor()
    # lock_until actual + unlock_from
    cur.execute("SELECT value FROM settings WHERE key='lock_until'")
    srow = cur.fetchone(); lock_until = (srow['value'] or '').strip() if srow else ''
    unlock_from = ''
    if lock_until:
        try:
            from datetime import datetime, timedelta
            unlock_from = (datetime.fromisoformat(lock_until).date() + timedelta(days=1)).isoformat()
        except Exception:
            unlock_from = ''

    # timeline: armar para centros según filtro de área
    from datetime import timedelta
    today = date.today()
    first_day = today.replace(day=1)
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year+1, month=1)
    else:
        next_month = first_day.replace(month=first_day.month+1)
    last_day = (next_month - timedelta(days=1)).day
    month_days = list(range(1, last_day+1))
    meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    month_label = f"{meses[today.month-1]} {today.year}"
    today_day = today.day

    # determinar lista de centros y opciones de combo (excluye ADMIN/AREA AYSEN)
    if area:
        cur.execute("SELECT centro FROM users WHERE area=? AND centro NOT IN ('ADMIN','AREA AYSEN') ORDER BY centro", (area,))
    else:
        cur.execute("SELECT centro FROM users WHERE centro NOT IN ('ADMIN','AREA AYSEN') ORDER BY centro")
    centers_all = [r['centro'] for r in cur.fetchall()]
    # opciones para el select
    CENTROS_OPT = centers_all[:]
    # aplicar filtro de centro si viene
    if centro:
        centers_to_show = [c for c in centers_all if c == centro]
    else:
        centers_to_show = centers_all

    def build_block(cname: str):
        cur.execute('SELECT fecha, desayunos, almuerzos, cenas, area FROM reports WHERE centro=? AND fecha BETWEEN ? AND ? ORDER BY fecha', (
            cname, first_day.isoformat(), today.replace(day=last_day).isoformat()
        ))
        rws = cur.fetchall()
        carea = ''
        if rws:
            carea = rws[0]['area']
        else:
            cur.execute('SELECT area FROM users WHERE centro=? LIMIT 1', (cname,))
            urow = cur.fetchone(); carea = (urow['area'] if urow else '')
        dmap = {int(r['fecha'].split('-')[-1]): (r['desayunos'], r['almuerzos'], r['cenas']) for r in rws}
        def aval(d, idx):
            if d > today_day:
                return '-'
            return dmap[d][idx] if d in dmap else 'SI'
        row_des = [aval(d,0) for d in month_days]
        row_alm = [aval(d,1) for d in month_days]
        row_cen = [aval(d,2) for d in month_days]
        return {
            'centro': cname,
            'area': carea,
            'des': list(zip(month_days, row_des)),
            'alm': list(zip(month_days, row_alm)),
            'cen': list(zip(month_days, row_cen)),
        }

    blocks = [build_block(c) for c in centers_to_show]

    conn.close()

    return render_page(ADMIN_TPL,
        title='Tablero', AREAS=AREAS, area=area, centro=centro, CENTROS_OPT=CENTROS_OPT,
        lock_until=lock_until, unlock_from=unlock_from,
        month_days=month_days, month_label=month_label,
        today_day=today_day, blocks=blocks
    )


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
    cur.execute(sql, params)
    rows = cur.fetchall(); conn.close()

    import io, csv
    buf = io.StringIO()
    # Usamos utf-8-sig para que Excel cree columnas correctamente sin caracteres extra al inicio
    w = csv.writer(buf, delimiter=';')  # separador que Excel (ES/CL) abre en columnas
    w.writerow(["id","usuario_carga","area","centro","fecha","nro_desayuno","nro_almuerzo","nro_cena","total","modificado"])
    for r in rows:
        w.writerow([r["id"], r["email"], r["area"], r["centro"], r["fecha"], r["desayunos"], r["almuerzos"], r["cenas"], r["total"], r["updated_at"]])
    mem = io.BytesIO(buf.getvalue().encode('utf-8-sig')); mem.seek(0)
    name = f"dotacion_{(desde or 'ini')}_{(hasta or 'fin')}.csv"
    return send_file(mem, mimetype='text/csv', as_attachment=True, download_name=name)


# -----------------------------
# Self-tests opcionales (para TI) — setea RUN_SELF_TESTS=1 para ejecutarlos y salir
# -----------------------------

def run_self_tests():
    import io, csv
    global DB_PATH
    test_db = 'selftest.db'
    try:
        if os.path.exists(test_db):
            os.remove(test_db)
    except Exception:
        pass
    old = DB_PATH
    DB_PATH = test_db
    init_db()

    # 1) usuarios sembrados: verificar presencia de todos los CENTROS y de todos los ADMIN_EMAILS
    conn = db(); cur = conn.cursor()
    for email, _, _ in CENTROS:
        cur.execute('SELECT 1 FROM users WHERE email=?', (email,))
        assert cur.fetchone(), f"Falta sembrar centro: {email}"
    for adm in {a.strip().lower() for a in ADMIN_EMAILS}:
        cur.execute('SELECT 1 FROM users WHERE email=?', (adm,))
        assert cur.fetchone(), f"Falta sembrar admin: {adm}"
    # (opcional) verificar que no existan emails duplicados
    cur.execute('SELECT COUNT(*), COUNT(DISTINCT email) FROM users')
    total, distintos = cur.fetchone()
    assert total == distintos, f"Usuarios duplicados detectados: total={total}, distintos={distintos}"

    # 2) upsert de reportes por conflicto (email, fecha)
    email0 = CENTROS[0][0]
    cur.execute('SELECT id, centro, area FROM users WHERE email=?', (email0,))
    urow = cur.fetchone(); uid = urow['id']; centro0 = urow['centro']; area0 = urow['area']
    fecha = '2025-01-01'
    # primer insert
    cur.execute(
        """
        INSERT INTO reports(user_id,email,centro,area,fecha,desayunos,almuerzos,cenas,total)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (uid, email0, centro0, area0, fecha, 1, 2, 3, 6)
    )
    # upsert (update)
    cur.execute(
        """
        INSERT INTO reports(user_id,email,centro,area,fecha,desayunos,almuerzos,cenas,total)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(email, fecha) DO UPDATE SET desayunos=excluded.desayunos, almuerzos=excluded.almuerzos,
            cenas=excluded.cenas, total=excluded.total
        """,
        (uid, email0, centro0, area0, fecha, 10, 20, 30, 60)
    )
    conn.commit()
    cur.execute('SELECT desayunos, almuerzos, cenas, total FROM reports WHERE email=? AND fecha=?', (email0, fecha))
    row = cur.fetchone()
    assert tuple(row) == (10, 20, 30, 60), f"Upsert falló: {tuple(row)}"

    # 3) export CSV simulado (no dependemos de estados)
    cur.execute('SELECT centro, area, fecha, desayunos, almuerzos, cenas, total, estado, updated_at FROM reports WHERE fecha=? ORDER BY centro', (fecha,))
    rows = cur.fetchall()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["centro","area","fecha","desayunos","almuerzos","cenas","total","estado","modificado"])
    for r in rows:
        w.writerow([r["centro"], r["area"], r["fecha"], r["desayunos"], r["almuerzos"], r["cenas"], r["total"], r["estado"], r["updated_at"]])
    out = buf.getvalue().strip().splitlines()
    assert len(out) >= 2, 'Export CSV vacío'
    header_cols = out[0].split(',')
    assert len(header_cols) == 9, f'CSV con columnas incorrectas: {len(header_cols)}'

    # 4) duplicado mismo día: debe violar UNIQUE(email, fecha)
    dup_error = False
    try:
        cur.execute(
            """
            INSERT INTO reports(user_id,email,centro,area,fecha,desayunos,almuerzos,cenas,total)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (uid, email0, centro0, area0, fecha, 5, 5, 5, 15)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        dup_error = True
        conn.rollback()
    assert dup_error, 'Se esperaba UNIQUE(email, fecha) en duplicado de fecha y no ocurrió'

    # 5) lock_until almacenado y leído
    cur.execute("UPDATE settings SET value=? WHERE key='lock_until'", ('2025-01-05',))
    conn.commit()
    cur.execute("SELECT value FROM settings WHERE key='lock_until'")
    v = (cur.fetchone()['value'] or '').strip()
    assert v == '2025-01-05', 'lock_until no persistió correctamente'

    conn.close()

    # 6) rutas básicas con test_client (sin abrir puertos)
    with app.test_client() as c:
        r = c.get('/health')
        assert r.status_code == 200 and r.data == b'ok', 'Healthcheck falló'
        r = c.post('/login', data={'email': email0}, follow_redirects=False)
        assert r.status_code in (302, 303) and '/form' in (r.headers.get('Location') or ''), 'Login no redirigió a /form'

    # limpiar
    DB_PATH = old
    try:
        os.remove(test_db)
    except Exception:
        pass
    print('SELF TESTS OK')


# -----------------------------
# Run (evita multiprocessing y OSError en entornos sin sockets)
# -----------------------------

def run_server():
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '5000'))
    try:
        # Arranque "simple" sin reloader, sin debugger y sin threads
        app.run(host=host, port=port, debug=False, use_reloader=False, threaded=False)
    except OSError as e:
        # Entornos restringidos (p.ej. sandbox) pueden no permitir sockets -> mostramos guía y ejecutamos self-tests
        print(f"\n⚠️ No se pudo abrir el puerto {host}:{port}: {e}")
        print("Sugerencias: 1) Ejecuta en tu PC con Anaconda Prompt; 2) Cambia el puerto con PORT=5001; 3) Verifica antivirus/firewall.")
        if os.environ.get('RUN_SELF_TESTS', '0') != '1':
            print("Ejecutando SELF TESTS como verificación mínima sin servidor...")
            run_self_tests()
    except SystemExit:
        # Werkzueg/serving puede llamar sys.exit(1) en algunos entornos: no abortamos duro
        print("\n⚠️ El servidor pidió salir (SystemExit). Ejecutando SELF TESTS...")
        if os.environ.get('RUN_SELF_TESTS', '0') != '1':
            run_self_tests()


if __name__ == '__main__':
    app.jinja_env.globals['BASE'] = BASE
    if os.environ.get('RUN_SELF_TESTS', '0') == '1':
        run_self_tests()
    else:
        run_server()
