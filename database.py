import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# URL de conexión a PostgreSQL (en Render o local usará la variable de entorno DATABASE_URL)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://usuario:password@localhost:5432/kizeo_rondas")

# Configuración del motor de la base de datos
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS DE LA BASE DE DATOS ---

class Guardia(Base):
    __tablename__ = "guardias"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    rut = Column(String(20), unique=True, index=True, nullable=False)
    
    # Relación con las rondas realizadas
    rondas = relationship("Ronda", back_populates="guardia")

class Ronda(Base):
    __tablename__ = "rondas"

    id = Column(Integer, primary_key=True, index=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    sucursal = Column(String(100), nullable=False) # Ej: ICESTAR Quilicura, Megafrio-Renca
    fecha_hora = Column(DateTime, default=datetime.utcnow)
    observaciones_generales = Column(Text, nullable=True)

    # Relaciones
    guardia = relationship("Guardia", back_populates="rondas")
    puntos = relationship("PuntoRevision", back_populates="ronda", cascade="all, delete-orphan")
    incidencias = relationship("Incidencia", back_populates="ronda", cascade="all, delete-orphan")

class PuntoRevision(Base):
    __tablename__ = "puntos_revision"

    id = Column(Integer, primary_key=True, index=True)
    ronda_id = Column(Integer, ForeignKey("rondas.id"), nullable=False)
    nombre_punto = Column(String(100), nullable=False) # Ej: "Bodega Principal", "Perímetro Sur"
    hora_escaneo = Column(DateTime, nullable=False)
    latitud = Column(Float, nullable=True)
    longitud = Column(Float, nullable=True)

    ronda = relationship("Ronda", back_populates="puntos")

class Incidencia(Base):
    __tablename__ = "incidencias"

    id = Column(Integer, primary_key=True, index=True)
    ronda_id = Column(Integer, ForeignKey("rondas.id"), nullable=False)
    descripcion = Column(Text, nullable=False)
    foto_url = Column(String(255), nullable=True) # Enlace a la foto si Kizeo la adjunta

    ronda = relationship("Ronda", back_populates="incidencias")

# Función para inicializar y crear las tablas en PostgreSQL
def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Conectando y creando tablas en PostgreSQL...")
    init_db()
    print("¡Tablas creadas exitosamente!")