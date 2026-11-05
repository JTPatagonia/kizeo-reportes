import os
import json
import imaplib
import email
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
    
    # Asegurar que la columna turno_activo exista en bases de datos ya creadas previamente
    try:
        db.session.execute(db.text('ALTER TABLE instalacion_db ADD COLUMN IF NOT EXISTS turno_activo VARCHAR(50);'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Aviso de migración de columna: {e}")

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
    turno_actual = obtener_turno_actual()
    instalaciones = InstalacionDB.query.all()
    for inst in instalaciones:
        if inst.turno_activo != turno_actual:
            inst.rondas = 0
            inst.turno_activo = turno_actual
            db.session.commit()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    try:
        verificar_y_actualizar_turnos()
        verificar_correos_kizeo()
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
        inst_id = data.get('id')
        nueva_meta = data.get('meta_rondas')

        inst = InstalacionDB.query.get(inst_id)
        if inst and nueva_meta is not None:
            inst.meta_rondas = int(nueva_meta)
            db.session.commit()
            return jsonify({"status": "success"}), 200
        return jsonify({"error": "No encontrada"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/actualizar-ubicacion', methods=['POST'])
def actualizar_ubicacion():
    try:
        data = request.json
        inst_id = data.get('id')
        nueva_lat = data.get('lat')
        nueva_lng = data.get('lng')

        inst = InstalacionDB.query.get(inst_id)
        if inst and nueva_lat is not None and nueva_lng is not None:
            inst.lat = float(nueva_lat)
            inst.lng = float(nueva_lng)
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

        status, messages = mail.search(None, '(UNSEEN SUBJECT "RONDA")')
        
        for num in messages[0].split():
            status, data = mail.fetch(num, '(RFC822)')
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    asunto = msg['subject']
                    
                    cuerpo = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                cuerpo = part.get_payload(decode=True).decode()
                    else:
                        cuerpo = msg.get_payload(decode=True).decode()

                    texto_completo = f"{asunto} {cuerpo}"

                    instalaciones = InstalacionDB.query.all()
                    for inst in instalaciones:
                        nombre_limpio = inst.nombre.replace("RONDA - ", "").strip().lower()
                        if nombre_limpio in texto_completo.lower() or inst.nombre.lower() in texto_completo.lower():
                            if inst.rondas < inst.meta_rondas:
                                inst.rondas += 1
                                db.session.commit()
                            break

            mail.store(num, '+FLAGS', '\\Seen')

        mail.logout()
    except Exception as e:
        print(f"Error al verificar correos automáticos: {e}")

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "Sin datos"}), 400

        verificar_y_actualizar_turnos()
        verificar_correos_kizeo()

        form_id = content.get('form_id')
        usuario = content.get('user', {}).get('login', 'Desconocido')
        fecha = content.get('update_time')
        
        form_name = content.get('form_name', '')
        instalaciones = InstalacionDB.query.all()
        for inst in instalaciones:
            if inst.nombre.lower() in form_name.lower():
                if inst.rondas < inst.meta_rondas:
                    inst.rondas += 1
                    db.session.commit()

        nuevo_reporte = ReporteKizeo(
            form_id=str(form_id) if form_id else None,
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