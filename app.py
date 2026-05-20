from decimal import Decimal
from flask import (Flask, render_template, request, session,
                   redirect, url_for, flash, jsonify, send_from_directory)
import pymysql, pymysql.cursors
import os, json, uuid, random, threading
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import math, hashlib
from functools import wraps

# ─── ZONA HORARIA COLOMBIA (UTC-5) ───────────────────────────
TZ_COL = timezone(timedelta(hours=-5))
def now_col():
    return datetime.now(TZ_COL).replace(tzinfo=None)

# ─── APP ─────────────────────────────────────────────────────
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')

app.secret_key = 'urbanalert-clave-secreta-2026'

# ─── FIX: Decimal → float para tojson en templates ──────────
class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)

app.json_encoder = _DecimalEncoder

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── CREDENCIALES BD ─────────────────────────────────────────
# Carga .env local si existe (desarrollo).
# En produccion (Render) las variables ya vienen inyectadas.
_env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(_env_path):
    for _line in open(_env_path):
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

MYSQL_HOST     = os.environ.get('MYSQL_HOST',     'localhost')
MYSQL_USER     = os.environ.get('MYSQL_USER',     'root')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '0000')
MYSQL_DB       = os.environ.get('MYSQL_DB',       'urban_alert')
MYSQL_PORT     = int(os.environ.get('MYSQL_PORT', 3306))
app.secret_key = os.environ.get('SECRET_KEY',     'urbanalert-clave-secreta-2026')

# ─── DB ──────────────────────────────────────────────────────
def get_db():
    return pymysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        port=MYSQL_PORT,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )

