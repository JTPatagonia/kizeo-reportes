import os
import json
import imaplib
import email
import re
from datetime import datetime
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
    meta_rondas = db.Column(db.Integer, default=5)
    turno_activo = db.Column(db.String(50), default="")

with app.app_context():
    db.create_all()
    try:
        db.session.execute(db.text('ALTER TABLE instalacion_db ADD COLUMN IF NOT EXISTS turno_activo VARCHAR(50);'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()

    if InstalacionDB.query.count() == 0:
        iniciales = [
            { "nombre": "RONDA - ARAMARK ACONCAGUA", "comuna": "Colina", "lat": -33.2000, "lng": -70.6700, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - ARAMARK CONCEPCION", "comuna": "Santiago", "lat": -33.4489, "lng": -70.6693, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - DESCO", "comuna": "Pudahuel", "lat": -33.4312, "lng": -70.8012, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - DITALCAR", "comuna": "Maipú", "lat": -33.5100, "lng": -70.7500, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - GILI", "comuna": "San Bernardo", "lat": -33.5900, "lng": -70.7000, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - ICESTAR PUDAHUEL", "comuna": "Pudahuel", "lat": -33.4111, "lng": -70.7922, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - ICESTAR QUILICURA", "comuna": "Quilicura", "lat": -33.3666, "lng": -70.7333, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - MEGAFRIO RENCA", "comuna": "Renca", "lat": -33.4034, "lng": -70.7185, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA - UNIPACK", "comuna": "Conchalí", "lat": -33.3800, "lng": -70.6700, "rondas": 0, "meta_rondas": 5 },
            { "nombre": "RONDA PRUEBA FINAL", "comuna": "Huechuraba", "lat": -33.3700, "lng": -70.6300, "rondas": 0, "meta_rondas": 5 }
        ]
        for data in iniciales:
            inst = InstalacionDB(**data)
            db.session.add(inst)
        db.session.commit()

def limpiar_texto(texto):
    if not texto:
        return ""
    texto_sin_emojis = re.sub(r'[^\w\s]', '', texto, flags=re.UNICODE)
    return texto_sin_emojis.lower().strip()

def obtener_turno_actual():
    chile_tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(chile_tz)
    hora = ahora.hour
    fecha_str = ahora.strftime('%Y-%m-%d')
    
    if hora >= 20 or hora < 8:
        if hora < 8:
            fecha_str = (ahora - pytz.datetime.timedelta(days=1)).strftime('%Y-%m-%d')
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
        print(f"Error en turnos: {e}")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    try:
        verificar_y_actualizar_turnos()
        instalaciones = InstalacionDB.query.all()
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
    try:
        verificar_correos_kizeo()
        return jsonify({"status": "success", "message": "Correos verificados"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/historial-rondas', methods=['GET'])
def obtener_historial():
    try:
        reportes = ReporteKizeo.query.order_by(ReporteKizeo.id.desc()).limit(50).all()
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

def verificar_correos_kizeo():
    try:
        mail_server = os.getenv('MAIL_SERVER', 'imap.gmail.com')
        mail_user = os.getenv('MAIL_USER')
        mail_password = os.getenv('MAIL_PASSWORD')

        if not mail_user or not mail_password:
            return  

        mail = imaplib.IMAP4_SSL(mail_server)
        mail.login(mail_user, mail_password)
        mail.select('inbox')

        status, messages = mail.search(None, 'ALL')
        if status != 'OK':
            mail.logout()
            return

        lista_ids = messages[0].split()
        ultimos_ids = lista_ids[-30:] if len(lista_ids) > 30 else lista_ids

        for num in ultimos_ids:
            try:
                status, data = mail.fetch(num, '(RFC822)')
                if status != 'OK':
                    continue
                
                for response_part in data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        asunto = msg['subject'] or ""
                        remitente = msg['from'] or ""
                        
                        if "google" in remitente.lower() or "security" in remitente.lower() or "alerta de seguridad" in asunto.lower():
                            continue

                        cuerpo = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        cuerpo = payload.decode(errors='ignore')
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                cuerpo = payload.decode(errors='ignore')

                        texto_completo = f"{asunto} {cuerpo}"
                        texto_limpio = limpiar_texto(texto_completo)
                        msg_id = msg.get('Message-ID', str(num))
                        existe_reporte = ReporteKizeo.query.filter_by(form_id=msg_id).first()

                        if not existe_reporte:
                            if "novedad" in texto_limpio or "registran novedades" in texto_limpio or "alerta" in texto_limpio:
                                nuevo_reporte = ReporteKizeo(
                                    form_id=msg_id,
                                    usuario="⚠️ NOVEDAD / ALERTA",
                                    fecha_envio=str(datetime.now()),
                                    datos_json=json.dumps({"tipo": "NOVEDAD", "asunto": asunto})
                                )
                                db.session.add(nuevo_reporte)
                                db.session.commit()
                            
                            elif "ronda" in texto_limpio:
                                instalaciones = InstalacionDB.query.all()
                                for inst in instalaciones:
                                    palabras_clave = [limpiar_texto(p) for p in inst.nombre.replace("RONDA - ", "").split() if len(p) > 3]
                                    coincide = any(palabra in texto_limpio for palabra in palabras_clave)
                                    
                                    if coincide:
                                        if inst.rondas < inst.meta_rondas:
                                            inst.rondas += 1
                                            db.session.commit()

                                        nuevo_reporte = ReporteKizeo(
                                            form_id=msg_id,
                                            usuario="Kizeo Bot / Ronda",
                                            fecha_envio=str(datetime.now()),
                                            datos_json=json.dumps({"tipo": "RONDA", "asunto": asunto, "instalacion": inst.nombre})
                                        )
                                        db.session.add(nuevo_reporte)
                                        db.session.commit()
                                        break
            except Exception as mail_err:
                continue

        mail.logout()
    except Exception as e:
        print(f"Error general al verificar correos: {e}")

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "Sin datos"}), 400

        verificar_y_actualizar_turnos()

        form_id = str(content.get('form_id', ''))
        usuario = content.get('user', {}).get('login', 'Desconocido')
        fecha = content.get('update_time')
        
        form_name = content.get('form_name', '')
        form_name_limpio = limpiar_texto(form_name)
        
        if "novedad" not in form_name_limpio and "alerta" not in form_name_limpio:
            instalaciones = InstalacionDB.query.all()
            for inst in instalaciones:
                palabras_clave = [limpiar_texto(p) for p in inst.nombre.replace("RONDA - ", "").split() if len(p) > 3]
                coincide = any(palabra in form_name_limpio for palabra in palabras_clave)
                if coincide:
                    if inst.rondas < inst.meta_rondas:
                        inst.rondas += 1
                        db.session.commit()

        existe = ReporteKizeo.query.filter_by(form_id=form_id).first() if form_id else None
        if not existe:
            nuevo_reporte = ReporteKizeo(
                form_id=form_id if form_id else None,
                usuario=str(usuario),
                fecha_envio=str(fecha) if fecha else None,
                datos_json=json.dumps(content)
            )
            db.session.add(nuevo_reporte)
            db.session.commit()

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)