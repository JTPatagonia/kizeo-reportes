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

    # Limpiar alertas falsas de seguridad de Google guardadas anteriormente
    try:
         falsas = ReporteKizeo.query.filter(ReporteKizeo.datos_json.ilike('%Alerta de seguridad%')).all()
         for f in falsas:
             db.session.delete(f)
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
    # Quitar tildes y diacríticos
    texto_norm = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
    # Dejar solo letras, números y espacios
    texto_limpio = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto_norm)
    return re.sub(r'\s+', ' ', texto_limpio).lower().strip()

def decodificar_encabezado(valor):
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = ""
    for texto, encoding in partes:
        if isinstance(texto, bytes):
            resultado += texto.decode(encoding or 'utf-8', errors='ignore')
        else:
            resultado += str(texto)
    return resultado.strip()

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
        for inst in instalaciones:
            if inst.turno_activo != turno_actual:
                inst.rondas = 0
                inst.turno_activo = turno_actual
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error en turnos: {e}")

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
    ok, msg, procesados = verificar_correos_kizeo()
    if ok:
        return jsonify({"status": "success", "message": msg, "procesados": procesados}), 200
    else:
        return jsonify({"status": "error", "message": msg, "procesados": 0}), 200

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

def coincidencia_instalacion(nombre_db, texto_correo_limpio):
    # Ej: "RONDA - ICESTAR PUDAHUEL" -> ["icestar", "pudahuel"]
    base = limpiar_texto(nombre_db.replace("RONDA - ", "").replace("RONDA", ""))
    palabras = [p for p in base.split() if len(p) > 2]
    if not palabras:
        return False
    # Deben estar TODAS las palabras del nombre de la instalación en el correo
    # Así "ICESTAR PUDAHUEL" no se confunde con "ICESTAR QUILICURA"
    return all(p in texto_correo_limpio for p in palabras)