def init_db():
    """Crea la BD si no existe. No toca datos existentes."""
    # Crear base de datos si no existe
    conn0 = pymysql.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD,
        port=MYSQL_PORT, charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor, connect_timeout=10,
    )
    cur0 = conn0.cursor()
    cur0.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` "
                 "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn0.commit(); cur0.close(); conn0.close()

    conn = get_db(); cur = conn.cursor()

    # Roles
    cur.execute("""CREATE TABLE IF NOT EXISTS roles (
        id        INT PRIMARY KEY AUTO_INCREMENT,
        nombre    VARCHAR(50) NOT NULL UNIQUE,
        descripcion TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("SELECT COUNT(*) as c FROM roles")
    if cur.fetchone()['c'] == 0:
        cur.execute("""INSERT INTO roles (nombre, descripcion) VALUES
            ('visitante',     'Acceso público sin cuenta'),
            ('ciudadano',     'Puede crear reportes y hacer seguimiento'),
            ('tecnico',       'Recibe asignaciones y resuelve reportes'),
            ('administrador', 'Gestiona plataforma, usuarios y asignaciones'),
            ('super_admin',   'Control total del sistema')""")

    # Usuarios
    cur.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id               INT PRIMARY KEY AUTO_INCREMENT,
        nombre           VARCHAR(100) NOT NULL,
        apellido         VARCHAR(100),
        email            VARCHAR(150) NOT NULL UNIQUE,
        password_hash    VARCHAR(255) NOT NULL,
        telefono         VARCHAR(20),
        ciudad           ENUM('Facatativá','Madrid','Mosquera') DEFAULT 'Facatativá',
        rol_id           INT NOT NULL DEFAULT 2,
        activo           BOOLEAN DEFAULT TRUE,
        email_verificado BOOLEAN DEFAULT TRUE,
        ultimo_login     TIMESTAMP NULL,
        creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        actualizado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (rol_id) REFERENCES roles(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Categorías
    cur.execute("""CREATE TABLE IF NOT EXISTS categorias (
        id        INT PRIMARY KEY AUTO_INCREMENT,
        nombre    VARCHAR(100) NOT NULL,
        descripcion TEXT,
        icono     VARCHAR(50),
        color     VARCHAR(7) DEFAULT '#FF6B00',
        activa    BOOLEAN DEFAULT TRUE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("SELECT COUNT(*) as c FROM categorias")
    if cur.fetchone()['c'] == 0:
        cur.execute("""INSERT INTO categorias (nombre, descripcion, icono, color) VALUES
            ('Bache / Pavimento',  'Huecos, grietas y daños en la vía',               'road',      '#E74C3C'),
            ('Basura / Residuos',  'Acumulación de basura o depósito ilegal',          'trash',     '#F39C12'),
            ('Espacio Público',    'Daños en andenes, parques, mobiliario urbano',     'building',  '#9B59B6'),
            ('Señalización Vial',  'Señales dañadas, semáforos en mal estado',        'signpost',  '#E67E22'),
            ('Alumbrado Público',  'Postes o luminarias apagados o peligrosos',       'lightbulb', '#F1C40F'),
            ('Árbol / Vegetación', 'Árboles caídos, ramas peligrosas',               'tree',      '#27AE60'),
            ('Inundación',         'Encharcamiento, desbordamiento de canales',        'droplets',  '#2980B9'),
            ('Otro',               'Situaciones que no encajan en otras categorías',   'flag',      '#7F8C8D')""")

    # Reportes
    cur.execute("""CREATE TABLE IF NOT EXISTS reportes (
        id               INT PRIMARY KEY AUTO_INCREMENT,
        titulo           VARCHAR(200) NOT NULL,
        descripcion      TEXT,
        categoria_id     INT NOT NULL,
        ciudad           ENUM('Facatativá','Madrid','Mosquera') NOT NULL,
        direccion        VARCHAR(300),
        latitud          DECIMAL(10,8),
        longitud         DECIMAL(11,8),
        estado           ENUM('pendiente','en_revision','aprobado','asignado',
                              'en_progreso','resuelto','rechazado','duplicado') DEFAULT 'pendiente',
        prioridad        ENUM('baja','media','alta','critica') DEFAULT 'media',
        gravedad_ia      DECIMAL(5,2),
        usuario_id       INT,
        tecnico_id       INT,
        admin_id         INT,
        imagen_principal VARCHAR(255),
        analisis_ia      JSON,
        es_duplicado     BOOLEAN DEFAULT FALSE,
        votos            INT DEFAULT 0,
        vistas           INT DEFAULT 0,
        publico          BOOLEAN DEFAULT TRUE,
        fecha_asignacion TIMESTAMP NULL,
        fecha_resolucion TIMESTAMP NULL,
        creado_en        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        actualizado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (categoria_id) REFERENCES categorias(id),
        FOREIGN KEY (usuario_id)   REFERENCES usuarios(id),
        FOREIGN KEY (tecnico_id)   REFERENCES usuarios(id),
        FOREIGN KEY (admin_id)     REFERENCES usuarios(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Tecnicos
    cur.execute("""CREATE TABLE IF NOT EXISTS tecnicos (
        id                 INT PRIMARY KEY AUTO_INCREMENT,
        usuario_id         INT NOT NULL UNIQUE,
        especialidad       VARCHAR(150),
        zona_cobertura     ENUM('Facatativá','Madrid','Mosquera','Todas') DEFAULT 'Todas',
        disponible         BOOLEAN DEFAULT TRUE,
        reportes_activos   INT DEFAULT 0,
        reportes_resueltos INT DEFAULT 0,
        calificacion       DECIMAL(3,2) DEFAULT 5.0,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Horario disponibilidad técnicos
    cur.execute("""CREATE TABLE IF NOT EXISTS horario_tecnico (
        id          INT PRIMARY KEY AUTO_INCREMENT,
        tecnico_id  INT NOT NULL,
        dia_semana  TINYINT NOT NULL COMMENT '0=Lun,1=Mar,2=Mie,3=Jue,4=Vie,5=Sab,6=Dom',
        hora_inicio TIME NOT NULL DEFAULT '07:00:00',
        hora_fin    TIME NOT NULL DEFAULT '17:00:00',
        disponible  BOOLEAN DEFAULT TRUE,
        UNIQUE KEY uq_tecnico_dia (tecnico_id, dia_semana),
        FOREIGN KEY (tecnico_id) REFERENCES usuarios(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Historial
    cur.execute("""CREATE TABLE IF NOT EXISTS historial (
        id              INT PRIMARY KEY AUTO_INCREMENT,
        reporte_id      INT NOT NULL,
        usuario_id      INT,
        accion          VARCHAR(100) NOT NULL,
        descripcion     TEXT,
        estado_anterior VARCHAR(50),
        estado_nuevo    VARCHAR(50),
        creado_en       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Notificaciones
    cur.execute("""CREATE TABLE IF NOT EXISTS notificaciones (
        id         INT PRIMARY KEY AUTO_INCREMENT,
        usuario_id INT NOT NULL,
        titulo     VARCHAR(200) NOT NULL,
        mensaje    TEXT NOT NULL,
        tipo       ENUM('info','exito','advertencia','error') DEFAULT 'info',
        leida      BOOLEAN DEFAULT FALSE,
        reporte_id INT,
        creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
        FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Evidencias
    cur.execute("""CREATE TABLE IF NOT EXISTS evidencias (
        id         INT PRIMARY KEY AUTO_INCREMENT,
        reporte_id INT NOT NULL,
        usuario_id INT NOT NULL,
        tipo       ENUM('imagen','video','documento') DEFAULT 'imagen',
        archivo    VARCHAR(255) NOT NULL,
        descripcion TEXT,
        subido_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (reporte_id) REFERENCES reportes(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # Migración: agregar imagen_hash si no existe
    try:
        cur.execute("ALTER TABLE reportes ADD COLUMN imagen_hash VARCHAR(16) NULL")
        conn.commit()
        print("[DB] Columna imagen_hash agregada")
    except Exception:
        pass

    # Migración: agregar dia_asignado si no existe
    try:
        cur.execute("""ALTER TABLE reportes
            ADD COLUMN dia_asignado TINYINT NULL COMMENT '0=Lun,1=Mar,2=Mie,3=Jue,4=Vie,5=Sab,6=Dom'""")
        conn.commit()
        print("[DB] Columna dia_asignado agregada")
    except Exception:
        pass  # Ya existe

    conn.commit(); cur.close(); conn.close()
    print("[DB] Tablas verificadas correctamente")

try:
    init_db()
except Exception as e:
    print(f"[DB ERROR] {e}")

# ─── HELPERS ─────────────────────────────────────────────────
def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)

def guardar_imagen(file, subcarpeta='reportes'):
    if not file or not allowed_file(file.filename):
        return None
    ext      = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    folder   = os.path.join(app.config['UPLOAD_FOLDER'], subcarpeta)
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, filename))
    return f"{subcarpeta}/{filename}"

def calcular_hash_perceptual(ruta):
    """Genera un hash perceptual (dHash 8x8 = 64 bits) de la imagen.
    Imágenes similares producen hashes con distancia Hamming baja."""
    try:
        from PIL import Image
        ruta_completa = os.path.join(os.path.dirname(__file__), 'app', 'uploads', ruta)
        if not os.path.exists(ruta_completa):
            return None
        img = Image.open(ruta_completa).convert('L').resize((9, 8), Image.LANCZOS)
        pixels = list(img.getdata())
        bits = []
        for row in range(8):
            for col in range(8):
                bits.append('1' if pixels[row*9+col] > pixels[row*9+col+1] else '0')
        hash_int = int(''.join(bits), 2)
        return format(hash_int, '016x')  # hex string de 16 chars
    except Exception:
        return None

def distancia_hamming(h1, h2):
    """Calcula distancia Hamming entre dos hashes hexadecimales."""
    try:
        n1, n2 = int(h1, 16), int(h2, 16)
        xor = n1 ^ n2
        return bin(xor).count('1')
    except Exception:
        return 64  # máxima diferencia si falla

def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia en km entre dos coordenadas."""
    try:
        R = 6371
        d_lat = math.radians(float(lat2) - float(lat1))
        d_lon = math.radians(float(lon2) - float(lon1))
        a = math.sin(d_lat/2)**2 + math.cos(math.radians(float(lat1))) * math.cos(math.radians(float(lat2))) * math.sin(d_lon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    except Exception:
        return 9999

def buscar_duplicados(conn, categoria_id, latitud, longitud, hash_imagen, radio_km=0.3, umbral_hash=12):
    """Busca reportes existentes similares por ubicación + categoría + imagen.
    Retorna lista de reportes candidatos con su score de similitud."""
    cur = conn.cursor()
    # Traer reportes activos (no rechazados, no duplicados) de la misma categoría
    cur.execute("""SELECT r.id, r.titulo, r.ciudad, r.direccion,
                          r.latitud, r.longitud, r.imagen_principal,
                          r.imagen_hash, r.estado, r.creado_en,
                          u.nombre as autor_nombre
                   FROM reportes r
                   LEFT JOIN usuarios u ON r.usuario_id = u.id
                   WHERE r.categoria_id = %s
                     AND r.estado NOT IN ('rechazado','duplicado','resuelto')
                   ORDER BY r.creado_en DESC
                   LIMIT 200""", (categoria_id,))
    candidatos_raw = cur.fetchall()
    cur.close()

    duplicados = []
    for r in candidatos_raw:
        score = 0
        razones = []

        # Criterio 1: Ubicación geográfica (≤ radio_km)
        geo_ok = False
        if latitud and longitud and r['latitud'] and r['longitud']:
            dist = haversine_km(latitud, longitud, r['latitud'], r['longitud'])
            if dist <= radio_km:
                geo_ok = True
                score += 50
                razones.append(f"📍 A {int(dist*1000)} m de distancia")
        
        # Criterio 2: Hash de imagen similar (distancia Hamming ≤ umbral)
        img_ok = False
        if hash_imagen and r.get('imagen_hash'):
            hamming = distancia_hamming(hash_imagen, r['imagen_hash'])
            if hamming <= umbral_hash:
                img_ok = True
                similitud = int((1 - hamming/64) * 100)
                score += 50
                razones.append(f"🖼️ Imagen {similitud}% similar")

        # Solo reportar si al menos 1 criterio coincide fuertemente
        if geo_ok or img_ok:
            duplicados.append({
                'id': r['id'],
                'titulo': r['titulo'],
                'ciudad': r['ciudad'],
                'direccion': r['direccion'] or '',
                'estado': r['estado'],
                'creado_en': r['creado_en'].strftime('%d/%m/%Y') if r['creado_en'] else '—',
                'autor': r['autor_nombre'] or 'Ciudadano',
                'imagen': r['imagen_principal'],
                'score': score,
                'razones': razones,
            })

    # Ordenar por score descendente
    duplicados.sort(key=lambda x: x['score'], reverse=True)
    return duplicados[:5]  # máximo 5 candidatos


def analizar_imagen_ia(ruta):
    """Analiza imagen con Claude Vision. Fallback si falla."""
    import base64
    try:
        import anthropic as _anthropic
        ruta_completa = os.path.join(os.path.dirname(__file__), 'app', 'uploads', ruta)
        if not os.path.exists(ruta_completa):
            ruta_completa = ruta
        with open(ruta_completa, 'rb') as f:
            img_b64 = base64.standard_b64encode(f.read()).decode('utf-8')
        ext        = ruta.rsplit('.', 1)[-1].lower()
        media_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                      'png': 'image/png',  'gif':  'image/gif'}.get(ext, 'image/jpeg')
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            raise ValueError('Sin API key')
        client = _anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=400,
            messages=[{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64',
                 'media_type': media_type, 'data': img_b64}},
                {'type': 'text', 'text':
                 'Analiza esta imagen. Responde SOLO con JSON sin texto extra ni bloques markdown:\n'
                 '{"tipo_detectado":"nombre corto","categoria_id_sugerida":1,"gravedad":50,'
                 '"confianza":0.85,"titulo_sugerido":"titulo breve maximo 8 palabras","descripcion_ia":"descripcion detallada y recomendacion"}\n'
                 'IMPORTANTE: Si la imagen NO muestra un problema urbano real (es una persona, animal, '
                 'objeto domestico, meme, selfie, comida, etc.), responde EXACTAMENTE:\n'
                 '{"tipo_detectado":"No es problema urbano","categoria_id_sugerida":8,"gravedad":0,'
                 '"confianza":0.99,"titulo_sugerido":"","descripcion_ia":"La imagen no corresponde a un problema urbano. Por favor sube una foto del dano real."}\n'
                 'Categorias validas (solo si ES un problema urbano): 1=Bache/Pavimento 2=Basura '
                 '3=Espacio Publico 4=Senalizacion Vial 5=Alumbrado 6=Arbol 7=Inundacion 8=Otro'}
            ]}]
        )
        texto = msg.content[0].text.strip()
        if texto.startswith('```'):
            texto = texto.split('```')[1]
            if texto.startswith('json'):
                texto = texto[4:]
        resultado = json.loads(texto)
        gravedad  = float(resultado.get('gravedad', 50))
        prioridad = ('critica' if gravedad >= 80 else
                     'alta'    if gravedad >= 60 else
                     'media'   if gravedad >= 40 else 'baja')
        return {
            'tipo_detectado':        resultado.get('tipo_detectado', 'Problema urbano'),
            'categoria_id_sugerida': int(resultado.get('categoria_id_sugerida', 8)),
            'gravedad':              gravedad,
            'prioridad':             prioridad,
            'confianza':             float(resultado.get('confianza', 0.85)),
            'descripcion_ia':        resultado.get('descripcion_ia', ''),
            'titulo_sugerido':       resultado.get('titulo_sugerido', ''),
            'modelo':                'Claude Vision',
        }
    except Exception as ex:
        print(f'[IA] Fallback por: {ex}')
        tipos = [
            {'label': 'Bache / Pavimento',  'id': 1},
            {'label': 'Basura / Residuos',  'id': 2},
            {'label': 'Señalización Vial',  'id': 4},
            {'label': 'Alumbrado Público',  'id': 5},
        ]
        t        = random.choice(tipos)
        gravedad = round(random.uniform(30, 90), 2)
        prioridad = ('critica' if gravedad >= 80 else
                     'alta'    if gravedad >= 60 else
                     'media'   if gravedad >= 40 else 'baja')
        return {
            'tipo_detectado':        t['label'],
            'categoria_id_sugerida': t['id'],
            'gravedad':              gravedad,
            'prioridad':             prioridad,
            'confianza':             round(random.uniform(0.75, 0.95), 2),
            'descripcion_ia':        f'Análisis automático (modo demo). {ex}',
            'modelo':                'Fallback demo',
        }

