from flask import Flask, jsonify, request
from flask_cors import CORS  # Importante para permitir conexión con el HTML

app = Flask(__name__)
CORS(app)  # Habilita CORS para que tu página web pueda consultar la API

# Base de datos simulada en memoria (puedes conectarla a tu PostgreSQL real con SQLAlchemy o psycopg2)
instalaciones_db = [
    { "id": 1, "nombre": "ICESTAR Quilicura", "comuna": "Quilicura", "lat": -33.3666, "lng": -70.7333, "rondas": 3 },
    { "id": 2, "nombre": "ICESTAR Aeroparque", "comuna": "Pudahuel", "lat": -33.4111, "lng": -70.7922, "rondas": 0 },
    { "id": 3, "nombre": "Megafrio-Renca", "comuna": "Renca", "lat": -33.4034, "lng": -70.7185, "rondas": 1 },
    # ... puedes agregar el resto de tus 20 instalaciones aquí o traerlas desde PostgreSQL
]

# Ruta que consulta la central 24/7 en tiempo real
@app.route('/api/estado-instalaciones', methods=['GET'])
def obtener_estado():
    return jsonify(instalaciones_db)

# Ruta Webhook que recibe los datos cuando Kizeo Forms procesa una ronda
@app.route('/api/webhook', methods=['POST'])
def webhook_kizeo():
    data = request.json
    if not data:
        return jsonify({"error": "Sin datos"}), 400

    # Aquí extraes el nombre de la instalación y las rondas enviadas por Kizeo
    nombre_inst = data.get("instalacion")
    nuevas_rondas = data.get("rondas")

    # Actualizamos el registro en la base de datos
    for inst in instalaciones_db:
        if inst["nombre"].lower() == nombre_inst.lower():
            inst["rondas"] = int(nuevas_rondas)
            return jsonify({"status": "success", "mensaje": f"Actualizado {nombre_inst} a {nuevas_rondas} rondas"}), 200

    return jsonify({"error": "Instalación no encontrada"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)