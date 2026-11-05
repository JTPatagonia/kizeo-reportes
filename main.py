import os
import json
import imaplib
import email
from email.header import decode_header
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from database import db, ReporteKizeo

app = Flask(__name__)
CORS(app)

# Configuración de tu base de datos PostgreSQL en Render
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

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado_instalaciones():
    try:
        # Aquí puedes consultar los datos reales de tu base de datos PostgreSQL
        # Por ahora devolvemos la estructura con las 20 instalaciones de la RM
        instalaciones_fijas = [
            { "id": 1, "nombre": "ICESTAR Quilicura", "comuna": "Quilicura", "lat": -33.3666, "lng": -70.7333, "rondas": 3 },
            { "id": 2, "nombre": "ICESTAR Aeroparque", "comuna": "Pudahuel", "lat": -33.4111, "lng": -70.7922, "rondas": 0 },
            { "id": 3, "nombre": "Megafrio-Renca", "comuna": "Renca", "lat": -33.4034, "lng": -70.7185, "rondas": 1 },
            { "id": 4, "nombre": "Bodegas San Francisco", "comuna": "Pudahuel", "lat": -33.4312, "lng": -70.8012, "rondas": 0 },
            { "id": 5, "nombre": "Centro Logístico Enea", "comuna": "Pudahuel", "lat": -33.4250, "lng": -70.7700, "rondas": 3 },
            { "id": 6, "nombre": "Planta Frigorífica Maipú", "comuna": "Maipú", "lat": -33.5100, "lng": -70.7500, "rondas": 2 },
            { "id": 7, "nombre": "Depósito San Bernardo", "comuna": "San Bernardo", "lat": -33.5900, "lng": -70.7000, "rondas": 1 },
            { "id": 8, "nombre": "Centro de Distribución Quilicura Norte", "comuna": "Quilicura", "lat": -33.3450, "lng": -70.7200, "rondas": 0 },
            { "id": 9, "nombre": "Instalación Conchalí Industrial", "comuna": "Conchalí", "lat": -33.3800, "lng": -70.6700, "rondas": 3 },
            { "id": 10, "nombre": "Bodegas Huechuraba", "comuna": "Huechuraba", "lat": -33.3700, "lng": -70.6300, "rondas": 2 },
            { "id": 11, "nombre": "Parque Industrial Lampa", "comuna": "Lampa", "lat": -33.2800, "lng": -70.8800, "rondas": 1 },
            { "id": 12, "nombre": "Centro Operativo Colina", "comuna": "Colina", "lat": -33.2000, "lng": -70.6700, "rondas": 0 },
            { "id": 13, "nombre": "Depósito Lo Espejo", "comuna": "Lo Espejo", "lat": -33.5150, "lng": -70.6800, "rondas": 3 },
            { "id": 14, "nombre": "Planta Nos", "comuna": "San Bernardo", "lat": -33.6100, "lng": -70.7100, "rondas": 2 },
            { "id": 15, "nombre": "Bodegas Cerrillos", "comuna": "Cerrillos", "lat": -33.4900, "lng": -70.7000, "rondas": 1 },
            { "id": 16, "nombre": "Centro Quilicura Poniente", "comuna": "Quilicura", "lat": -33.3550, "lng": -70.7500, "rondas": 3 },
            { "id": 17, "nombre": "Instalación Pudahuel Sur", "comuna": "Pudahuel", "lat": -33.4500, "lng": -70.7800, "rondas": 0 },
            { "id": 18, "nombre": "Centro Renca Bodega 4", "comuna": "Renca", "lat": -33.3950, "lng": -70.7050, "rondas": 2 },
            { "id": 19, "nombre": "Depósito Estación Central", "comuna": "Estación Central", "lat": -33.4500, "lng": -70.6800, "rondas": 1 },
            { "id": 20, "nombre": "Planta Valle Grande", "comuna": "Lampa", "lat": -33.3100, "lng": -70.7400, "rondas": 3 }
        ]
        return jsonify(instalaciones_fijas), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Función para leer automáticamente los correos de Kizeo
def verificar_correos_kizeo():
    try:
        # Configura tus credenciales de correo o variables de entorno en Render
        mail_server = os.getenv('MAIL_SERVER', 'imap.gmail.com')
        mail_user = os.getenv('MAIL_USER')
        mail_password = os.getenv('MAIL_PASSWORD')

        if not mail_user or not mail_password:
            return  # Si no hay credenciales configuradas, omite la lectura automática

        mail = imaplib.IMAP4_SSL(mail_server)
        mail.login(mail_user, mail_password)
        mail.select('inbox')

        # Buscar correos no leídos provenientes o relacionados con Kizeo
        status, messages = mail.search(None, '(UNSEEN SUBJECT "Kizeo")')
        
        for num in messages[0].split():
            status, data = mail.fetch(num, '(RFC822)')
            for response_part in data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    asunto = msg['subject']
                    
                    # Extraer el cuerpo del mensaje
                    cuerpo = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                cuerpo = part.get_payload(decode=True).decode()
                    else:
                        cuerpo = msg.get_payload(decode=True).decode()

                    # Aquí procesamos el texto para identificar la instalación y actualizar la base de datos
                    print(f"Correo procesado automáticamente: {asunto}")

        mail.logout()
    except Exception as e:
        print(f"Error al verificar correos automáticos: {e}")

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "No se recibieron datos"}), 400

        # Dispara también la revisión automática de correo al recibir peticiones
        verificar_correos_kizeo()

        form_id = content.get('form_id')
        usuario = content.get('user', {}).get('login', 'Desconocido')
        fecha = content.get('update_time')
        
        nuevo_reporte = ReporteKizeo(
            form_id=str(form_id) if form_id else None,
            usuario=str(usuario),
            fecha_envio=str(fecha) if fecha else None,
            datos_json=json.dumps(content)
        )
        
        db.session.add(nuevo_reporte)
        db.session.commit()

        return jsonify({"status": "success", "message": "Reporte procesado y guardado en PostgreSQL"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)