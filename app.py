import os, re, io, unicodedata
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func
import pandas as pd

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'cambiar-esta-clave')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db').replace('postgres://','postgresql://',1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

def norm(v):
    if v is None: return ''
    s = str(v).strip()
    return '' if s.lower() in ('nan','none','null') else s

def normkey(v):
    s = unicodedata.normalize('NFKD', norm(v)).encode('ascii','ignore').decode()
    return re.sub(r'[^a-z0-9]+','',s.lower())

def clean_dni(v):
    s = re.sub(r'\D','', norm(v))
    return s or None

def normalize_col(c):
    c = unicodedata.normalize('NFKD', str(c)).encode('ascii','ignore').decode().upper().strip()
    c = re.sub(r'[^A-Z0-9]+','_',c).strip('_')
    aliases = {
        'NOMBRES_Y_APELLIDOS':'NOMBRES_APELLIDOS','NOMBRE_Y_APELLIDO':'NOMBRES_APELLIDOS',
        'NOMBRES':'NOMBRES_APELLIDOS','APELLIDOS_Y_NOMBRES':'NOMBRES_APELLIDOS',
        'MAIL':'CORREO','EMAIL':'CORREO','E_MAIL':'CORREO','TELEFONO':'CELULAR','MOVIL':'CELULAR',
        'NUMERO_CELULAR':'CELULAR','GRUPO':'GRUPO_PARLAMENTARIO','BANCADA':'GRUPO_PARLAMENTARIO',
        'ID':'ID_INTERNO','CODIGO':'ID_INTERNO','CODIGO_INTERNO':'ID_INTERNO','DEPARTAMENTO':'REGION'
    }
    return aliases.get(c,c)

class Participant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    id_interno = db.Column(db.String(100), index=True)
    region = db.Column(db.String(100), index=True, nullable=False)
    dni = db.Column(db.String(20), index=True)
    nombres_apellidos = db.Column(db.String(250), nullable=False)
    correo = db.Column(db.String(250), index=True)
    celular = db.Column(db.String(50), index=True)
    camara = db.Column(db.String(50), index=True)
    grupo_parlamentario = db.Column(db.String(150))
    observacion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    region = db.Column(db.String(100), index=True, nullable=False)
    abierta = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('participant.id'), nullable=False, index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_session.id'), nullable=False, index=True)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)
    participant = db.relationship('Participant')
    attendance_session = db.relationship('AttendanceSession')
    __table_args__ = (db.UniqueConstraint('participant_id','session_id', name='uq_attendance'),)

with app.app_context(): db.create_all()

def is_admin(): return session.get('admin') is True

@app.route('/')
def home():
    active = AttendanceSession.query.filter_by(abierta=True).order_by(AttendanceSession.id.desc()).all()
    return render_template('home.html', active=active)

@app.route('/marcar/<int:session_id>', methods=['GET','POST'])
def marcar(session_id):
    ses = AttendanceSession.query.get_or_404(session_id)
    if not ses.abierta:
        return render_template('message.html', title='Asistencia cerrada', message='La asistencia de esta sesión ya está cerrada.')
    if request.method == 'POST':
        q = norm(request.form.get('identificador'))
        qdni = clean_dni(q)
        filters=[]
        if qdni: filters.append(Participant.dni == qdni)
        if q: filters += [func.lower(Participant.correo)==q.lower(), Participant.celular==re.sub(r'\D','',q)]
        candidates = Participant.query.filter_by(region=ses.region, activo=True).filter(or_(*filters)).all() if filters else []
        if not candidates:
            flash('No encontramos ese DNI, correo o celular en la lista de esta región.')
            return redirect(url_for('marcar', session_id=session_id))
        p = candidates[0]
        if Attendance.query.filter_by(participant_id=p.id, session_id=ses.id).first():
            return render_template('message.html', title='Asistencia ya registrada', message=f'{p.nombres_apellidos}, tu asistencia ya fue registrada.')
        db.session.add(Attendance(participant_id=p.id, session_id=ses.id)); db.session.commit()
        return render_template('message.html', title='Asistencia registrada', message=f'Gracias, {p.nombres_apellidos}. Tu asistencia fue registrada correctamente.')
    return render_template('mark.html', ses=ses)

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password','') == ADMIN_PASSWORD:
            session['admin']=True; return redirect(url_for('admin'))
        flash('Contraseña incorrecta.')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout(): session.clear(); return redirect(url_for('admin_login'))

@app.route('/admin')
def admin():
    if not is_admin(): return redirect(url_for('admin_login'))
    region = request.args.get('region','').strip(); sid = request.args.get('session_id', type=int)
    regions=[r[0] for r in db.session.query(Participant.region).distinct().order_by(Participant.region).all() if r[0]]
    sessions=AttendanceSession.query.order_by(AttendanceSession.id.desc()).all()
    q=Participant.query
    if region: q=q.filter_by(region=region)
    participants=q.order_by(Participant.region, Participant.nombres_apellidos).all()
    if not sid and sessions: sid=sessions[0].id
    attendance_ids={x.participant_id for x in Attendance.query.filter_by(session_id=sid).all()} if sid else set()
    total=len(participants); present=sum(p.id in attendance_ids for p in participants)
    return render_template('admin.html', regions=regions, sessions=sessions, participants=participants,
        region=region, session_id=sid, attendance_ids=attendance_ids, total=total, present=present,
        complete_dni=sum(bool(p.dni) for p in participants), complete_email=sum(bool(p.correo) for p in participants))

