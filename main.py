from flask import Flask, request, jsonify
import os
from datetime import datetime
from database import SessionLocal, init_db, Guardia, Ronda, PuntoRevision, Incidencia

app = Flask(__name__)

# Inicializar base de datos al arrancar
with app.app_context():
    init_db()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "API de Rondas Kizeo con Flask funcionando correctamente 🚀"})

@app.route("/webhook/kizeo", methods=["POST"])
def recibir_webhook_kizeo():
    db = SessionLocal()
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "No JSON payload provided"}), 400
        
        rut_guardia = payload.get("rut_guardia")
        nombre_guardia = payload.get("nombre_guardia", "Guardia Desconocido")
        sucursal = payload.get("sucursal", "Sucursal General")
        observaciones = payload.get("observaciones", "")
        
        # 1. Buscar o crear al guardia
        guardia = db.query(Guardia).filter(Guardia.rut == rut_guardia).first()
        if not guardia:
            guardia = Guardia(nombre=nombre_guardia, rut=rut_guardia)
            db.add(guardia)
            db.commit()
            db.refresh(guardia)
            
        # 2. Registrar la ronda principal
        nueva_ronda = Ronda(
            guardia_id=guardia.id,
            sucursal=sucursal,
            fecha_hora=datetime.utcnow(),
            observaciones_generales=observaciones
        )
        db.add(nueva_ronda)
        db.commit()
        db.refresh(nueva_ronda)
        
        # 3. Procesar puntos de marcación
        for p in payload.get("puntos", []):
            punto = PuntoRevision(
                ronda_id=nueva_ronda.id,
                nombre_punto=p.get("nombre", "Punto sin nombre"),
                hora_escaneo=datetime.utcnow(),
                latitud=p.get("lat"),
                longitud=p.get("lon")
            )
            db.add(punto)
            
        # 4. Registrar incidencias
        for inc in payload.get("incidencias", []):
            incidencia = Incidencia(
                ronda_id=nueva_ronda.id,
                descripcion=inc.get("descripcion", ""),
                foto_url=inc.get("foto_url")
            )
            db.add(incidencia)
            
        db.commit()
        return jsonify({"status": "success", "message": "Ronda procesada correctamente", "ronda_id": nueva_ronda.id}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        db.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))