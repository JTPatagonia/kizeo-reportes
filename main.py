from fastapi import FastAPI, Request, Depends, status, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from database import SessionLocal, init_db, Guardia, Ronda, PuntoRevision, Incidencia

app = FastAPI(title="Kizeo Rondas Webhook", version="1.0")

# Dependencia para obtener la sesión de base de datos en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
def startup_event():
    # Asegura que las tablas existan al iniciar el servidor
    init_db()

@app.post("/webhook/kizeo")
async def recibir_webhook_kizeo(request: Request, db: Session = Depends(get_db)):
    try:
        # Recibimos el JSON enviado por Kizeo Forms
        payload = await request.json()
        
        # Nota: Dependiendo de cómo configures tu formulario en Kizeo,
        # aquí mapearemos las llaves del JSON que llegan en 'payload'.
        # Este es un esquema base de ejemplo:
        
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
        
        # 3. Procesar puntos de marcación / revisión (si vienen en una lista en el JSON)
        puntos_enviados = payload.get("puntos", [])
        for p in puntos_enviados:
            punto = PuntoRevision(
                ronda_id=nueva_ronda.id,
                nombre_punto=p.get("nombre", "Punto sin nombre"),
                hora_escaneo=datetime.utcnow(), # o parsear la fecha de Kizeo
                latitud=p.get("lat"),
                longitud=p.get("lon")
            )
            db.add(punto)
            
        # 4. Registrar incidencias si las hay
        incidencias_enviadas = payload.get("incidencias", [])
        for inc in incidencias_enviadas:
            incidencia = Incidencia(
                ronda_id=nueva_ronda.id,
                descripcion=inc.get("descripcion", ""),
                foto_url=inc.get("foto_url")
            )
            db.add(incidencia)
            
        db.commit()
        
        return {"status": "success", "message": "Ronda procesada y guardada correctamente", "ronda_id": nueva_ronda.id}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/")
def home():
    return {"message": "API de Rondas Kizeo funcionando correctamente 🚀"}