@app.route('/admin/upload', methods=['POST'])
def upload():
    if not is_admin(): return redirect(url_for('admin_login'))
    f=request.files.get('file')
    if not f or not f.filename: flash('Selecciona un Excel o CSV.'); return redirect(url_for('admin'))
    try:
        if f.filename.lower().endswith(('.xlsx','.xls')): df=pd.read_excel(f)
        else:
            raw=f.read(); txt=raw.decode('utf-8-sig', errors='replace'); sep=';' if txt.count(';')>txt.count(',') else ','; df=pd.read_csv(io.StringIO(txt), sep=sep)
        df.columns=[normalize_col(c) for c in df.columns]
        if not {'REGION','NOMBRES_APELLIDOS'}.issubset(df.columns):
            flash('El archivo debe incluir al menos REGION y NOMBRES_APELLIDOS.'); return redirect(url_for('admin'))
        created=updated=skipped=0
        for _,row in df.iterrows():
            data={c:norm(row.get(c,'')) for c in df.columns}; region=data.get('REGION',''); name=data.get('NOMBRES_APELLIDOS','')
            if not region or not name: skipped+=1; continue
            dni=clean_dni(data.get('DNI')); correo=data.get('CORREO','').lower() or None; celular=re.sub(r'\D','',data.get('CELULAR','')) or None; idint=data.get('ID_INTERNO','') or None
            p=None
            if idint: p=Participant.query.filter_by(id_interno=idint).first()
            if not p and dni: p=Participant.query.filter_by(dni=dni).first()
            if not p and correo: p=Participant.query.filter(func.lower(Participant.correo)==correo).first()
            if not p and celular: p=Participant.query.filter_by(celular=celular).first()
            if not p:
                nk=normkey(name)
                p=next((c for c in Participant.query.filter_by(region=region).all() if normkey(c.nombres_apellidos)==nk), None)
            fields={'id_interno':idint,'region':region,'dni':dni,'nombres_apellidos':name,'correo':correo,'celular':celular,
                    'camara':data.get('CAMARA','') or None,'grupo_parlamentario':data.get('GRUPO_PARLAMENTARIO','') or None,
                    'observacion':data.get('OBSERVACION','') or None}
            if p:
                for k,v in fields.items():
                    if v not in (None,''): setattr(p,k,v)
                updated+=1
            else: db.session.add(Participant(**fields, activo=True)); created+=1
        db.session.commit(); flash(f'Importación completada: {created} nuevos, {updated} actualizados, {skipped} omitidos. Las asistencias existentes NO fueron borradas.')
    except Exception as e:
        db.session.rollback(); flash('Error al importar: '+str(e))
    return redirect(url_for('admin'))

@app.route('/admin/session/create', methods=['POST'])
def session_create():
    if not is_admin(): return redirect(url_for('admin_login'))
    titulo=norm(request.form.get('titulo')); region=norm(request.form.get('region'))
    if titulo and region:
        db.session.add(AttendanceSession(titulo=titulo, region=region, abierta=False)); db.session.commit(); flash('Sesión creada.')
    else: flash('Completa título y región.')
    return redirect(url_for('admin', region=region))

@app.route('/admin/session/<int:sid>/toggle', methods=['POST'])
def session_toggle(sid):
    if not is_admin(): return redirect(url_for('admin_login'))
    s=AttendanceSession.query.get_or_404(sid); s.abierta=not s.abierta; db.session.commit(); flash('Asistencia abierta.' if s.abierta else 'Asistencia cerrada.')
    return redirect(url_for('admin', region=s.region, session_id=s.id))

@app.route('/admin/attendance/<int:sid>/<int:pid>/delete', methods=['POST'])
def delete_attendance(sid,pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    a=Attendance.query.filter_by(session_id=sid, participant_id=pid).first()
    if a: db.session.delete(a); db.session.commit(); flash('Marca de asistencia eliminada.')
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/attendance/<int:sid>/reset', methods=['POST'])
def reset_attendance(sid):
    if not is_admin(): return redirect(url_for('admin_login'))
    s=AttendanceSession.query.get_or_404(sid); Attendance.query.filter_by(session_id=sid).delete(); db.session.commit(); flash(f'Asistencia reiniciada para: {s.titulo}.')
    return redirect(url_for('admin', region=s.region, session_id=sid))

@app.route('/admin/participant/<int:pid>/toggle', methods=['POST'])
def participant_toggle(pid):
    if not is_admin(): return redirect(url_for('admin_login'))
    p=Participant.query.get_or_404(pid); p.activo=not p.activo; db.session.commit(); flash('Participante actualizado.')
    return redirect(request.referrer or url_for('admin'))

@app.route('/admin/export/<int:sid>')
def export_attendance(sid):
    if not is_admin(): return redirect(url_for('admin_login'))
    s=AttendanceSession.query.get_or_404(sid); rows=[]
    for p in Participant.query.filter_by(region=s.region).order_by(Participant.nombres_apellidos).all():
        a=Attendance.query.filter_by(session_id=sid, participant_id=p.id).first()
        rows.append({'REGION':p.region,'DNI':p.dni or '','NOMBRES_APELLIDOS':p.nombres_apellidos,'CORREO':p.correo or '',
        'CELULAR':p.celular or '','CAMARA':p.camara or '','GRUPO_PARLAMENTARIO':p.grupo_parlamentario or '',
        'ASISTENCIA':'SI' if a else 'NO','FECHA_HORA':a.marked_at.strftime('%Y-%m-%d %H:%M:%S') if a else ''})
    out=io.BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as w: pd.DataFrame(rows).to_excel(w,index=False,sheet_name='Asistencia')
    out.seek(0); return send_file(out, as_attachment=True, download_name=f'asistencia_{s.region}_{s.id}.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__=='__main__': app.run(host='0.0.0.0', port=int(os.getenv('PORT','5000')))
