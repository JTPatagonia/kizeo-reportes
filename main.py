import os
import json
from flask import Flask, request, jsonify
from database import db, ReporteKizeo

app = Flask(__name__)

# Configuración de la base de datos PostgreSQL usando la URL de Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar la base de datos con la app
db.init_app(app)

# Crear las tablas automáticamente en PostgreSQL al iniciar
with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return jsonify({"message": "API de Rondas Kizeo con Flask funcionando correctamente 🚀"})

@app.route('/api/webhook', methods=['POST'])
def recibir_webhook():
    try:
        content = request.json
        if not content:
            return jsonify({"error": "No se recibieron datos"}), 400

        # Extraer campos básicos del JSON enviado por Kizeo Forms
        form_id = content.get('form_id')
        usuario = content.get('user', {}).get('login', 'Desconocido')
        fecha = content.get('update_time')
        
        # Guardar el registro completo en la base de datos PostgreSQL
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