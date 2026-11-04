from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ReporteKizeo(db.Model):
    __tablename__ = 'reportes_kizeo'
    
    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.String(100), nullable=True)
    usuario = db.Column(db.String(150), nullable=True)
    fecha_envio = db.Column(db.String(100), nullable=True)
    datos_json = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<ReporteKizeo {self.id} - {self.usuario}>'