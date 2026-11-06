import os
import json
import imaplib
import email
from email.header import decode_header
import re
import unicodedata
from datetime import datetime, timedelta
import pytz
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from database import db, ReporteKizeo

app = Flask(__name__)
CORS(app)

database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif database_url and database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

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

with app.app_context():
    db.create_all()
    try:
        db.session.execute(db.text('ALTER TABLE instalacion_db ADD COLUMN IF NOT EXISTS turno_activo VARCHAR(50);'))
        db.session.commit()
    except Exception:
        db.session.rollback()

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

def obtener_turno_actual():
    chile_tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(chile_tz)
    hora = ahora.hour
    fecha_str = ahora.strftime('%Y-%m-%d')
    
    if hora >= 20 or hora < 8:
        if hora < 8:
            fecha_str = (ahora - timedelta(days=1)).strftime('%Y-%m-%d')
        return f"NOCHE-{fecha_str}"
    else:
        return f"DIA-{fecha_str}"

def verificar_y_actualizar_turnos():
    try:
        turno_actual = obtener_turno_actual()
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

def verificar_correos_kizeo(forzar_reconteo=False):
    procesados = 0
    mail = None
    try:
        mail_server = os.getenv('MAIL_SERVER', 'imap.gmail.com')
        mail_user = os.getenv('MAIL_USER')
        mail_password = os.getenv('MAIL_PASSWORD')

        if not mail_user or not mail_password:
            return False, "Faltan variables MAIL_USER o MAIL_PASSWORD en Render", 0

        # 1. Conectar y descargar TODOS los encabezados en UN SOLO VIAJE (tarda < 0.5 seg)
        mail = imaplib.IMAP4_SSL(mail_server, timeout=8)
        mail.login(mail_user, mail_password)
        status, messages = mail.select('INBOX', readonly=True)
        
        if status != 'OK':
            mail.logout()
            return False, "No se pudo abrir INBOX", 0

        total_correos = int(messages[0])
        if total_correos == 0:
            mail.logout()
            return True, "Bandeja vacía", 0

        inicio = max(1, total_correos - 24)
        rango_lote = f"{inicio}:{total_correos}"

        # PETICIÓN ÚNICA EN LOTE (No hay bucle de red, descarga los 25 encabezados de golpe)
        status, data = mail.fetch(rango_lote, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID DATE)])')
        
        try:
            mail.logout()
        except Exception:
            pass

        if status != 'OK' or not data:
            return False, "No se pudieron obtener encabezados", 0

        # 2. Ya con los correos en memoria, procesamos rápido en la base de datos
        if forzar_reconteo:
            ReporteKizeo.query.delete()
            for inst in InstalacionDB.query.all():
                inst.rondas = 0
            db.session.commit()

        instalaciones = InstalacionDB.query.all()
        ids_existentes = set(r.form_id for r in ReporteKizeo.query.all() if r.form_id)
        chile_tz = pytz.timezone('America/Santiago')
        ahora_str = datetime.now(chile_tz).strftime('%Y-%m-%d %H:%M:%S')

        idx = 0
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                idx += 1
                raw_header = part[1]
                if not raw_header:
                    continue

                msg_hdr = email.message_from_bytes(raw_header)
                asunto = decodificar_encabezado(msg_hdr.get('Subject', ''))
                remitente = decodificar_encabezado(msg_hdr.get('From', ''))
                msg_id = (msg_hdr.get('Message-ID') or '').strip()
                date_hdr = decodificar_encabezado(msg_hdr.get('Date', ''))
                fecha_correo = date_hdr[:25] if date_hdr else ahora_str

                if not asunto:
                    continue

                nombre_remitente = re.sub(r'<[^>]+>', '', remitente).strip()
                asunto_limpio = limpiar_texto(asunto)
                remitente_limpio = limpiar_texto(nombre_remitente)
                texto_busqueda = f"{asunto_limpio} {remitente_limpio}"

                # Ignorar correos ajenos a Kizeo
                if any(x in texto_busqueda for x in ["alerta de seguridad", "finish setting up", "verificacion", "google", "render"]):
                    continue

                uid_unico = msg_id if msg_id else f"lote-{idx}-{asunto_limpio[:25]}"
                if uid_unico in ids_existentes:
                    continue

                # A) ¿Es ALERTA o NOVEDAD? -> Va a la tabla roja de Novedades, NO suma ronda
                if "alerta" in asunto_limpio or "novedad" in asunto_limpio:
                    inst_obj = buscar_instalacion_en_texto(instalaciones, texto_busqueda)
                    nombre_inst = inst_obj.nombre.replace("RONDA - ", "") if inst_obj else (nombre_remitente or "General")

                    nuevo_rep = ReporteKizeo(
                        form_id=uid_unico,
                        usuario=f"⚠️ ALERTA ({nombre_inst})",
                        fecha_envio=fecha_correo,
                        datos_json=json.dumps({
                            "tipo": "NOVEDAD",
                            "instalacion": nombre_inst,
                            "asunto": asunto
                        }, ensure_ascii=False)
                    )
                    db.session.add(nuevo_rep)
                    ids_existentes.add(uid_unico)
                    procesados += 1

                # B) ¿Es RONDA? -> Busca instalación y suma +1
                elif "ronda" in asunto_limpio:
                    inst_obj = buscar_instalacion_en_texto(instalaciones, texto_busqueda)
                    if inst_obj:
                        inst_obj.rondas += 1
                        nuevo_rep = ReporteKizeo(
                            form_id=uid_unico,
                            usuario=f"Guardia / {inst_obj.nombre.replace('RONDA - ', '')}",
                            fecha_envio=fecha_correo,
                            datos_json=json.dumps({
                                "tipo": "RONDA",
                                "instalacion": inst_obj.nombre,
                                "asunto": asunto
                            }, ensure_ascii=False)
                        )
                        db.session.add(nuevo_rep)
                        ids_existentes.add(uid_unico)
                        procesados += 1

        # Un único commit a PostgreSQL al terminar el lote
        db.session.commit()
        return True, "Sincronización instantánea completada", procesados

    except Exception as e:
        db.session.rollback()
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
        return False, f"Error IMAP: {str(e)}", 0

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    try:
        verificar_y_actualizar_turnos()
        instalaciones = InstalacionDB.query.order_by(InstalacionDB.id.asc()).all()
        resultado = [{
            "id": i.id,
            "nombre": i.nombre,
            "comuna": i.comuna,
            "lat": i.lat,
            "lng": i.lng,
            "rondas": i.rondas,
            "meta_rondas": i.meta_rondas,
            "turno": i.turno_activo
        } for i in instalaciones]
        return jsonify(resultado), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/verificar-correo', methods=['GET'])
def disparar_verificacion_correo():
    ok, msg, procesados = verificar_correos_kizeo(forzar_reconteo=True)
    return jsonify({
        "status": "success" if ok else "error",
        "message": msg,
        "procesados": procesados
    }), 200

@app.route('/api/historial-rondas', methods=['GET'])
def obtener_historial():
    try:
        reportes = ReporteKizeo.query.order_by(ReporteKizeo.id.desc()).limit(60).all()
        historial = [{
            "id": r.id,
            "form_id": r.form_id,
            "usuario": r.usuario,
            "fecha_envio": r.fecha_envio,
            "detalles": r.datos_json
        } for r in reportes]
        return jsonify(historial), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/actualizar-meta', methods=['POST'])
def actualizar_meta():
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
        fecha = content.get('update_time') or datetime.now(chile_tz).strftime('%Y-%m-%d %H:%M:%S')
        
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
                    datos_json=json.dumps({"tipo": "NOVEDAD", "instalacion": nombre_inst, "asunto": form_name}, ensure_ascii=False)
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
                    datos_json=json.dumps({"tipo": "RONDA", "instalacion": nombre_inst, "asunto": form_name}, ensure_ascii=False)
                )
                db.session.add(nuevo_reporte)
                db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)