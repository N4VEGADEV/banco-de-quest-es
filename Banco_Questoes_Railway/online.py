"""Entrada WSGI privada para Railway. Uma conta de administrador, sem cadastro público."""
import io
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta, datetime
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, redirect, render_template, request, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from servidor import Aplicacao, ROOT, handler


def criar_app(ambiente=None):
    env=dict(os.environ if ambiente is None else ambiente)
    usuario=env.get('ADMIN_USER','').strip()
    senha=env.get('ADMIN_PASSWORD','')
    segredo=env.get('SECRET_KEY','')
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{3,80}',usuario):
        raise ValueError('Configure ADMIN_USER em Variables: 3 a 80 caracteres, sem espaços.')
    if not 12<=len(senha)<=200:
        raise ValueError('Configure ADMIN_PASSWORD em Variables com 12 a 200 caracteres.')
    if len(segredo)<32:
        raise ValueError('Configure SECRET_KEY em Variables com pelo menos 32 caracteres aleatórios.')
    mount=env.get('RAILWAY_VOLUME_MOUNT_PATH','')
    if env.get('RAILWAY_ENVIRONMENT_ID') and not mount:
        raise ValueError('Conecte um volume persistente ao serviço Railway, montado em /data.')
    pasta=Path(env.get('DATA_DIR') or str(Path(mount or '/data')/'acervo')).resolve()
    if mount and (pasta==Path(mount).resolve() or Path(mount).resolve() not in pasta.parents):
        raise ValueError('DATA_DIR deve ser uma subpasta do volume, por exemplo /data/acervo.')

    # A restauração acontece antes de abrir o banco, nunca com o site em uso.
    pendente=Path(mount or pasta.parent)/'backup_importar.zip'
    if env.get('RESTORE_ON_START')=='1' and pendente.is_file():
        from restaurar import restaurar
        restaurar(pendente,pasta)
        pendente.rename(pendente.with_name('backup_importado_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip'))
        print('Backup restaurado; dados anteriores preservados no volume.',flush=True)

    core=Aplicacao(pasta)
    if env.get('BANCO_API_KEY') or any(env.get(k) for k in ('API_PROTOCOLO','API_BASE_URL','API_MODELO')):
        c=core.ia.api_config.publico()
        for origem,destino in [('API_PROTOCOLO','protocolo'),('API_BASE_URL','base_url'),('API_MODELO','modelo')]:
            if env.get(origem):c[destino]=env[origem]
        c.update(chave=env.get('BANCO_API_KEY',''),guardar_chave=False)
        core.ia.configurar_api(c)

    app=Flask(__name__,static_folder=None,template_folder=str(ROOT/'templates'))
    hosts=['localhost','127.0.0.1','.up.railway.app','healthcheck.railway.app']
    hosts.extend(x.strip() for x in env.get('TRUSTED_HOSTS','').split(',') if x.strip())
    if env.get('RAILWAY_PUBLIC_DOMAIN'):hosts.append(env['RAILWAY_PUBLIC_DOMAIN'])
    app.config.update(SECRET_KEY=segredo,SESSION_COOKIE_NAME='banco_admin',
        SESSION_COOKIE_SECURE=env.get('COOKIE_SECURE','1')!='0',
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
        SESSION_REFRESH_EACH_REQUEST=False,PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=100*1024*1024,TRUSTED_HOSTS=hosts)
    app.extensions['banco']=core
    hash_senha=generate_password_hash(senha)
    instancia=secrets.token_hex(24)
    falhas=defaultdict(deque);limite_lock=threading.Lock()
    sessoes_ativas={};sessao_lock=threading.Lock()

    def autenticado():
        if session.get('admin')!=usuario or session.get('instancia')!=instancia:return False
        with sessao_lock:
            id=session.get('sid','')
            if sessoes_ativas.get(id,0)<=time.monotonic():
                sessoes_ativas.pop(id,None);return False
            return True

    def csrf():
        if not session.get('csrf'):session['csrf']=secrets.token_urlsafe(32)
        return session['csrf']

    def csrf_valido():
        esperado=session.get('csrf','')
        informado=request.headers.get('X-Local-Token','') or request.form.get('csrf','')
        if not esperado or not secrets.compare_digest(esperado.encode(),informado.encode()):return False
        origem=request.headers.get('Origin')
        if origem:
            try:u=urlsplit(origem)
            except ValueError:return False
            if u.netloc.lower()!=request.host.lower():return False
            if app.config['SESSION_COOKIE_SECURE'] and u.scheme!='https':return False
        return True

    @app.before_request
    def proteger():
        # O healthcheck só revela disponibilidade; nunca o banco ou credenciais.
        if request.path=='/health':return None
        if request.path in ('/login','/login.js','/style.css'):
            if request.path=='/login' and request.content_length and request.content_length>8192:
                return 'Formulário de entrada maior que o limite.',413
            if request.method=='POST' and not csrf_valido():
                return render_template('login.html',csrf=csrf(),erro='Sessão de entrada expirada. Tente novamente.'),403
            return None
        if not autenticado():
            if request.path.startswith(('/api/','/pdf/')):
                return jsonify(erro='Entre com sua conta de administrador.'),401
            return redirect('/login')
        if request.method not in ('GET','HEAD','OPTIONS'):
            if not csrf_valido():return jsonify(erro='Sessão expirada ou solicitação inválida. Atualize a página.'),403
            if request.path!='/api/enviar-pdf' and request.content_length and request.content_length>8*1024*1024:
                return jsonify(erro='Requisição maior que o limite de 8 MB.'),413
            if request.path.startswith('/api/') and request.path not in ('/api/enviar-pdf','/api/logout'):
                if not request.is_json or not isinstance(request.get_json(silent=True),dict):
                    return jsonify(erro='Envie um objeto JSON válido.'),400

    @app.after_request
    def cabecalhos(resposta):
        resposta.headers['Cache-Control']='no-store'
        resposta.headers['X-Content-Type-Options']='nosniff'
        resposta.headers['Referrer-Policy']='same-origin'
        resposta.headers['X-Frame-Options']='SAMEORIGIN'
        resposta.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'"
        if app.config['SESSION_COOKIE_SECURE']:resposta.headers['Strict-Transport-Security']='max-age=31536000'
        return resposta

    @app.get('/health')
    def health():return jsonify(ok=True)

    @app.route('/login',methods=['GET','POST'])
    def login():
        if request.method=='GET':
            if autenticado():return redirect('/')
            return render_template('login.html',csrf=csrf(),erro='')
        nome=request.form.get('usuario','');passada=request.form.get('senha','')
        endereco=request.remote_addr or 'desconhecido';agora=time.monotonic()
        with limite_lock:
            for key in list(falhas):
                while falhas[key] and agora-falhas[key][0]>300:falhas[key].popleft()
                if not falhas[key]:falhas.pop(key,None)
            if len(falhas[endereco])>=5 or sum(map(len,falhas.values()))>=30:
                return render_template('login.html',csrf=csrf(),erro='Muitas tentativas. Aguarde cinco minutos antes de tentar novamente.'),429
        valida=check_password_hash(hash_senha,passada) if len(passada)<=200 else False
        if not (secrets.compare_digest(nome.encode(),usuario.encode()) and valida):
            with limite_lock:falhas[endereco].append(agora)
            return render_template('login.html',csrf=csrf(),erro='Usuário ou senha inválidos.'),401
        with limite_lock:falhas.pop(endereco,None)
        session.clear();session.permanent=True
        sid=secrets.token_urlsafe(32)
        with sessao_lock:
            for id in list(sessoes_ativas):
                if sessoes_ativas[id]<=agora:sessoes_ativas.pop(id,None)
            if len(sessoes_ativas)>=100:sessoes_ativas.pop(min(sessoes_ativas,key=sessoes_ativas.get))
            sessoes_ativas[sid]=agora+8*3600
        session.update(admin=usuario,instancia=instancia,sid=sid,csrf=secrets.token_urlsafe(32))
        return redirect('/')

    @app.post('/api/logout')
    def logout():
        with sessao_lock:sessoes_ativas.pop(session.get('sid',''),None)
        session.clear();return jsonify(ok=True)

    @app.get('/login.js')
    def login_js():return Response((ROOT/'web'/'login.js').read_bytes(),mimetype='text/javascript')

    # Reaproveita as rotas e validações do banco local como funções internas.
    # Não abre http.server na internet: a camada pública é Flask + Gunicorn.
    base=handler(core)
    class Ponte(base):
        def __init__(self):
            self.path=request.full_path.removesuffix('?')
            self.headers=Message()
            for k,v in request.headers.items():
                if k.lower() not in ('host','x-local-token','content-length'):self.headers[k]=v
            self.headers['Host']='127.0.0.1:8767';self.headers['X-Local-Token']=core.token
            corpo=request.get_data(cache=False) if request.method=='POST' else b''
            self.headers['Content-Length']=str(len(corpo))
            self.rfile=io.BytesIO(corpo);self.wfile=io.BytesIO()
            self.server=SimpleNamespace(server_port=8767)
            self.status=200;self.resposta_headers=[]
        def log_message(self,*args):pass
        def send_response(self,status,message=None):self.status=status
        def send_header(self,k,v):self.resposta_headers.append((k,v))
        def end_headers(self):pass
        def _enviar(self,dados,*args,**kw):
            if self.path=='/api/inicio' and isinstance(dados,dict):
                dados=dict(dados,token=csrf(),online=True,usuario=usuario)
            return super()._enviar(dados,*args,**kw)

    @app.route('/',defaults={'caminho':''},methods=['GET','POST'])
    @app.route('/<path:caminho>',methods=['GET','POST'])
    def banco(caminho):
        if request.path.startswith('/api/instalar'):
            return jsonify(erro='Instalação de modelos locais não é oferecida nesta hospedagem.'),404
        ponte=Ponte()
        if request.method=='POST':ponte.do_POST()
        else:ponte.do_GET()
        return Response(ponte.wfile.getvalue(),status=ponte.status,headers=ponte.resposta_headers)

    @app.errorhandler(HTTPException)
    def erro_http(e):
        mensagem='Requisição inválida.' if e.code!=413 else 'Arquivo ou requisição maior que o limite aceito (100 MB).'
        if request.path.startswith('/api/'):return jsonify(erro=mensagem),e.code
        return mensagem,e.code

    return app