# ─── DECORADORES ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'usuario_id' not in session:
            flash('Debes iniciar sesión para continuar.', 'warning')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return dec

def rol_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a, **kw):
            if 'usuario_id' not in session:
                flash('Debes iniciar sesión.', 'warning')
                return redirect(url_for('login'))
            if session.get('rol') not in roles:
                flash('No tienes permisos para acceder a esta sección.', 'danger')
                return redirect(url_for('index'))
            return f(*a, **kw)
        return dec
    return decorator

# ─── FILTROS JINJA ───────────────────────────────────────────
@app.template_filter('fecha')
def filtro_fecha(value, fmt='%d/%m/%Y'):
    if value is None: return ''
    if hasattr(value, 'strftime'): return value.strftime(fmt)
    return str(value)[:10]

@app.template_filter('fecha_hora')
def filtro_fecha_hora(value):
    if value is None: return ''
    if hasattr(value, 'strftime'): return value.strftime('%d/%m/%Y %H:%M')
    return str(value)[:16]

app.jinja_env.globals['enumerate'] = enumerate

# ─── SERVIR UPLOADS ──────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Normaliza separadores para compatibilidad Windows/Linux
    filename = filename.replace('\\', '/')
    subfolder = os.path.dirname(filename)
    basename  = os.path.basename(filename)
    base_dir  = app.config['UPLOAD_FOLDER']
    if subfolder:
        base_dir = os.path.join(base_dir, subfolder)
    return send_from_directory(base_dir, basename)

# ─── LANDING ─────────────────────────────────────────────────
@app.route('/')
def index():
    if 'usuario_id' in session:
        rol = session.get('rol', '')
        if rol in ('administrador', 'super_admin'):
            return redirect(url_for('admin_dashboard'))
        if rol == 'tecnico':
            return redirect(url_for('tecnico_dashboard'))
        return redirect(url_for('ciudadano_dashboard'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) as total,
        SUM(estado='resuelto')    as resueltos,
        SUM(estado='pendiente')   as pendientes,
        SUM(estado='en_progreso') as en_progreso,
        SUM(estado='aprobado')    as aprobados
        FROM reportes""")
    stats = cur.fetchone() or {}
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre, c.color
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.publico=TRUE ORDER BY r.creado_en DESC LIMIT 6""")
    recientes = cur.fetchall()
    cur.execute("SELECT ciudad, COUNT(*) as total, SUM(estado='resuelto') as resueltos FROM reportes GROUP BY ciudad")
    por_ciudad = cur.fetchall()
    cur.close(); conn.close()
    return render_template('landing/index.html',
                           stats=stats, recientes=recientes, por_ciudad=por_ciudad)

# ─── QUICK ACCESS (solo 4 seeds, uno por rol) ────────────────
@app.route('/api/usuarios-acceso')
def api_usuarios_acceso():
    """Panel de acceso rápido — muestra todos los usuarios agrupados por rol."""
    # Contraseñas de demo — SOLO emails yopmail.com predefinidos
    DEMO_PASSWORDS = {
        'superadmin@yopmail.com':  'superadmin2026',
        'admin@yopmail.com':       'admin2026',
        'tecnico1@yopmail.com':    'tecnico2026',
        'tecnico2@yopmail.com':    'tecnico2026',
        'tecnico3@yopmail.com':    'tecnico2026',
        'tecnico4@yopmail.com':    'tecnico2026',
        'tecnico5@yopmail.com':    'tecnico2026',
        'ciudadano1@yopmail.com':  'ciudad2026',
        'ciudadano2@yopmail.com':  'ciudad2026',
        'ciudadano3@yopmail.com':  'ciudad2026',
        'ciudadano4@yopmail.com':  'ciudad2026',
        'ciudadano5@yopmail.com':  'ciudad2026',
    }
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("""
            SELECT u.nombre, u.apellido, u.email, r.nombre AS rol
            FROM usuarios u JOIN roles r ON u.rol_id = r.id
            WHERE u.activo = TRUE
              AND r.nombre IN ('super_admin','administrador','tecnico','ciudadano')
            ORDER BY FIELD(r.nombre,'super_admin','administrador','tecnico','ciudadano'), u.id
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        return jsonify([{
            'nombre':   r['nombre'],
            'apellido': r['apellido'] or '',
            'email':    r['email'],
            'rol':      r['rol'],
            'pw':       DEMO_PASSWORDS.get(r['email'], ''),  # vacío si no es usuario demo
        } for r in rows])
    except Exception:
        return jsonify([])

# ─── AUTH ─────────────────────────────────────────────────────
@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        conn = get_db(); cur = conn.cursor()
        cur.execute("""SELECT u.*, r.nombre as rol_nombre
            FROM usuarios u JOIN roles r ON u.rol_id=r.id
            WHERE u.email=%s AND u.activo=TRUE""", (email,))
        u = cur.fetchone()
        pw_ok = False
        if u and u.get('password_hash'):
            try:
                pw_ok = check_password_hash(u['password_hash'], password)
            except Exception:
                pw_ok = False
        if u and pw_ok:
            cur.execute("UPDATE usuarios SET ultimo_login=%s WHERE id=%s",
                        (now_col(), u['id']))
            conn.commit()
            session['usuario_id'] = u['id']
            session['nombre']     = f"{u['nombre']} {u['apellido'] or ''}".strip()
            session['email']      = u['email']
            session['rol']        = u['rol_nombre']
            cur.close(); conn.close()
            flash(f"Bienvenido, {u['nombre']}!", 'success')
            rol = u['rol_nombre']
            if rol in ('administrador', 'super_admin'):
                return redirect(url_for('admin_dashboard'))
            if rol == 'tecnico':
                return redirect(url_for('tecnico_dashboard'))
            return redirect(url_for('ciudadano_dashboard'))
        cur.close(); conn.close()
        flash('Correo o contraseña incorrectos.', 'danger')
    return render_template('auth/login.html')

@app.route('/auth/registro', methods=['GET', 'POST'])
def registro():
    if 'usuario_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        nombre   = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        ciudad   = request.form.get('ciudad', 'Facatativá')
        if not all([nombre, email, password]):
            flash('Todos los campos son requeridos.', 'danger')
            return render_template('auth/registro.html')
        if len(password) < 6:
            flash('La contraseña debe tener mínimo 6 caracteres.', 'danger')
            return render_template('auth/registro.html')
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE email=%s", (email,))
        if cur.fetchone():
            flash('Ya existe una cuenta con ese correo.', 'warning')
            cur.close(); conn.close()
            return render_template('auth/registro.html')
        cur.execute("""INSERT INTO usuarios (nombre,apellido,email,password_hash,ciudad,rol_id)
            VALUES (%s,%s,%s,%s,%s,(SELECT id FROM roles WHERE nombre='ciudadano'))""",
            (nombre, apellido, email, generate_password_hash(password), ciudad))
        conn.commit()
        uid = cur.lastrowid
        cur.close(); conn.close()
        session['usuario_id'] = uid
        session['nombre']     = f"{nombre} {apellido}".strip()
        session['email']      = email
        session['rol']        = 'ciudadano'
        flash(f'Cuenta creada. ¡Bienvenido a Urban Alert, {nombre}!', 'success')
        return redirect(url_for('ciudadano_dashboard'))
    return render_template('auth/registro.html')

@app.route('/auth/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ─── CIUDADANO ───────────────────────────────────────────────
@app.route('/ciudadano/dashboard')
@login_required
def ciudadano_dashboard():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.usuario_id=%s ORDER BY r.creado_en DESC LIMIT 5""", (uid,))
    mis_reportes = cur.fetchall()
    cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s", (uid,))
    total = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s AND estado='resuelto'", (uid,))
    resueltos = cur.fetchone()['c']
    cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s AND estado='pendiente'", (uid,))
    pendientes = cur.fetchone()['c']
    cur.close(); conn.close()
    return render_template('ciudadano/dashboard.html',
                           mis_reportes=mis_reportes,
                           total=total, resueltos=resueltos, pendientes=pendientes)

@app.route('/reportes/<int:reporte_id>/eliminar', methods=['POST'])
@login_required
def eliminar_reporte(reporte_id):
    """Permite al ciudadano eliminar su propio reporte (solo si está pendiente o rechazado)."""
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM reportes WHERE id=%s AND usuario_id=%s", (reporte_id, session['usuario_id']))
    reporte = cur.fetchone()
    if not reporte:
        flash('Reporte no encontrado o no tienes permiso para eliminarlo.', 'danger')
        cur.close(); conn.close()
        return redirect(url_for('mis_reportes'))
    if reporte['estado'] not in ('pendiente', 'rechazado'):
        flash('Solo puedes eliminar reportes en estado Pendiente o Rechazado.', 'warning')
        cur.close(); conn.close()
        return redirect(url_for('mis_reportes'))
    cur.execute("DELETE FROM reportes WHERE id=%s", (reporte_id,))
    conn.commit(); cur.close(); conn.close()
    flash('Reporte eliminado correctamente.', 'success')
    return redirect(url_for('mis_reportes'))

