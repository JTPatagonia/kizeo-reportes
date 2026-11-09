import os
import json
import time
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import re
import unicodedata
import base64
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, Response
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from database import db, ReporteKizeo

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', 'central_monitoreo_secreto_2026')

database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

ultimo_chequeo_imap = 0

class InstalacionDB(db.Model):
    __tablename__ = 'instalacion_db'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), unique=True, nullable=False)
    comuna = db.Column(db.String(100), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    rondas = db.Column(db.Integer, default=0)
    meta_rondas = db.Column(db.Integer, default=3)
    turno_activo = db.Column(db.String(50), default="")

class Operador(db.Model):
    __tablename__ = 'operador'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(150), nullable=False)

class SesionOperador(db.Model):
    __tablename__ = 'sesion_operador'
    id = db.Column(db.Integer, primary_key=True)
    operador_id = db.Column(db.Integer, db.ForeignKey('operador.id'), nullable=False)
    nombre_operador = db.Column(db.String(150), nullable=False)
    turno = db.Column(db.String(100), nullable=False)
    login_time = db.Column(db.String(50), nullable=False)
    logout_time = db.Column(db.String(50), nullable=True)
    estado = db.Column(db.String(20), default="ACTIVO")

with app.app_context():
    db.create_all()
    try:
        db.session.execute(db.text('ALTER TABLE instalacion_db ADD COLUMN IF NOT EXISTS turno_activo VARCHAR(50);'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    if Operador.query.count() == 0:
        admin = Operador(
            username="admin",
            password_hash=generate_password_hash("admin2026"),
            nombre_completo="Administrador Central"
        )
        db.session.add(admin)
        db.session.commit()

    if InstalacionDB.query.count() == 0:
        iniciales = [
            { "nombre": "RONDA - ARAMARK ACONCAGUA", "comuna": "Colina", "lat": -33.2000, "lng": -70.6700, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - ARAMARK CONCEPCION", "comuna": "Santiago", "lat": -33.4489, "lng": -70.6693, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - DESCO", "comuna": "Pudahuel", "lat": -33.4312, "lng": -70.8012, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - DITALCAR", "comuna": "Maipú", "lat": -33.5100, "lng": -70.7500, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - GILI", "comuna": "San Bernardo", "lat": -33.5900, "lng": -70.7000, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - ICESTAR PUDAHUEL", "comuna": "Pudahuel", "lat": -33.4111, "lng": -70.7922, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - ICESTAR QUILICURA", "comuna": "Quilicura", "lat": -33.3666, "lng": -70.7333, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - MEGAFRIO RENCA", "comuna": "Renca", "lat": -33.4034, "lng": -70.7185, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA - UNIPACK", "comuna": "Conchalí", "lat": -33.3800, "lng": -70.6700, "rondas": 0, "meta_rondas": 3 },
            { "nombre": "RONDA PRUEBA FINAL", "comuna": "Huechuraba", "lat": -33.3700, "lng": -70.6300, "rondas": 0, "meta_rondas": 3 }
        ]
        for data in iniciales:
            inst = InstalacionDB(**data)
            db.session.add(inst)
        db.session.commit()

def limpiar_texto(texto):
    if not texto:
        return ""
    texto_norm = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
    texto_limpio = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto_norm)
    return re.sub(r'\s+', ' ', texto_limpio).lower().strip()

def decodificar_encabezado(valor):
    if not valor:
        return ""
    try:
        partes = decode_header(valor)
        resultado = ""
        for texto, encoding in partes:
            if isinstance(texto, bytes):
                resultado += texto.decode(encoding or 'utf-8', errors='ignore')
            else:
                resultado += str(texto)
        return resultado.strip()
    except Exception:
        return str(valor)

def calcular_info_turno(dt_chile):
    if dt_chile.hour >= 20:
        inicio_turno = dt_chile.replace(hour=20, minute=0, second=0, microsecond=0)
        fecha_codigo = inicio_turno.strftime('%Y-%m-%d')
        fecha_visible = inicio_turno.strftime('%d/%m/%Y')
        return f"NOCHE-{fecha_codigo}", f"Día {fecha_visible} — Turno Nocturno (20:00 - 08:00)", inicio_turno
    elif dt_chile.hour < 8:
        ayer = dt_chile - timedelta(days=1)
        inicio_turno = ayer.replace(hour=20, minute=0, second=0, microsecond=0)
        fecha_codigo = inicio_turno.strftime('%Y-%m-%d')
        fecha_visible = inicio_turno.strftime('%d/%m/%Y')
        return f"NOCHE-{fecha_codigo}", f"Día {fecha_visible} — Turno Nocturno (20:00 - 08:00)", inicio_turno
    else:
        inicio_turno = dt_chile.replace(hour=8, minute=0, second=0, microsecond=0)
        fecha_codigo = inicio_turno.strftime('%Y-%m-%d')
        fecha_visible = inicio_turno.strftime('%d/%m/%Y')
        return f"DIA-{fecha_codigo}", f"Día {fecha_visible} — Turno Diurno (08:00 - 20:00)", inicio_turno

def obtener_datos_turno_actual():
    chile_tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(chile_tz)
    return calcular_info_turno(ahora)

def verificar_y_actualizar_turnos():
    try:
        turno_actual, _, _ = obtener_datos_turno_actual()
        instalaciones = InstalacionDB.query.all()
        cambio_turno = False
        for inst in instalaciones:
            if inst.turno_activo != turno_actual:
                inst.rondas = 0
                inst.turno_activo = turno_actual
                cambio_turno = True
        if cambio_turno:
            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error en turnos: {e}")

def buscar_instalacion_en_texto(instalaciones, texto_limpio):
    for inst in instalaciones:
        nombre_sin_prefijo = inst.nombre.replace("RONDA - ", "").replace("RONDA", "").strip()
        palabras_clave = [p for p in limpiar_texto(nombre_sin_prefijo).split() if len(p) > 2]
        if palabras_clave and all(p in texto_limpio for p in palabras_clave):
            return inst
    return None

def recalcular_contadores_turno_actual():
    codigo_turno_actual, _, _ = obtener_datos_turno_actual()
    instalaciones = InstalacionDB.query.all()
    conteo = {inst.nombre: 0 for inst in instalaciones}

    reportes = ReporteKizeo.query.all()
    for r in reportes:
        try:
            det = json.loads(r.datos_json or '{}')
            if det.get('turno_codigo') == codigo_turno_actual and det.get('tipo') == 'RONDA':
                nom = det.get('instalacion')
                if nom in conteo:
                    conteo[nom] += 1
        except Exception:
            continue

    for inst in instalaciones:
        inst.rondas = conteo.get(inst.nombre, 0)
        inst.turno_activo = codigo_turno_actual
    db.session.commit()

def verificar_correos_kizeo(forzar_reconteo=False):
    global ultimo_chequeo_imap
    procesados = 0
    mail = None
    try:
        mail_server = os.getenv('MAIL_SERVER', 'imap.gmail.com')
        mail_user = os.getenv('MAIL_USER')
        mail_password = os.getenv('MAIL_PASSWORD')

        if not mail_user or not mail_password:
            return False, "Faltan variables MAIL_USER o MAIL_PASSWORD en Render", 0

        ultimo_chequeo_imap = time.time()

        mail = imaplib.IMAP4_SSL(mail_server, timeout=10)
        mail.login(mail_user, mail_password)
        status, messages = mail.select('INBOX', readonly=True)
        
        if status != 'OK':
            mail.logout()
            return False, "No se pudo abrir INBOX", 0

        total_correos = int(messages[0])
        if total_correos == 0:
            mail.logout()
            return True, "Bandeja vacía", 0

        inicio = max(1, total_correos - 39)
        rango_lote = f"{inicio}:{total_correos}"

        status, data = mail.fetch(rango_lote, '(RFC822)')
        
        try:
            mail.logout()
        except Exception:
            pass

        if status != 'OK' or not data:
            return False, "No se pudieron obtener correos", 0

        chile_tz = pytz.timezone('America/Santiago')
        codigo_turno_actual, _, _ = obtener_datos_turno_actual()

        if forzar_reconteo:
            ReporteKizeo.query.delete()
            for inst in InstalacionDB.query.all():
                inst.rondas = 0
                inst.turno_activo = codigo_turno_actual
            db.session.commit()

        instalaciones = InstalacionDB.query.all()
        ids_existentes = set(r.form_id for r in ReporteKizeo.query.all() if r.form_id)

        idx = 0
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                idx += 1
                raw_msg = part[1]
                if not raw_msg:
                    continue

                msg = email.message_from_bytes(raw_msg)
                asunto = decodificar_encabezado(msg.get('Subject', ''))
                remitente = decodificar_encabezado(msg.get('From', ''))
                msg_id = (msg.get('Message-ID') or '').strip()
                date_hdr = decodificar_encabezado(msg.get('Date', ''))

                if not asunto or not date_hdr:
                    continue

                try:
                    dt_correo = parsedate_to_datetime(date_hdr)
                    if dt_correo.tzinfo is None:
                        dt_correo = pytz.utc.localize(dt_correo)
                    dt_correo_chile = dt_correo.astimezone(chile_tz)
                except Exception:
                    continue

                turno_cod_correo, turno_label_correo, _ = calcular_info_turno(dt_correo_chile)
                fecha_correo_str = dt_correo_chile.strftime('%d/%m/%Y %H:%M:%S')

                cuerpo_texto = ""
                pdf_base64 = ""
                nombre_pdf = ""

                for part_m in msg.walk():
                    content_type = part_m.get_content_type()
                    filename = part_m.get_filename()
                    if filename:
                        filename = decodificar_encabezado(filename)

                    try:
                        payload_bytes = part_m.get_payload(decode=True)
                        if payload_bytes:
                            if payload_bytes.startswith(b'%PDF'):
                                pdf_base64 = base64.b64encode(payload_bytes).decode('utf-8')
                                nombre_pdf = filename or "reporte_kizeo.pdf"
                    except Exception:
                        pass

                    if content_type == "text/plain" and not cuerpo_texto:
                        try:
                            payload = part_m.get_payload(decode=True)
                            charset = part_m.get_content_charset() or 'utf-8'
                            cuerpo_texto = payload.decode(charset, errors='ignore')
                        except Exception:
                            pass

                if not cuerpo_texto:
                    cuerpo_texto = asunto

                nombre_remitente = re.sub(r'<[^>]+>', '', remitente).strip()
                asunto_limpio = limpiar_texto(asunto)
                remitente_limpio = limpiar_texto(nombre_remitente)
                texto_busqueda = f"{asunto_limpio} {remitente_limpio}"

                if any(x in texto_busqueda for x in ["alerta de seguridad", "finish setting up", "verificacion", "google", "render"]):
                    continue

                uid_unico = msg_id if msg_id else f"lote-{idx}-{asunto_limpio[:25]}-{fecha_correo_str}"
                tiene_pdf_bool = bool(pdf_base64)

                if "alerta" in asunto_limpio or "novedad" in asunto_limpio:
                    inst_obj = buscar_instalacion_en_texto(instalaciones, texto_busqueda)
                    nombre_inst = inst_obj.nombre.replace("RONDA - ", "") if inst_obj else (nombre_remitente or "General")

                    rep_existente = ReporteKizeo.query.filter_by(form_id=uid_unico).first()
                    if rep_existente:
                        if not json.loads(rep_existente.datos_json or '{}').get('tiene_pdf') and tiene_pdf_bool:
                            rep_existente.datos_json = json.dumps({
                                "tipo": "NOVEDAD",
                                "instalacion": nombre_inst,
                                "asunto": asunto,
                                "cuerpo": cuerpo_texto[:2500],
                                "tiene_pdf": tiene_pdf_bool,
                                "pdf_base64": pdf_base64,
                                "nombre_pdf": nombre_pdf,
                                "remitente": nombre_remitente,
                                "turno_codigo": turno_cod_correo,
                                "turno_etiqueta": turno_label_correo
                            }, ensure_ascii=False)
                    else:
                        nuevo_rep = ReporteKizeo(
                            form_id=uid_unico,
                            usuario=f"⚠️ ALERTA ({nombre_inst})",
                            fecha_envio=fecha_correo_str,
                            datos_json=json.dumps({
                                "tipo": "NOVEDAD",
                                "instalacion": nombre_inst,
                                "asunto": asunto,
                                "cuerpo": cuerpo_texto[:2500],
                                "tiene_pdf": tiene_pdf_bool,
                                "pdf_base64": pdf_base64,
                                "nombre_pdf": nombre_pdf,
                                "remitente": nombre_remitente,
                                "turno_codigo": turno_cod_correo,
                                "turno_etiqueta": turno_label_correo
                            }, ensure_ascii=False)
                        )
                        db.session.add(nuevo_rep)
                        procesados += 1

                elif "ronda" in asunto_limpio:
                    inst_obj = buscar_instalacion_en_texto(instalaciones, texto_busqueda)
                    if inst_obj:
                        if turno_cod_correo == codigo_turno_actual and not ReporteKizeo.query.filter_by(form_id=uid_unico).first():
                            inst_obj.rondas += 1

                        rep_existente = ReporteKizeo.query.filter_by(form_id=uid_unico).first()
                        if not rep_existente:
                            nuevo_rep = ReporteKizeo(
                                form_id=uid_unico,
                                usuario=f"Guardia / {inst_obj.nombre.replace('RONDA - ', '')}",
                                fecha_envio=fecha_correo_str,
                                datos_json=json.dumps({
                                    "tipo": "RONDA",
                                    "instalacion": inst_obj.nombre,
                                    "asunto": asunto,
                                    "cuerpo": cuerpo_texto[:2500],
                                    "tiene_pdf": tiene_pdf_bool,
                                    "pdf_base64": pdf_base64,
                                    "nombre_pdf": nombre_pdf,
                                    "remitente": nombre_remitente,
                                    "turno_codigo": turno_cod_correo,
                                    "turno_etiqueta": turno_label_correo
                                }, ensure_ascii=False)
                            )
                            db.session.add(nuevo_rep)
                            procesados += 1

        db.session.commit()
        recalcular_contadores_turno_actual()
        return True, f"Sincronizado correctamente ({codigo_turno_actual})", procesados

    except Exception as e:
        db.session.rollback()
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
        return False, f"Error IMAP: {str(e)}", 0

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    data = request.json if request.is_json else request.form
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    operador = Operador.query.filter_by(username=username).first()
    if operador and check_password_hash(operador.password_hash, password):
        session['operador_id'] = operador.id
        session['nombre_operador'] = operador.nombre_completo

        chile_tz = pytz.timezone('America/Santiago')
        ahora_chile = datetime.now(chile_tz)
        _, etiqueta_turno, _ = calcular_info_turno(ahora_chile)

        nueva_sesion = SesionOperador(
            operador_id=operador.id,
            nombre_operador=operador.nombre_completo,
            turno=etiqueta_turno,
            login_time=ahora_chile.strftime('%d/%m/%Y %H:%M:%S'),
            estado="ACTIVO"
        )
        db.session.add(nueva_sesion)
        db.session.commit()
        session['sesion_id'] = nueva_sesion.id

        if request.is_json:
            return jsonify({"status": "success", "redirect": "/"}), 200
        return redirect(url_for('home'))
    
    if request.is_json:
        return jsonify({"status": "error", "message": "Usuario o contraseña incorrectos"}), 401
    return render_template('login.html', error="Usuario o contraseña incorrectos")

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    sesion_id = session.get('sesion_id')
    if sesion_id:
        sesion_op = SesionOperador.query.get(sesion_id)
        if sesion_op and sesion_op.estado == "ACTIVO":
            chile_tz = pytz.timezone('America/Santiago')
            sesion_op.logout_time = datetime.now(chile_tz).strftime('%d/%m/%Y %H:%M:%S')
            sesion_op.estado = "CERRADO"
            db.session.commit()
    
    session.clear()
    if request.is_json:
        return jsonify({"status": "success", "redirect": "/login"}), 200
    return redirect(url_for('login'))

@app.route('/api/sesiones-auditoria', methods=['GET'])
def obtener_auditoria_sesiones():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        sesiones = SesionOperador.query.order_by(SesionOperador.id.desc()).limit(50).all()
        resultado = [{
            "id": s.id,
            "nombre": s.nombre_operador,
            "turno": s.turno,
            "login": s.login_time,
            "logout": s.logout_time or "En turno activo...",
            "estado": s.estado
        } for s in sesiones]
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/crear-operador', methods=['POST'])
def crear_operador():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    
    operador_actual = Operador.query.get(session.get('operador_id'))
    if not operador_actual or operador_actual.username != 'admin':
        return jsonify({"error": "Acceso denegado. Solo el administrador puede registrar nuevos operadores."}), 403

    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        nombre = data.get('nombre_completo', '').strip()

        if not username or not password or not nombre:
            return jsonify({"error": "Faltan datos obligatorios"}), 400

        existente = Operador.query.filter_by(username=username).first()
        if existente:
            return jsonify({"error": "El nombre de usuario ya existe"}), 400

        nuevo_op = Operador(
            username=username,
            password_hash=generate_password_hash(password),
            nombre_completo=nombre
        )
        db.session.add(nuevo_op)
        db.session.commit()
        return jsonify({"status": "success", "message": "Operador creado correctamente"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def home():
    if 'operador_id' not in session:
        return redirect(url_for('login'))
    operador_actual = Operador.query.get(session.get('operador_id'))
    es_admin = operador_actual.username == 'admin' if operador_actual else False
    return render_template('index.html', operador=session.get('nombre_operador'), es_admin=es_admin)

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        verificar_y_actualizar_turnos()
        # Se omite el IMAP síncrono aquí para evitar que la página se congele al iniciar

        instalaciones = InstalacionDB.query.order_by(InstalacionDB.id.asc()).all()
        _, etiqueta_turno_actual, _ = obtener_datos_turno_actual()
        resultado = [{
            "id": i.id,
            "nombre": i.nombre,
            "comuna": i.comuna,
            "lat": i.lat,
            "lng": i.lng,
            "rondas": i.rondas,
            "meta_rondas": i.meta_rondas,
            "turno": i.turno_activo,
            "turno_etiqueta": etiqueta_turno_actual
        } for i in instalaciones]
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verificar-correo', methods=['GET'])
def disparar_verificacion_correo():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    forzar = request.args.get('reconteo') == '1'
    ok, msg, procesados = verificar_correos_kizeo(forzar_reconteo=forzar)
    return jsonify({
        "status": "success" if ok else "error",
        "message": msg,
        "procesados": procesados
    }), 200

@app.route('/api/historial-rondas', methods=['GET'])
def obtener_historial():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        codigo_actual, etiqueta_actual, _ = obtener_datos_turno_actual()
        reportes = ReporteKizeo.query.order_by(ReporteKizeo.id.desc()).limit(200).all()
        historial = [{
            "id": r.id,
            "form_id": r.form_id,
            "usuario": r.usuario,
            "fecha_envio": r.fecha_envio,
            "detalles": r.datos_json,
            "turno_actual_codigo": codigo_actual,
            "turno_actual_etiqueta": etiqueta_actual
        } for r in reportes]
        return jsonify(historial), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/detalle-reporte/<int:reporte_id>', methods=['GET'])
def obtener_detalle_reporte(reporte_id):
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        rep = ReporteKizeo.query.get(reporte_id)
        if not rep:
            return jsonify({"error": "Reporte no encontrado"}), 404
        
        detalles = json.loads(rep.datos_json or '{}')
        return jsonify({
            "id": rep.id,
            "usuario": rep.usuario,
            "fecha_envio": rep.fecha_envio,
            "asunto": detalles.get('asunto', 'Sin asunto'),
            "cuerpo": detalles.get('cuerpo', 'Sin contenido en el cuerpo del mensaje.'),
            "remitente": detalles.get('remitente', 'Desconocido'),
            "instalacion": detalles.get('instalacion', 'General'),
            "tiene_pdf": detalles.get('tiene_pdf', False),
            "nombre_pdf": detalles.get('nombre_pdf', 'reporte.pdf'),
            "tipo": detalles.get('tipo', 'INFORME')
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/ver-pdf/<int:reporte_id>')
def servir_pdf_dinamico(reporte_id):
    if 'operador_id' not in session:
        return "No autorizado", 401
    try:
        rep = ReporteKizeo.query.get(reporte_id)
        if not rep:
            return "No encontrado", 404
        detalles = json.loads(rep.datos_json or '{}')
        pdf_b64 = detalles.get('pdf_base64', '')
        if not pdf_b64:
            return "PDF no disponible", 404
        
        pdf_bytes = base64.b64decode(pdf_b64)
        return Response(pdf_bytes, mimetype='application/pdf')
    except Exception as e:
        return str(e), 500

@app.route('/api/actualizar-meta', methods=['POST'])
def actualizar_meta():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        data = request.json
        inst = InstalacionDB.query.get(data.get('id'))
        if inst:
            inst.meta_rondas = int(data.get('meta_rondas'))
            db.session.commit()
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "No encontrada"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/actualizar-ubicacion', methods=['POST'])
def actualizar_ubicacion():
    if 'operador_id' not in session:
        return jsonify({"error": "No autorizado"}), 401
    try:
        data = request.json
        inst = InstalacionDB.query.get(data.get('id'))
        if inst:
            inst.lat = float(data.get('lat'))
            inst.lng = float(data.get('lng'))
            db.session.commit()
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "No encontrada"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "Sin datos"}), 400

        verificar_y_actualizar_turnos()

        form_id = str(content.get('form_id') or content.get('id') or datetime.now().timestamp())
        usuario = content.get('user', {}).get('login', 'Guardia Kizeo')
        
        chile_tz = pytz.timezone('America/Santiago')
        ahora_chile = datetime.now(chile_tz)
        fecha = ahora_chile.strftime('%d/%m/%Y %H:%M:%S')
        turno_cod, turno_label, _ = calcular_info_turno(ahora_chile)
        
        form_name = content.get('form_name', '')
        texto_webhook = limpiar_texto(f"{form_name} {json.dumps(content)}")
        
        es_novedad = "novedad" in texto_webhook or "alerta" in texto_webhook

        existe = ReporteKizeo.query.filter_by(form_id=form_id).first()
        if not existe:
            instalaciones = InstalacionDB.query.all()
            inst_obj = buscar_instalacion_en_texto(instalaciones, texto_webhook)
            
            if es_novedad:
                nombre_inst = inst_obj.nombre.replace("RONDA - ", "") if inst_obj else "General"
                nuevo_reporte = ReporteKizeo(
                    form_id=form_id,
                    usuario=f"⚠️ ALERTA ({nombre_inst})",
                    fecha_envio=str(fecha),
                    datos_json=json.dumps({
                        "tipo": "NOVEDAD",
                        "instalacion": nombre_inst,
                        "asunto": form_name,
                        "cuerpo": json.dumps(content, ensure_ascii=False),
                        "tiene_pdf": False,
                        "pdf_base64": "",
                        "nombre_pdf": "",
                        "remitente": usuario,
                        "turno_codigo": turno_cod,
                        "turno_etiqueta": turno_label
                    }, ensure_ascii=False)
                )
                db.session.add(nuevo_reporte)
                db.session.commit()
            else:
                nombre_inst = inst_obj.nombre if inst_obj else "Instalación"
                if inst_obj:
                    inst_obj.rondas += 1
                nuevo_reporte = ReporteKizeo(
                    form_id=form_id,
                    usuario=str(usuario),
                    fecha_envio=str(fecha),
                    datos_json=json.dumps({
                        "tipo": "RONDA",
                        "instalacion": nombre_inst,
                        "asunto": form_name,
                        "cuerpo": json.dumps(content, ensure_ascii=False),
                        "tiene_pdf": False,
                        "pdf_base64": "",
                        "nombre_pdf": "",
                        "remitente": usuario,
                        "turno_codigo": turno_cod,
                        "turno_etiqueta": turno_label
                    }, ensure_ascii=False)
                )
                db.session.add(nuevo_reporte)
                db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)