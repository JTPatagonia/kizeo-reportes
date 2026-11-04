import os
import json
from flask import Flask, request, jsonify
from database import db, ReporteKizeo

app = Flask(__name__)

# Forzar el uso del driver psycopg2 para evitar que busque el módulo psycopg v3
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
    return jsonify({"message": "API de Rondas Kizeo con Flask funcionando correctamente 🚀"})

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "No se recibieron datos"}), 400

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

        return jsonify({"status": "success", "message": "Reporte guardado correctamente en PostgreSQL"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)