@app.route('/ciudadano/mis-reportes')
@login_required
def mis_reportes():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre, c.color
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.usuario_id=%s ORDER BY r.creado_en DESC""", (uid,))
    reportes = cur.fetchall()
    cur.close(); conn.close()
    return render_template('ciudadano/mis_reportes.html', reportes=reportes)

# ─── REPORTES ────────────────────────────────────────────────
@app.route('/reportes/mapa')
def mapa():
    ciudad = request.args.get('ciudad')
    conn = get_db(); cur = conn.cursor()
    sql = """SELECT r.*, c.nombre as categoria_nombre, c.color as categoria_color
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.publico=TRUE"""
    if ciudad:
        cur.execute(sql + " AND r.ciudad=%s ORDER BY r.creado_en DESC", (ciudad,))
    else:
        cur.execute(sql + " ORDER BY r.creado_en DESC")
    reportes = cur.fetchall()
    cur.close(); conn.close()
    reportes = [
        {**r,
         'latitud':  float(r['latitud'])  if r.get('latitud')  is not None else None,
         'longitud': float(r['longitud']) if r.get('longitud') is not None else None}
        for r in reportes
    ]
    if session.get('usuario_id'):
        return render_template('ciudadano/mapa.html', reportes=reportes)
    return render_template('landing/mapa_publico.html', reportes=reportes)

@app.route('/api/verificar-duplicado', methods=['POST'])
@login_required
def api_verificar_duplicado():
    """Verifica si una imagen/ubicación corresponde a un reporte ya existente."""
    data = request.get_json() or {}
    categoria_id = data.get('categoria_id')
    latitud      = data.get('latitud')
    longitud     = data.get('longitud')
    hash_img     = data.get('hash_imagen')  # hash calculado en cliente o enviado

    if not categoria_id:
        return jsonify({'duplicados': []})

    conn = get_db()
    duplicados = buscar_duplicados(conn, categoria_id, latitud, longitud, hash_img)
    conn.close()
    return jsonify({'duplicados': duplicados})


@app.route('/reportes/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_reporte():
    conn = get_db(); cur = conn.cursor()
    if request.method == 'POST':
        imagen   = request.files.get('imagen')
        ruta     = guardar_imagen(imagen) if imagen and imagen.filename else None
        analisis = analizar_imagen_ia(ruta) if ruta else {}

        # Bloquear si la IA detecta que NO es un problema urbano
        if ruta and analisis.get('gravedad', 50) == 0:
            try:
                ruta_completa = os.path.join(app.config['UPLOAD_FOLDER'], ruta)
                if os.path.exists(ruta_completa): os.remove(ruta_completa)
            except Exception: pass
            flash('⚠️ La imagen no corresponde a un problema urbano. Por favor sube una foto del daño real.', 'danger')
            cur.execute("SELECT * FROM categorias WHERE activa=TRUE ORDER BY nombre")
            cats = cur.fetchall(); cur.close(); conn.close()
            return render_template('ciudadano/nuevo_reporte.html', categorias=cats)

        titulo      = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        cat_id      = request.form.get('categoria_id')
        ciudad      = request.form.get('ciudad', 'Facatativá')
        direccion   = request.form.get('direccion', '').strip()
        latitud     = request.form.get('latitud') or None
        longitud    = request.form.get('longitud') or None
        if not all([titulo, descripcion, cat_id, ciudad]):
            flash('Completa todos los campos obligatorios.', 'danger')
            cur.execute("SELECT * FROM categorias WHERE activa=TRUE ORDER BY nombre")
            cats = cur.fetchall(); cur.close(); conn.close()
            return render_template('ciudadano/nuevo_reporte.html', categorias=cats)

        # Calcular hash perceptual y verificar duplicados antes de guardar
        hash_img  = calcular_hash_perceptual(ruta) if ruta else None
        ignorar   = request.form.get('ignorar_duplicado') == '1'
        if not ignorar and (latitud or hash_img):
            duplicados = buscar_duplicados(conn, cat_id, latitud, longitud, hash_img)
            if duplicados:
                cur.execute("SELECT * FROM categorias WHERE activa=TRUE ORDER BY nombre")
                cats = cur.fetchall(); cur.close(); conn.close()
                return render_template('ciudadano/nuevo_reporte.html',
                                       categorias=cats,
                                       duplicados_encontrados=duplicados,
                                       form_data=request.form,
                                       ruta_imagen_temp=ruta,
                                       hash_imagen=hash_img)

        prioridad = analisis.get('prioridad', 'media')
        cur.execute("""INSERT INTO reportes
            (titulo,descripcion,categoria_id,ciudad,direccion,latitud,longitud,
             usuario_id,imagen_principal,gravedad_ia,analisis_ia,prioridad,imagen_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (titulo, descripcion, cat_id, ciudad, direccion, latitud, longitud,
             session['usuario_id'], ruta,
             analisis.get('gravedad'), json.dumps(analisis) if analisis else None,
             prioridad, hash_img))
        nuevo_reporte_id = cur.lastrowid
        # Notificar a todos los administradores y super_admins
        cur.execute("""SELECT u.id FROM usuarios u
            JOIN roles r ON u.rol_id=r.id
            WHERE r.nombre IN ('administrador','super_admin') AND u.activo=TRUE""")
        admins = cur.fetchall()
        ciudadano_nombre = session.get('nombre', 'Un ciudadano')
        for admin in admins:
            cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
                VALUES (%s, %s, %s, 'info', %s)""",
                (admin['id'],
                 'Nuevo reporte recibido',
                 f'{ciudadano_nombre} reportó: "{titulo}" en {ciudad}.',
                 nuevo_reporte_id))
        conn.commit(); cur.close(); conn.close()
        flash('¡Reporte enviado exitosamente! Lo revisaremos pronto.', 'success')
        return redirect(url_for('mis_reportes'))
    cur.execute("SELECT * FROM categorias WHERE activa=TRUE ORDER BY nombre")
    cats = cur.fetchall(); cur.close(); conn.close()
    return render_template('ciudadano/nuevo_reporte.html', categorias=cats)

@app.route('/reportes/<int:reporte_id>')
def detalle_reporte(reporte_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre, c.icono as categoria_icono,
        u.nombre as usuario_nombre, u.apellido as usuario_apellido,
        t.nombre as tecnico_nombre, t.apellido as tecnico_apellido
        FROM reportes r
        LEFT JOIN categorias c ON r.categoria_id=c.id
        LEFT JOIN usuarios u   ON r.usuario_id=u.id
        LEFT JOIN usuarios t   ON r.tecnico_id=t.id
        WHERE r.id=%s""", (reporte_id,))
    reporte = cur.fetchone()
    if reporte:
        cur.execute("UPDATE reportes SET vistas=vistas+1 WHERE id=%s", (reporte_id,))
        conn.commit()
    cur.close(); conn.close()
    if not reporte:
        flash('Reporte no encontrado.', 'danger')
        return redirect(url_for('index'))
    if session.get('usuario_id'):
        return render_template('ciudadano/detalle_reporte.html', reporte=reporte)
    return render_template('landing/detalle_publico.html', reporte=reporte)

