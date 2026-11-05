import os
import json
import imaplib
import email
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

with app.app_context():
    try:
        db.create_all()
        print("¡Tablas creadas o verificadas con éxito en PostgreSQL!")
    except Exception as e:
        print(f"Aviso de conexión a base de datos en inicio: {e}")

# Instalaciones con meta total de rondas por turno (ej: meta de 5 rondas)
# Las rondas inician en 0 y aumentan automáticamente con los correos/webhooks de Kizeo
instalaciones_memoria = [
    { "id": 1, "nombre": "RONDA - ARAMARK ACONCAGUA", "comuna": "Colina", "lat": -33.2000, "lng": -70.6700, "rondas": 0, "meta_rondas": 5 },
    { "id": 2, "nombre": "RONDA - ARAMARK CONCEPCION", "comuna": "Santiago", "lat": -33.4489, "lng": -70.6693, "rondas": 0, "meta_rondas": 5 },
    { "id": 3, "nombre": "RONDA - DESCO", "comuna": "Pudahuel", "lat": -33.4312, "lng": -70.8012, "rondas": 0, "meta_rondas": 5 },
    { "id": 4, "nombre": "RONDA - DITALCAR", "comuna": "Maipú", "lat": -33.5100, "lng": -70.7500, "rondas": 0, "meta_rondas": 5 },
    { "id": 5, "nombre": "RONDA - GILI", "comuna": "San Bernardo", "lat": -33.5900, "lng": -70.7000, "rondas": 0, "meta_rondas": 5 },
    { "id": 6, "nombre": "RONDA - ICESTAR PUDAHUEL", "comuna": "Pudahuel", "lat": -33.4111, "lng": -70.7922, "rondas": 0, "meta_rondas": 5 },
    { "id": 7, "nombre": "RONDA - ICESTAR QUILICURA", "comuna": "Quilicura", "lat": -33.3666, "lng": -70.7333, "rondas": 0, "meta_rondas": 5 },
    { "id": 8, "nombre": "RONDA - MEGAFRIO RENCA", "comuna": "Renca", "lat": -33.4034, "lng": -70.7185, "rondas": 0, "meta_rondas": 5 },
    { "id": 9, "nombre": "RONDA - UNIPACK", "comuna": "Conchalí", "lat": -33.3800, "lng": -70.6700, "rondas": 0, "meta_rondas": 5 },
    { "id": 10, "nombre": "RONDA PRUEBA FINAL", "comuna": "Huechuraba", "lat": -33.3700, "lng": -70.6300, "rondas": 0, "meta_rondas": 5 }
]

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    try:
        return jsonify(instalaciones_memoria), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Ruta para configurar la meta total de rondas de una instalación si se requiere
@app.route('/api/actualizar-meta', methods=['POST'])
def actualizar_meta():
    try:
        data = request.json
        inst_id = data.get('id')
        nueva_meta = data.get('meta_rondas')

        for inst in instalaciones_memoria:
            if inst['id'] == int(inst_id):
                if nueva_meta is not None:
                    inst['meta_rondas'] = int(nueva_meta)
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

        status, messages = mail.search(None, '(UNSEEN SUBJECT "Kizeo")')
        
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

                    # Automatización: Buscar a qué instalación pertenece el correo y sumar +1 ronda
                    for inst in instalaciones_memoria:
                        if inst['nombre'].lower() in asunto.lower() or inst['nombre'].lower() in cuerpo.lower():
                            inst['rondas'] += 1
                            print(f"Ronda sumada automáticamente para: {inst['nombre']}")

        mail.logout()
    except Exception as e:
        print(f"Error al verificar correos automáticos: {e}")

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "No se recibieron datos"}), 400

        verificar_correos_kizeo()

        form_id = content.get('form_id')
        usuario = content.get('user', {}).get('login', 'Desconocido')
        fecha = content.get('update_time')
        
        # Opcional: También sumar automáticamente si el webhook trae el nombre del formulario/instalación
        form_name = content.get('form_name', '')
        for inst in instalaciones_memoria:
            if inst['nombre'].lower() in form_name.lower():
                inst['rondas'] += 1

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