def verificar_correos_kizeo():
    procesados = 0
    try:
        mail_server = os.getenv('MAIL_SERVER', 'imap.gmail.com')
        mail_user = os.getenv('MAIL_USER')
        mail_password = os.getenv('MAIL_PASSWORD')

        if not mail_user or not mail_password:
            return False, "Faltan variables MAIL_USER o MAIL_PASSWORD en Render", 0

        # Timeout de 15s para que jamás cuelgue el worker de Gunicorn en Render
        mail = imaplib.IMAP4_SSL(mail_server, timeout=15)
        mail.login(mail_user, mail_password)
        mail.select('inbox')

        status, messages = mail.search(None, 'ALL')
        if status != 'OK' or not messages or not messages[0]:
            mail.logout()
            return True, "Bandeja vacía", 0

        lista_ids = messages[0].split()
        # Revisar los últimos 20 correos recibidos
        ultimos_ids = lista_ids[-20:] if len(lista_ids) > 20 else lista_ids

        instalaciones = InstalacionDB.query.all()
        chile_tz = pytz.timezone('America/Santiago')
        ahora_str = datetime.now(chile_tz).strftime('%Y-%m-%d %H:%M:%S')

        for num in ultimos_ids:
            try:
                # CLAVE: Solo descarga encabezados y los primeros 2000 bytes de texto (ignora los PDFs pesados)
                status, data = mail.fetch(num, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM MESSAGE-ID DATE)] BODY.PEEK[TEXT]<0.2000>)')
                if status != 'OK' or not data:
                    continue

                asunto = ""
                remitente = ""
                msg_id = ""
                cuerpo_snippet = ""

                for part in data:
                    if isinstance(part, tuple):
                        header_info = part[0].decode('utf-8', errors='ignore').upper()
                        contenido_bytes = part[1]
                        if 'HEADER' in header_info:
                            msg_hdr = email.message_from_bytes(contenido_bytes)
                            asunto = decodificar_encabezado(msg_hdr.get('Subject', ''))
                            remitente = decodificar_encabezado(msg_hdr.get('From', ''))
                            msg_id = (msg_hdr.get('Message-ID') or '').strip()
                        else:
                            cuerpo_snippet += contenido_bytes.decode('utf-8', errors='ignore')

                if not msg_id:
                    msg_id = f"imap-uid-{num.decode('utf-8', errors='ignore')}"

                asunto_limpio = limpiar_texto(asunto)
                remitente_limpio = limpiar_texto(remitente)
                texto_completo_limpio = limpiar_texto(f"{asunto} {cuerpo_snippet}")

                # Ignorar correos de Google o alertas de cuenta
                if "google" in remitente_limpio or "alerta de seguridad" in asunto_limpio or "accounts google" in texto_completo_limpio:
                    continue

                # Verificar si ya fue registrado en la base de datos
                existe = ReporteKizeo.query.filter_by(form_id=msg_id).first()
                if existe:
                    continue

                # 1. PLANO APARTE: ¿Es un correo de ALERTA / NOVEDADES?
                if "alerta" in asunto_limpio or "novedad" in texto_completo_limpio or "novedades" in texto_completo_limpio:
                    inst_detectada = "General"
                    for inst in instalaciones:
                        if coincidencia_instalacion(inst.nombre, texto_completo_limpio):
                            inst_detectada = inst.nombre.replace("RONDA - ", "")
                            break

                    nuevo_rep = ReporteKizeo(
                        form_id=msg_id,
                        usuario=f"⚠️ ALERTA ({inst_detectada})",
                        fecha_envio=ahora_str,
                        datos_json=json.dumps({
                            "tipo": "NOVEDAD",
                            "instalacion": inst_detectada,
                            "asunto": asunto
                        }, ensure_ascii=False)
                    )
                    db.session.add(nuevo_rep)
                    db.session.commit()
                    procesados += 1

                # 2. PLANO DE RONDAS: ¿Es un correo de RONDA normal?
                elif "ronda" in texto_completo_limpio:
                    for inst in instalaciones:
                        if coincidencia_instalacion(inst.nombre, texto_completo_limpio):
                            if inst.rondas < inst.meta_rondas:
                                inst.rondas += 1
                            
                            nuevo_rep = ReporteKizeo(
                                form_id=msg_id,
                                usuario=f"Guardia / {inst.nombre.replace('RONDA - ', '')}",
                                fecha_envio=ahora_str,
                                datos_json=json.dumps({
                                    "tipo": "RONDA",
                                    "instalacion": inst.nombre,
                                    "asunto": asunto
                                }, ensure_ascii=False)
                            )
                            db.session.add(nuevo_rep)
                            db.session.commit()
                            procesados += 1
                            break

            except Exception as e_inner:
                db.session.rollback()
                print(f"Error procesando correo {num}: {e_inner}")
                continue

        try:
            mail.logout()
        except Exception:
            pass

        return True, "Sincronización completada", procesados

    except Exception as e:
        print(f"Error IMAP: {e}")
        return False, f"Error IMAP: {str(e)}", 0

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
            if es_novedad:
                nuevo_reporte = ReporteKizeo(
                    form_id=form_id,
                    usuario="⚠️ ALERTA / WEBHOOK",
                    fecha_envio=str(fecha),
                    datos_json=json.dumps({"tipo": "NOVEDAD", "asunto": form_name or "Alerta reportada vía Webhook"}, ensure_ascii=False)
                )
                db.session.add(nuevo_reporte)
                db.session.commit()
            else:
                instalaciones = InstalacionDB.query.all()
                inst_nombre = "Instalación"
                for inst in instalaciones:
                    if coincidencia_instalacion(inst.nombre, texto_webhook):
                        inst_nombre = inst.nombre
                        if inst.rondas < inst.meta_rondas:
                            inst.rondas += 1
                        break

                nuevo_reporte = ReporteKizeo(
                    form_id=form_id,
                    usuario=str(usuario),
                    fecha_envio=str(fecha),
                    datos_json=json.dumps({"tipo": "RONDA", "instalacion": inst_nombre, "asunto": form_name}, ensure_ascii=False)
                )
                db.session.add(nuevo_reporte)
                db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)