# ─── TÉCNICO ─────────────────────────────────────────────────
@app.route('/tecnico/dashboard')
@rol_required('tecnico')
def tecnico_dashboard():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.tecnico_id=%s ORDER BY r.prioridad DESC, r.creado_en DESC""", (uid,))
    trabajos  = cur.fetchall()
    activos   = [r for r in trabajos if r['estado'] in ('asignado', 'en_progreso')]
    resueltos = [r for r in trabajos if r['estado'] == 'resuelto']
    cur.execute("SELECT COUNT(*) as c FROM notificaciones WHERE usuario_id=%s AND leida=FALSE", (uid,))
    no_leidas = (cur.fetchone() or {}).get('c', 0)
    # Horario del técnico para mostrarlo en el dashboard
    cur.execute("SELECT * FROM horario_tecnico WHERE tecnico_id=%s ORDER BY dia_semana", (uid,))
    horario_rows = {r['dia_semana']: r for r in cur.fetchall()}
    # Trabajos agrupados por dia_asignado (para mostrar en el horario)
    trabajos_por_dia = {}
    for t in trabajos:
        d = t.get('dia_asignado')
        if d is not None:
            trabajos_por_dia.setdefault(int(d), []).append(t)
    cur.close(); conn.close()
    dias_es = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    return render_template('tecnico/dashboard.html',
                           trabajos=trabajos, activos=activos, resueltos=resueltos,
                           no_leidas=no_leidas, horario_rows=horario_rows,
                           trabajos_por_dia=trabajos_por_dia, dias_es=dias_es)

@app.route('/tecnico/reporte/<int:reporte_id>/resolver', methods=['POST'])
@rol_required('tecnico')
def tecnico_resolver(reporte_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""UPDATE reportes SET estado='resuelto', fecha_resolucion=NOW()
        WHERE id=%s AND tecnico_id=%s""", (reporte_id, session['usuario_id']))
    # Notificar al ciudadano
    cur.execute("SELECT titulo, usuario_id FROM reportes WHERE id=%s", (reporte_id,))
    rep = cur.fetchone()
    if rep and rep['usuario_id']:
        cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
            VALUES (%s, %s, %s, 'exito', %s)""",
            (rep['usuario_id'],
             '¡Tu reporte fue resuelto!',
             f'El reporte "{rep["titulo"]}" ha sido resuelto satisfactoriamente. ¡Gracias por reportarlo!',
             reporte_id))
    conn.commit(); cur.close(); conn.close()
    flash('Reporte marcado como resuelto.', 'success')
    return redirect(url_for('tecnico_dashboard'))

@app.route('/tecnico/reporte/<int:reporte_id>/progreso', methods=['POST'])
@rol_required('tecnico')
def tecnico_en_progreso(reporte_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE reportes SET estado='en_progreso' WHERE id=%s AND tecnico_id=%s",
                (reporte_id, session['usuario_id']))
    # Notificar al ciudadano
    cur.execute("SELECT titulo, usuario_id FROM reportes WHERE id=%s", (reporte_id,))
    rep = cur.fetchone()
    if rep and rep['usuario_id']:
        cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
            VALUES (%s, %s, %s, 'info', %s)""",
            (rep['usuario_id'],
             'Tu reporte está en progreso',
             f'El técnico ha comenzado a trabajar en tu reporte "{rep["titulo"]}". Pronto estará resuelto.',
             reporte_id))
    conn.commit(); cur.close(); conn.close()
    flash('Reporte marcado como en progreso.', 'success')
    return redirect(url_for('tecnico_dashboard'))

@app.route('/tecnico/mapa')
@rol_required('tecnico')
def tecnico_mapa():
    ciudad = request.args.get('ciudad')
    conn = get_db(); cur = conn.cursor()
    q = "SELECT id,titulo,ciudad,estado,latitud,longitud FROM reportes WHERE latitud IS NOT NULL AND longitud IS NOT NULL"
    params = []
    if ciudad:
        q += " AND ciudad=%s"; params.append(ciudad)
    cur.execute(q, params)
    rows = cur.fetchall(); cur.close(); conn.close()
    reportes = [
        {**r,
         'latitud':  float(r['latitud'])  if r['latitud']  is not None else None,
         'longitud': float(r['longitud']) if r['longitud'] is not None else None}
        for r in rows
    ]
    return render_template('tecnico/mapa.html', reportes=reportes)


@app.route('/tecnico/mis-trabajos')
@rol_required('tecnico')
def tecnico_mis_trabajos():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.tecnico_id=%s ORDER BY r.creado_en DESC""", (uid,))
    trabajos = cur.fetchall()
    cur.close(); conn.close()
    return render_template('tecnico/mis_trabajos.html', trabajos=trabajos)

# ─── ADMIN ───────────────────────────────────────────────────
@app.route('/admin/dashboard')
@rol_required('administrador', 'super_admin')
def admin_dashboard():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) as total,
        SUM(estado='resuelto')    as resueltos,
        SUM(estado='pendiente')   as pendientes,
        SUM(estado='en_progreso') as en_progreso,
        SUM(estado='aprobado')    as aprobados
        FROM reportes""")
    stats = cur.fetchone() or {}
    cur.execute("""SELECT r.*, c.nombre as categoria_nombre, c.color
        FROM reportes r LEFT JOIN categorias c ON r.categoria_id=c.id
        WHERE r.publico=TRUE ORDER BY r.creado_en DESC LIMIT 8""")
    recientes = cur.fetchall()
    cur.execute("SELECT ciudad, COUNT(*) as total, SUM(estado='resuelto') as resueltos FROM reportes GROUP BY ciudad")
    por_ciudad = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE activo=TRUE")
    total_usuarios = (cur.fetchone() or {}).get('total', 0)
    cur.close(); conn.close()
    return render_template('admin/dashboard.html',
                           stats=stats, recientes=recientes,
                           por_ciudad=por_ciudad, total_usuarios=total_usuarios)

@app.route('/admin/reportes')
@rol_required('administrador', 'super_admin')
def admin_reportes():
    estado    = request.args.get('estado', '')
    ciudad    = request.args.get('ciudad', '')
    pagina    = int(request.args.get('pagina', 1))
    por_pagina = 15
    offset    = (pagina - 1) * por_pagina
    conn = get_db(); cur = conn.cursor()
    conds = ['r.publico=TRUE']; params = []
    if estado: conds.append('r.estado=%s');  params.append(estado)
    if ciudad: conds.append('r.ciudad=%s');  params.append(ciudad)
    where = ' AND '.join(conds)
    cur.execute(f"""SELECT r.*, c.nombre as categoria_nombre, c.color,
        u.nombre as usuario_nombre, u.apellido as usuario_apellido,
        t.nombre as tecnico_nombre, t.apellido as tecnico_apellido
        FROM reportes r
        LEFT JOIN categorias c ON r.categoria_id=c.id
        LEFT JOIN usuarios u   ON r.usuario_id=u.id
        LEFT JOIN usuarios t   ON r.tecnico_id=t.id
        WHERE {where} ORDER BY r.creado_en DESC
        LIMIT %s OFFSET %s""", (*params, por_pagina, offset))
    reportes = cur.fetchall()
    cur.execute("""SELECT u.*, t.disponible as tec_disponible, t.especialidad,
        (SELECT GROUP_CONCAT(
            CONCAT(dia_semana,':',disponible,':',
                (SELECT COUNT(*) FROM reportes r2
                 WHERE r2.tecnico_id=u.id
                   AND r2.estado IN ('asignado','en_progreso')
                   AND r2.dia_asignado=ht.dia_semana))
            ORDER BY ht.dia_semana SEPARATOR '|')
         FROM horario_tecnico ht WHERE ht.tecnico_id=u.id AND ht.disponible=1) as horario_raw,
        (SELECT COUNT(*) FROM reportes
         WHERE tecnico_id=u.id AND estado IN ('asignado','en_progreso')) as trabajos_activos
        FROM usuarios u
        LEFT JOIN tecnicos t ON t.usuario_id=u.id
        WHERE u.rol_id=(SELECT id FROM roles WHERE nombre='tecnico') AND u.activo=TRUE""")
    tecnicos = cur.fetchall()
    cur.close(); conn.close()
    return render_template('admin/reportes.html',
                           reportes=reportes, tecnicos=tecnicos,
                           ciudad=ciudad, estado=estado)

@app.route('/admin/reportes/<int:reporte_id>/estado', methods=['POST'])
@rol_required('administrador', 'super_admin')
def admin_cambiar_estado(reporte_id):
    # Soporta tanto form-data como JSON
    if request.is_json:
        data         = request.get_json()
        nuevo_estado = data.get('estado')
        tecnico_id   = data.get('tecnico_id') or None
        dia_asignado = data.get('dia_asignado')  # 0-6, None si no se seleccionó
    else:
        nuevo_estado = request.form.get('estado')
        tecnico_id   = request.form.get('tecnico_id') or None
        dia_asignado = request.form.get('dia_asignado')
    # Convertir dia_asignado a int si viene
    if dia_asignado is not None and dia_asignado != '':
        try: dia_asignado = int(dia_asignado)
        except: dia_asignado = None
    else:
        dia_asignado = None

    # Si hay técnico asignado pero el estado llegó vacío, asumir 'asignado'
    if tecnico_id and not nuevo_estado:
        nuevo_estado = 'asignado'

    # El admin solo puede mover hasta 'asignado'; en_progreso y resuelto son del técnico
    ESTADOS_ADMIN = ('pendiente', 'aprobado', 'asignado', 'rechazado')
    if nuevo_estado not in ESTADOS_ADMIN:
        if request.is_json:
            return jsonify({'ok': False, 'error': 'Estado no permitido'}), 400
        flash('No tienes permiso para establecer ese estado.', 'danger')
        return redirect(url_for('admin_reportes'))

    conn = get_db(); cur = conn.cursor()
    if tecnico_id:
        # Validar límite de 2 trabajos por día (si se seleccionó día)
        if dia_asignado is not None:
            cur.execute("""SELECT COUNT(*) as c FROM reportes
                WHERE tecnico_id=%s AND estado IN ('asignado','en_progreso')
                AND dia_asignado=%s AND id != %s""", (tecnico_id, dia_asignado, reporte_id))
            trabajos_dia = (cur.fetchone() or {}).get('c', 0)
            if trabajos_dia >= 2:
                DIAS_ES = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
                nombre_dia = DIAS_ES[dia_asignado] if 0 <= dia_asignado <= 6 else 'ese día'
                cur.close(); conn.close()
                if request.is_json:
                    return jsonify({'ok': False, 'error': f'Este técnico ya tiene 2 trabajos asignados el {nombre_dia}. Escoge otro día u otro técnico.'}), 400
                flash(f'El técnico ya tiene 2 trabajos el {nombre_dia}.', 'danger')
                return redirect(url_for('admin_reportes'))
        else:
            # Sin día seleccionado: verificar límite global de 2
            cur.execute("""SELECT COUNT(*) as c FROM reportes
                WHERE tecnico_id=%s AND estado IN ('asignado','en_progreso')
                AND id != %s""", (tecnico_id, reporte_id))
            trabajos_activos = (cur.fetchone() or {}).get('c', 0)
            if trabajos_activos >= 2:
                cur.close(); conn.close()
                if request.is_json:
                    return jsonify({'ok': False, 'error': f'Este técnico ya tiene {trabajos_activos} trabajos activos (máximo 2). Selecciona otro técnico o un día específico.'}), 400
                flash('Este técnico ya tiene el máximo de trabajos activos (2).', 'danger')
                return redirect(url_for('admin_reportes'))

        cur.execute("""UPDATE reportes SET estado=%s, tecnico_id=%s,
            admin_id=%s, fecha_asignacion=NOW(), dia_asignado=%s WHERE id=%s""",
            (nuevo_estado, tecnico_id, session['usuario_id'], dia_asignado, reporte_id))
        cur.execute("SELECT titulo, ciudad, usuario_id FROM reportes WHERE id=%s", (reporte_id,))
        rep = cur.fetchone()
        titulo_rep   = rep['titulo']    if rep else f'Reporte #{reporte_id}'
        ciudad_rep   = rep['ciudad']    if rep else ''
        ciudadano_id = rep['usuario_id'] if rep else None
        cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
            VALUES (%s, %s, %s, 'exito', %s)""",
            (tecnico_id,
             'Nuevo trabajo asignado',
             f'Se te asignó el reporte "{titulo_rep}" en {ciudad_rep}.',
             reporte_id))
        if ciudadano_id:
            cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
                VALUES (%s, %s, %s, 'info', %s)""",
                (ciudadano_id,
                 'Tu reporte fue asignado',
                 f'Tu reporte "{titulo_rep}" fue asignado a un técnico y está en proceso.',
                 reporte_id))
    else:
        cur.execute("UPDATE reportes SET estado=%s, admin_id=%s WHERE id=%s",
                    (nuevo_estado, session['usuario_id'], reporte_id))
        if nuevo_estado in ('aprobado', 'rechazado'):
            cur.execute("SELECT titulo, usuario_id FROM reportes WHERE id=%s", (reporte_id,))
            rep = cur.fetchone()
            if rep and rep['usuario_id']:
                if nuevo_estado == 'aprobado':
                    msg_t = 'Tu reporte fue aprobado'
                    msg_b = f'Tu reporte "{rep["titulo"]}" fue revisado y aprobado.'
                    tipo  = 'exito'
                else:
                    msg_t = 'Tu reporte fue rechazado'
                    msg_b = f'Tu reporte "{rep["titulo"]}" fue rechazado por el administrador.'
                    tipo  = 'error'
                cur.execute("""INSERT INTO notificaciones (usuario_id, titulo, mensaje, tipo, reporte_id)
                    VALUES (%s, %s, %s, %s, %s)""",
                    (rep['usuario_id'], msg_t, msg_b, tipo, reporte_id))
    conn.commit(); cur.close(); conn.close()

    if request.is_json:
        return jsonify({'ok': True, 'estado': nuevo_estado})
    flash(f'Estado actualizado a "{nuevo_estado}".', 'success')
    return redirect(url_for('admin_reportes'))


# ─── HORARIO TÉCNICO ────────────────────────────────────────
@app.route('/tecnico/horario', methods=['GET', 'POST'])
@rol_required('tecnico')
def tecnico_horario():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    dias = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    if request.method == 'POST':
        for i in range(7):
            disponible = 1 if request.form.get(f'disp_{i}') else 0
            cur.execute("""INSERT INTO horario_tecnico (tecnico_id, dia_semana, hora_inicio, hora_fin, disponible)
                VALUES (%s,%s,'07:00','17:00',%s)
                ON DUPLICATE KEY UPDATE disponible=%s""",
                (uid, i, disponible, disponible))
        conn.commit()
        flash('Horario actualizado correctamente.', 'success')
    cur.execute("SELECT * FROM horario_tecnico WHERE tecnico_id=%s ORDER BY dia_semana", (uid,))
    rows = {r['dia_semana']: r for r in cur.fetchall()}
    cur.close(); conn.close()
    return render_template('tecnico/horario.html', dias=dias, rows=rows)


# ─── NOTIFICACIONES TÉCNICO (API JSON) ──────────────────────
@app.route('/tecnico/notificaciones')
@rol_required('tecnico')
def tecnico_notificaciones():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT * FROM notificaciones WHERE usuario_id=%s
        ORDER BY creado_en DESC LIMIT 30""", (uid,))
    notifs = cur.fetchall()
    cur.execute("SELECT COUNT(*) as c FROM notificaciones WHERE usuario_id=%s AND leida=FALSE", (uid,))
    no_leidas = (cur.fetchone() or {}).get('c', 0)
    cur.close(); conn.close()
    return jsonify({'notificaciones': [dict(n) for n in notifs], 'no_leidas': no_leidas})


@app.route('/tecnico/notificaciones/leer', methods=['POST'])
@rol_required('tecnico')
def tecnico_marcar_leidas():
    uid = session['usuario_id']
    nid = request.json.get('id') if request.is_json else None
    conn = get_db(); cur = conn.cursor()
    if nid:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE id=%s AND usuario_id=%s", (nid, uid))
    else:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE usuario_id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True})


@app.route('/tecnico/disponibilidad', methods=['POST'])
@rol_required('tecnico')
def tecnico_toggle_disponibilidad():
    uid = session['usuario_id']
    data = request.get_json(silent=True) or {}
    disponible = bool(data.get('disponible', True))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE tecnicos SET disponible=%s WHERE usuario_id=%s", (disponible, uid))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True, 'disponible': disponible})


# ─── HORARIO TÉCNICO (vista admin) ──────────────────────────
@app.route('/admin/tecnico/<int:tecnico_id>/horario')
@rol_required('administrador', 'super_admin')
def admin_ver_horario_tecnico(tecnico_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT nombre, apellido FROM usuarios WHERE id=%s", (tecnico_id,))
    tec = cur.fetchone()
    if not tec:
        flash('Técnico no encontrado.', 'danger')
        return redirect(url_for('admin_usuarios', tab='tecnicos'))
    dias = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']
    cur.execute("SELECT * FROM horario_tecnico WHERE tecnico_id=%s ORDER BY dia_semana", (tecnico_id,))
    rows = {r['dia_semana']: r for r in cur.fetchall()}
    cur.close(); conn.close()
    return render_template('admin/horario_tecnico.html',
                           tecnico=tec, tecnico_id=tecnico_id, dias=dias, rows=rows)


# ─── API: REPORTES NUEVOS PENDIENTES (polling dashboard admin) ──
@app.route('/admin/api/reportes-pendientes')
@rol_required('administrador', 'super_admin')
def admin_api_reportes_pendientes():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) as c FROM reportes WHERE estado='pendiente'""")
    pendientes = (cur.fetchone() or {}).get('c', 0)
    cur.execute("""SELECT id, titulo, ciudad, creado_en FROM reportes
        WHERE estado='pendiente' ORDER BY creado_en DESC LIMIT 5""")
    ultimos = cur.fetchall()
    cur.close(); conn.close()
    return jsonify({
        'pendientes': pendientes,
        'ultimos': [{'id': r['id'], 'titulo': r['titulo'], 'ciudad': r['ciudad']} for r in ultimos]
    })


# ─── NOTIFICACIONES CIUDADANO (API JSON) ───────────────────
@app.route('/ciudadano/notificaciones')
@rol_required('ciudadano')
def ciudadano_notificaciones():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT * FROM notificaciones WHERE usuario_id=%s
        ORDER BY creado_en DESC LIMIT 30""", (uid,))
    notifs = cur.fetchall()
    cur.execute("SELECT COUNT(*) as c FROM notificaciones WHERE usuario_id=%s AND leida=FALSE", (uid,))
    no_leidas = (cur.fetchone() or {}).get('c', 0)
    cur.close(); conn.close()
    return jsonify({'notificaciones': [dict(n) for n in notifs], 'no_leidas': no_leidas})


@app.route('/ciudadano/notificaciones/leer', methods=['POST'])
@rol_required('ciudadano')
def ciudadano_marcar_leidas():
    uid = session['usuario_id']
    nid = request.json.get('id') if request.is_json else None
    conn = get_db(); cur = conn.cursor()
    if nid:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE id=%s AND usuario_id=%s", (nid, uid))
    else:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE usuario_id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True})


# ─── NOTIFICACIONES ADMIN (API JSON) ────────────────────────
@app.route('/admin/notificaciones')
@rol_required('administrador', 'super_admin')
def admin_notificaciones():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT * FROM notificaciones WHERE usuario_id=%s ORDER BY creado_en DESC LIMIT 30""", (uid,))
    notifs = cur.fetchall()
    cur.execute("SELECT COUNT(*) as c FROM notificaciones WHERE usuario_id=%s AND leida=FALSE", (uid,))
    no_leidas = (cur.fetchone() or {}).get('c', 0)
    cur.close(); conn.close()
    return jsonify({'notificaciones': [dict(n) for n in notifs], 'no_leidas': no_leidas})

@app.route('/admin/notificaciones/leer', methods=['POST'])
@rol_required('administrador', 'super_admin')
def admin_marcar_leidas():
    uid = session['usuario_id']
    nid = request.json.get('id') if request.is_json else None
    conn = get_db(); cur = conn.cursor()
    if nid:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE id=%s AND usuario_id=%s", (nid, uid))
    else:
        cur.execute("UPDATE notificaciones SET leida=TRUE WHERE usuario_id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'ok': True})


@app.route('/admin/usuarios')
@rol_required('administrador', 'super_admin')
def admin_usuarios():
    tab = request.args.get('tab', 'todos')
    pagina = int(request.args.get('pagina', 1))
    por_pagina = 20; offset = (pagina - 1) * por_pagina
    conn = get_db(); cur = conn.cursor()
    cond = ""
    if tab == 'tecnicos':   cond = " AND r.nombre='tecnico'"
    elif tab == 'ciudadanos': cond = " AND r.nombre='ciudadano'"
    cur.execute(f"""SELECT u.id,u.nombre,u.apellido,u.email,u.ciudad,
        u.activo,u.creado_en, r.nombre as rol, r.id as rol_id
        FROM usuarios u JOIN roles r ON u.rol_id=r.id
        WHERE 1=1{cond}
        ORDER BY u.creado_en DESC LIMIT %s OFFSET %s""", (por_pagina, offset))
    usuarios = cur.fetchall()
    cur.execute("SELECT id, nombre FROM roles ORDER BY id")
    roles = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM usuarios u JOIN roles r ON u.rol_id=r.id WHERE 1=1")
    total_todos = (cur.fetchone() or {}).get('total', 0)
    cur.execute("SELECT COUNT(*) as total FROM usuarios u JOIN roles r ON u.rol_id=r.id WHERE r.nombre='tecnico'")
    total_tecnicos = (cur.fetchone() or {}).get('total', 0)
    cur.execute("SELECT COUNT(*) as total FROM usuarios u JOIN roles r ON u.rol_id=r.id WHERE r.nombre='ciudadano'")
    total_ciudadanos = (cur.fetchone() or {}).get('total', 0)
    cur.close(); conn.close()
    return render_template('admin/usuarios.html', usuarios=usuarios, roles=roles,
                           tab=tab, total_todos=total_todos,
                           total_tecnicos=total_tecnicos, total_ciudadanos=total_ciudadanos)

@app.route('/admin/usuarios/<int:uid>/cambiar-rol', methods=['POST'])
@rol_required('administrador', 'super_admin')
def admin_cambiar_rol(uid):
    rol_id = request.form.get('rol_id')
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE usuarios SET rol_id=%s WHERE id=%s", (rol_id, uid))
    conn.commit(); cur.close(); conn.close()
    flash('Rol actualizado correctamente.', 'success')
    return redirect(url_for('admin_usuarios', tab=request.form.get('tab', 'todos')))

@app.route('/admin/usuarios/<int:uid>/eliminar', methods=['POST'])
@rol_required('administrador', 'super_admin')
def admin_eliminar_usuario(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE id=%s", (uid,))
    conn.commit(); cur.close(); conn.close()
    flash('Usuario eliminado.', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/usuarios/<int:uid>/toggle', methods=['POST'])
@rol_required('administrador', 'super_admin')
def admin_toggle_usuario(uid):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT activo FROM usuarios WHERE id=%s", (uid,))
    u = cur.fetchone()
    cur.execute("UPDATE usuarios SET activo=%s WHERE id=%s",
                (not u['activo'] if u else True, uid))
    conn.commit(); cur.close(); conn.close()
    flash('Usuario actualizado.', 'success')
    return redirect(url_for('admin_usuarios'))

@app.route('/admin/mapa')
@rol_required('administrador', 'super_admin')
def admin_mapa():
    ciudad = request.args.get('ciudad')
    conn = get_db(); cur = conn.cursor()
    q = "SELECT id,titulo,ciudad,estado,latitud,longitud FROM reportes WHERE latitud IS NOT NULL AND longitud IS NOT NULL"
    params = []
    if ciudad:
        q += " AND ciudad=%s"; params.append(ciudad)
    cur.execute(q, params)
    rows = cur.fetchall(); cur.close(); conn.close()
    reportes = [
        {**r,
         'latitud':  float(r['latitud'])  if r['latitud']  is not None else None,
         'longitud': float(r['longitud']) if r['longitud'] is not None else None}
        for r in rows
    ]
    return render_template('admin/mapa.html', reportes=reportes)

@app.route('/admin/estadisticas')
@rol_required('administrador', 'super_admin')
def admin_estadisticas():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT
        COUNT(*) as total,
        SUM(estado='resuelto')    as resueltos,
        SUM(estado='pendiente')   as pendientes,
        SUM(estado='en_progreso') as en_progreso,
        SUM(estado='asignado')    as asignados,
        SUM(estado='rechazado')   as rechazados,
        ROUND(AVG(gravedad_ia),1) as gravedad_promedio,
        SUM(CASE WHEN fecha_resolucion IS NOT NULL
            THEN TIMESTAMPDIFF(HOUR,creado_en,fecha_resolucion) ELSE NULL END) as horas_total,
        SUM(CASE WHEN fecha_resolucion IS NOT NULL THEN 1 ELSE 0 END) as con_resolucion
        FROM reportes""")
    kpis = cur.fetchone() or {}
    tiempo_promedio = round(kpis['horas_total'] / kpis['con_resolucion'], 1) \
        if kpis.get('con_resolucion') else 0
    cur.execute("""SELECT ciudad,
        COUNT(*) as total,
        SUM(estado='resuelto') as resueltos,
        SUM(estado='pendiente') as pendientes
        FROM reportes GROUP BY ciudad ORDER BY total DESC""")
    por_ciudad = cur.fetchall()
    cur.execute("""SELECT c.nombre as categoria, COUNT(r.id) as total
        FROM reportes r JOIN categorias c ON r.categoria_id=c.id
        GROUP BY c.nombre ORDER BY total DESC LIMIT 8""")
    por_categoria = cur.fetchall()
    cur.execute("SELECT estado, COUNT(*) as total FROM reportes GROUP BY estado ORDER BY total DESC")
    por_estado = cur.fetchall()
    cur.execute("SELECT prioridad, COUNT(*) as total FROM reportes GROUP BY prioridad ORDER BY FIELD(prioridad,'critica','alta','media','baja')")
    por_prioridad = cur.fetchall()
    cur.execute("""SELECT DATE(creado_en) as fecha, COUNT(*) as total
        FROM reportes WHERE creado_en >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY DATE(creado_en) ORDER BY fecha""")
    tendencia = cur.fetchall()
    cur.execute("""SELECT u.nombre, u.apellido,
        COUNT(r.id) as total_asignados,
        SUM(r.estado='resuelto') as resueltos
        FROM usuarios u JOIN reportes r ON r.tecnico_id=u.id
        GROUP BY u.id ORDER BY resueltos DESC LIMIT 5""")
    top_tecnicos = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE creado_en >= DATE_SUB(NOW(), INTERVAL 7 DAY)")
    usuarios_nuevos = (cur.fetchone() or {}).get('total', 0)
    cur.execute("SELECT COUNT(*) as total FROM usuarios WHERE activo=TRUE")
    total_usuarios = (cur.fetchone() or {}).get('total', 0)
    cur.close(); conn.close()
    return render_template('admin/estadisticas.html',
        kpis=kpis, tiempo_promedio=tiempo_promedio,
        por_ciudad=por_ciudad, por_categoria=por_categoria,
        por_estado=por_estado, por_prioridad=por_prioridad,
        tendencia=tendencia, top_tecnicos=top_tecnicos,
        usuarios_nuevos=usuarios_nuevos, total_usuarios=total_usuarios)

# ─── PERFIL ──────────────────────────────────────────────────
@app.route('/perfil')
@login_required
def mi_perfil():
    uid = session['usuario_id']
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT u.*, r.nombre as rol_nombre
        FROM usuarios u LEFT JOIN roles r ON u.rol_id=r.id
        WHERE u.id=%s""", (uid,))
    usuario = cur.fetchone()
    rol = session.get('rol', '')
    stats = {}
    if rol == 'ciudadano':
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s", (uid,))
        stats['total_reportes'] = (cur.fetchone() or {}).get('c', 0)
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s AND estado='resuelto'", (uid,))
        stats['resueltos'] = (cur.fetchone() or {}).get('c', 0)
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE usuario_id=%s AND estado='pendiente'", (uid,))
        stats['pendientes'] = (cur.fetchone() or {}).get('c', 0)
    elif rol == 'tecnico':
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE tecnico_id=%s AND estado='resuelto'", (uid,))
        stats['resueltos'] = (cur.fetchone() or {}).get('c', 0)
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE tecnico_id=%s AND estado='en_progreso'", (uid,))
        stats['en_progreso'] = (cur.fetchone() or {}).get('c', 0)
    elif rol in ('administrador', 'super_admin'):
        cur.execute("SELECT COUNT(*) as c FROM usuarios WHERE activo=TRUE")
        stats['total_usuarios'] = (cur.fetchone() or {}).get('c', 0)
        cur.execute("SELECT COUNT(*) as c FROM reportes")
        stats['total_reportes'] = (cur.fetchone() or {}).get('c', 0)
        cur.execute("SELECT COUNT(*) as c FROM reportes WHERE estado='pendiente'")
        stats['pendientes'] = (cur.fetchone() or {}).get('c', 0)
    cur.close(); conn.close()
    return render_template('perfil/mi_perfil.html', usuario=usuario, stats=stats)

@app.route('/perfil/editar', methods=['POST'])
@login_required
def editar_perfil():
    uid      = session['usuario_id']
    nombre   = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    nueva_pw = request.form.get('nueva_password', '').strip()
    conn = get_db(); cur = conn.cursor()
    if nueva_pw:
        if len(nueva_pw) < 6:
            flash('La contraseña debe tener mínimo 6 caracteres.', 'danger')
            cur.close(); conn.close()
            return redirect(url_for('mi_perfil'))
        cur.execute("UPDATE usuarios SET nombre=%s, apellido=%s, password_hash=%s WHERE id=%s",
                    (nombre, apellido, generate_password_hash(nueva_pw), uid))
    else:
        cur.execute("UPDATE usuarios SET nombre=%s, apellido=%s WHERE id=%s",
                    (nombre, apellido, uid))
    conn.commit()
    session['nombre'] = f"{nombre} {apellido}".strip()
    cur.close(); conn.close()
    flash('Perfil actualizado correctamente.', 'success')
    return redirect(url_for('mi_perfil'))

# ─── API ─────────────────────────────────────────────────────
@app.route('/api/v1/health')
def api_health():
    return jsonify({'status': 'ok', 'app': 'Urban Alert', 'version': '3.0'})

@app.route('/api/v1/stats')
def api_stats():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) as total,
        SUM(estado='resuelto')    as resueltos,
        SUM(estado='pendiente')   as pendientes,
        SUM(estado='en_progreso') as en_progreso
        FROM reportes""")
    data = cur.fetchone(); cur.close(); conn.close()
    return jsonify(dict(data) if data else {})

@app.route('/api/v1/reportes/mapa')
def api_reportes_mapa():
    ciudad = request.args.get('ciudad')
    conn = get_db(); cur = conn.cursor()
    sql = """SELECT id,titulo,estado,latitud,longitud,ciudad,prioridad
             FROM reportes WHERE publico=TRUE AND latitud IS NOT NULL AND longitud IS NOT NULL"""
    if ciudad:
        cur.execute(sql + " AND ciudad=%s ORDER BY creado_en DESC LIMIT 200", (ciudad,))
    else:
        cur.execute(sql + " ORDER BY creado_en DESC LIMIT 200")
    rows = cur.fetchall(); cur.close(); conn.close()
    return jsonify([{**r, 'lat': float(r['latitud']), 'lng': float(r['longitud'])} for r in rows])

@app.route('/api/v1/ciudades/stats')
def api_ciudades_stats():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT ciudad, COUNT(*) as total, SUM(estado='resuelto') as resueltos FROM reportes GROUP BY ciudad")
    data = cur.fetchall(); cur.close(); conn.close()
    return jsonify(list(data))

@app.route('/api/v1/analizar-imagen', methods=['POST'])
def api_analizar_imagen():
    """Endpoint IA en tiempo real para analizar imágenes."""
    import base64
    try:
        import anthropic as _anthropic
        data = request.get_json()
        if not data or 'imagen' not in data:
            return jsonify({'error': 'No se recibió imagen'}), 400
        img_b64    = data['imagen']
        media_type = data.get('tipo', 'image/jpeg')
        if media_type not in {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}:
            media_type = 'image/jpeg'
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not api_key:
            return jsonify({'error': 'ANTHROPIC_API_KEY no configurada en .env'}), 500
        client = _anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=400,
            messages=[{'role': 'user', 'content': [
                {'type': 'image', 'source': {'type': 'base64',
                 'media_type': media_type, 'data': img_b64}},
                {'type': 'text', 'text':
                 'Analiza esta imagen. Responde SOLO con JSON sin texto extra ni bloques markdown:\n'
                 '{"tipo_detectado":"nombre","categoria_id_sugerida":1,"gravedad":50,'
                 '"confianza":0.85,"titulo_sugerido":"titulo breve maximo 8 palabras","descripcion_ia":"descripcion detallada y recomendacion"}\n'
                 'IMPORTANTE: Si la imagen NO muestra un problema urbano real (persona, animal, '
                 'objeto domestico, meme, selfie, comida, etc.), responde EXACTAMENTE:\n'
                 '{"tipo_detectado":"No es problema urbano","categoria_id_sugerida":8,"gravedad":0,'
                 '"confianza":0.99,"titulo_sugerido":"","descripcion_ia":"La imagen no corresponde a un problema urbano."}\n'
                 'Categorias validas: 1=Bache 2=Basura 3=Espacio Publico 4=Senalizacion '
                 '5=Alumbrado 6=Arbol 7=Inundacion 8=Otro'}
            ]}]
        )
        texto = msg.content[0].text.strip()
        if texto.startswith('```'):
            texto = texto.split('```')[1]
            if texto.startswith('json'): texto = texto[4:]
        resultado = json.loads(texto)
        gravedad  = float(resultado.get('gravedad', 50))
        prioridad = ('critica' if gravedad >= 80 else
                     'alta'    if gravedad >= 60 else
                     'media'   if gravedad >= 40 else 'baja')
        return jsonify({
            'tipo_detectado':        resultado.get('tipo_detectado', 'Problema urbano'),
            'categoria_id_sugerida': int(resultado.get('categoria_id_sugerida', 8)),
            'gravedad':              gravedad,
            'prioridad':             prioridad,
            'confianza':             float(resultado.get('confianza', 0.85)),
            'descripcion_ia':        resultado.get('descripcion_ia', ''),
            'titulo_sugerido':       resultado.get('titulo_sugerido', ''),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── ERRORES ─────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return render_template('landing/index.html',
                           stats={}, recientes=[], por_ciudad=[]), 404

@app.errorhandler(500)
def server_error(e):
    return f'<h1>500 - Error interno</h1><pre>{e}</pre>', 500

# ──────────────────────────────────────────────
# CREAR TÉCNICO (admin)
# ──────────────────────────────────────────────
@app.route('/admin/usuarios/crear-tecnico', methods=['GET', 'POST'])
@rol_required('administrador', 'super_admin')
def admin_crear_tecnico():
    if request.method == 'POST':
        nombre       = request.form.get('nombre', '').strip()
        apellido     = request.form.get('apellido', '').strip()
        email        = request.form.get('email', '').strip().lower()
        password     = request.form.get('password', '')
        telefono     = request.form.get('telefono', '').strip()
        ciudad       = request.form.get('ciudad', 'Facatativá')
        especialidad = request.form.get('especialidad', '').strip()
        zona         = request.form.get('zona_cobertura', 'Todas')

        errores = []
        if not all([nombre, apellido, email, password]):
            errores.append('Nombre, apellido, correo y contraseña son obligatorios.')
        if password and len(password) < 6:
            errores.append('La contrasena debe tener minimo 6 caracteres.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('admin/crear_tecnico.html', form=request.form)

        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT id FROM usuarios WHERE email=%s", (email,))
        if cur.fetchone():
            flash('Ya existe un usuario con ese correo electronico.', 'warning')
            cur.close(); conn.close()
            return render_template('admin/crear_tecnico.html', form=request.form)

        cur.execute("""INSERT INTO usuarios
            (nombre, apellido, email, password_hash, telefono, ciudad, rol_id, activo, email_verificado)
            VALUES (%s, %s, %s, %s, %s, %s,
                    (SELECT id FROM roles WHERE nombre='tecnico'),
                    TRUE, TRUE)""",
            (nombre, apellido, email,
             generate_password_hash(password),
             telefono or None, ciudad))
        conn.commit()
        nuevo_uid = cur.lastrowid

        cur.execute("""INSERT INTO tecnicos (usuario_id, especialidad, zona_cobertura, disponible)
            VALUES (%s, %s, %s, TRUE)""",
            (nuevo_uid, especialidad or None, zona))
        conn.commit()
        cur.close(); conn.close()

        flash(f'Tecnico {nombre} {apellido} creado correctamente.', 'success')
        return redirect(url_for('admin_usuarios', tab='tecnicos'))

    return render_template('admin/crear_tecnico.html', form={})

# ─── ARRANQUE ────────────────────────────────────────────────
if __name__ == '__main__':
    port   = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=True)

