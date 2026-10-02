"""Regressões da versão privada; nenhuma conta externa ou chave real utilizada."""
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from banco import identidade_pdf
from online import criar_app
from servidor import ROOT

USUARIO='admin-fixture'
SENHA='SenhaSINTETICA-fixture-2026'


class OnlineTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env={'ADMIN_USER':USUARIO,'ADMIN_PASSWORD':SENHA,'SECRET_KEY':secrets.token_hex(32),
                  'DATA_DIR':str(Path(self.tmp.name)/'dados')}
        self.a=criar_app(self.env);self.a.testing=True;self.c=self.a.test_client();self.core=self.a.extensions['banco']
    def tearDown(self):self.core.ia.encerrar();self.tmp.cleanup()
    def login(self,cliente=None):
        c=cliente or self.c
        html=c.get('/login',base_url='https://localhost').get_data(as_text=True)
        token=re.search(r'name="csrf" value="([^"]+)"',html).group(1)
        r=c.post('/login',base_url='https://localhost',data={'csrf':token,'usuario':USUARIO,'senha':SENHA})
        self.assertEqual(r.status_code,302)
        inicio=c.get('/api/inicio',base_url='https://localhost').get_json()
        return inicio['token']
    def post(self,rota,dados,token):
        return self.c.post(rota,base_url='https://localhost',json=dados,headers={'X-Local-Token':token,'Origin':'https://localhost'})
    def acervo(self):
        pdf=next((ROOT/'provas_entrada').glob('*.pdf'));sha=identidade_pdf(pdf)
        shutil.copyfile(pdf,self.core.fontes/(sha+'.pdf'))
        self.core.banco.registrar_prova({'id':sha,'arquivo':pdf.name},[{'id':'online1','numero':1,
            'enunciado_candidato':'No Microsoft Excel, identifique a funcao que soma os valores.',
            'alternativas_candidatas':dict(A='SOMA',B='MEDIA',C='MAXIMO',D='MINIMO')}])
        q=self.core.banco.questao('PDF-online1')
        return self.core.banco.salvar_questao(dict(q,revisao='apta',conferida=True,disciplina='Informática',
            assuntos=['Planilhas / Excel'],classificacao='revisada',status_gabarito='oficial',gabarito='A',fonte_gabarito='Fixture sintetica'))
    def test_sem_credenciais_nao_inicia(self):
        for campo in ['ADMIN_USER','ADMIN_PASSWORD','SECRET_KEY']:
            with self.subTest(campo=campo),self.assertRaises(ValueError):criar_app(dict(self.env,**{campo:''}))
    def test_railway_sem_volume_ou_pasta_fora_dele_recusado(self):
        with self.assertRaisesRegex(ValueError,'volume'):criar_app(dict(self.env,RAILWAY_ENVIRONMENT_ID='fixture'))
        with self.assertRaisesRegex(ValueError,'subpasta'):criar_app(dict(self.env,RAILWAY_VOLUME_MOUNT_PATH=self.env['DATA_DIR']))
    def test_anonimo_nao_le_banco_pdf_backup_ou_script(self):
        self.acervo()
        for rota in ['/api/inicio','/api/painel','/api/ia','/api/questoes','/api/exportar','/api/historico','/api/baixar-backup','/pdf/'+'c'*64+'.pdf']:
            with self.subTest(rota=rota):self.assertEqual(self.c.get(rota,base_url='https://localhost').status_code,401)
        self.assertEqual(self.c.get('/',base_url='https://localhost').location,'/login')
        self.assertEqual(self.c.get('/app.js',base_url='https://localhost').status_code,302)
        self.assertEqual(self.c.post('/api/configurar',json={'intervalo':10},base_url='https://localhost',headers={'X-Local-Token':self.core.token}).status_code,401)
    def test_health_railway_publico_sem_dados(self):
        r=self.c.get('/health',base_url='https://healthcheck.railway.app')
        self.assertEqual(r.status_code,200);self.assertEqual(r.json,{'ok':True})
    def test_host_nao_confiavel_recusado(self):
        self.assertEqual(self.c.get('/health',base_url='https://site-inventado.example').status_code,400)
    def test_login_exige_csrf_e_bloqueia_origem_externa(self):
        self.assertEqual(self.c.post('/login',data={'usuario':USUARIO,'senha':SENHA},base_url='https://localhost').status_code,403)
        html=self.c.get('/login',base_url='https://localhost').text
        token=re.search(r'name="csrf" value="([^"]+)"',html).group(1)
        r=self.c.post('/login',data={'csrf':token,'usuario':USUARIO,'senha':SENHA},base_url='https://localhost',headers={'Origin':'https://externo.example'})
        self.assertEqual(r.status_code,403)
    def test_senha_errada_e_limite_de_tentativas(self):
        html=self.c.get('/login',base_url='https://localhost').text
        token=re.search(r'name="csrf" value="([^"]+)"',html).group(1)
        for _ in range(5):
            self.assertEqual(self.c.post('/login',data={'csrf':token,'usuario':USUARIO,'senha':'senha errada'},base_url='https://localhost').status_code,401)
        self.assertEqual(self.c.post('/login',data={'csrf':token,'usuario':USUARIO,'senha':SENHA},base_url='https://localhost').status_code,429)
    def test_cookie_seguro_login_rotaciona_token_e_nao_expoe_segredos(self):
        token=self.login()
        self.assertNotEqual(token,self.core.token)
        r=self.c.get('/login',base_url='https://localhost')
        self.assertEqual(r.location,'/')
        cookie=self.c.get_cookie('banco_admin')
        self.assertTrue(cookie.secure);self.assertTrue(cookie.http_only);self.assertEqual(cookie.same_site,'Lax')
        r=self.c.get('/api/inicio',base_url='https://localhost')
        self.assertTrue(r.json['online']);self.assertEqual(r.json['usuario'],USUARIO)
        self.assertNotIn(SENHA,r.text);self.assertNotIn(self.env['SECRET_KEY'],r.text)
    def test_token_de_outro_navegador_nao_pode_escrever(self):
        um=self.login();outro=self.login(self.a.test_client())
        self.assertNotEqual(um,outro)
        self.assertEqual(self.post('/api/configurar',{'intervalo':10},outro).status_code,403)
        self.assertEqual(self.post('/api/configurar',{'intervalo':10},um).status_code,200)
    def test_operacoes_legacy_autenticadas_preservadas(self):
        q=self.acervo();token=self.login()
        r=self.post('/api/responder',{'id':q['id'],'escolha':'A','tentativa_id':'online-fixture'},token)
        self.assertEqual(r.status_code,200);self.assertTrue(r.json['tentativa']['correta'])
        r=self.post('/api/pessoal',{'id':q['id'],'anotacao':'Anotacao do teste','favorito':True},token)
        self.assertEqual(r.status_code,200)
        hist=self.c.get('/api/historico',base_url='https://localhost').json;self.assertEqual(len(hist),1)
        r=self.c.get('/api/exportar',base_url='https://localhost');self.assertEqual(r.status_code,200)
        self.assertEqual(r.json['questoes'][0]['gabarito'],'A')
        r=self.post('/api/backup',{},token);self.assertEqual(r.status_code,200)
        zipr=self.c.get('/api/baixar-backup?nome='+r.json['nome'],base_url='https://localhost')
        self.assertEqual(zipr.status_code,200);self.assertEqual(zipr.data[:2],b'PK')
        self.assertNotIn(SENHA.encode(),zipr.data)
        pdf=self.c.get('/pdf/'+q['prova_id']+'.pdf',base_url='https://localhost')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
    def test_upload_pdf_autenticado_e_json_invalido_recusado(self):
        token=self.login();data=b'%PDF-1.7\nFixture sintetica'
        r=self.c.post('/api/enviar-pdf?nome=fixture.pdf',data=data,base_url='https://localhost',headers={'X-Local-Token':token},content_type='application/pdf')
        self.assertEqual(r.status_code,200);self.assertEqual((self.core.entrada/'fixture.pdf').read_bytes(),data)
        self.assertEqual(self.post('/api/configurar',[],token).status_code,400)
        self.assertEqual(self.post('/api/configurar',{},'não-ascii').status_code,403)
    def test_logout_revoga_cookie_anterior(self):
        token=self.login();cookie=self.c.get_cookie('banco_admin').value
        self.assertEqual(self.post('/api/logout',{},token).status_code,200)
        self.assertEqual(self.c.get('/api/inicio',base_url='https://localhost').status_code,401)
        replay=self.a.test_client();replay.set_cookie('banco_admin',cookie)
        self.assertEqual(replay.get('/api/inicio',base_url='https://localhost').status_code,401)
    def test_dados_persistem_apos_reiniciar_aplicacao(self):
        self.acervo();self.core.banco.pessoal({'id':'PDF-online1','anotacao':'Persistiu'})
        outra=criar_app(self.env)
        try:self.assertEqual(outra.extensions['banco'].banco.questao('PDF-online1')['anotacao'],'Persistiu')
        finally:outra.extensions['banco'].ia.encerrar()
    def test_api_key_em_variable_nao_vai_para_disco_ou_resposta(self):
        key='chave-sintetica-do-teste'
        outra=criar_app(dict(self.env,BANCO_API_KEY=key,API_MODELO='claude-fixture'))
        try:
            core=outra.extensions['banco'];self.assertTrue(core.ia.api_config.publico()['pronta'])
            self.assertNotIn(key,json.dumps(core.ia.estado()))
            self.assertNotIn(key,core.ia.api_config.arquivo.read_text())
        finally:outra.extensions['banco'].ia.encerrar()
    def test_restauracao_no_inicio_preserva_backup_e_dados_anteriores(self):
        self.acervo();zip=self.core.backup()
        mount=Path(self.tmp.name)/'volume';mount.mkdir();shutil.copyfile(zip,mount/'backup_importar.zip')
        pasta=mount/'acervo';pasta.mkdir();(pasta/'marcador_anterior.txt').write_text('dados antigos')
        outra=criar_app(dict(self.env,DATA_DIR=str(pasta),RAILWAY_VOLUME_MOUNT_PATH=str(mount),RESTORE_ON_START='1'))
        try:
            self.assertEqual(outra.extensions['banco'].banco.questao('PDF-online1')['gabarito'],'A')
            self.assertFalse((mount/'backup_importar.zip').exists())
            self.assertTrue(list(mount.glob('backup_importado_*.zip')))
            self.assertTrue(list(mount.glob('dados_antes_restauracao_*/marcador_anterior.txt')))
        finally:outra.extensions['banco'].ia.encerrar()
    def test_backup_invalido_nao_substitui_acervo(self):
        mount=Path(self.tmp.name)/'volume';mount.mkdir();(mount/'backup_importar.zip').write_bytes(b'zip invalido')
        pasta=mount/'acervo';pasta.mkdir();(pasta/'marcador').write_text('preservado')
        with self.assertRaises(Exception):criar_app(dict(self.env,DATA_DIR=str(pasta),RAILWAY_VOLUME_MOUNT_PATH=str(mount),RESTORE_ON_START='1'))
        self.assertEqual((pasta/'marcador').read_text(),'preservado')
    def test_cabecalhos_e_estaticos(self):
        self.login()
        for rota in ['/','/app.js','/style.css','/login.js']:
            r=self.c.get(rota,base_url='https://localhost');self.assertEqual(r.status_code,200)
            self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
        self.assertEqual(self.c.get('/dados/banco.sqlite',base_url='https://localhost').status_code,404)


class ServidorRealTest(unittest.TestCase):
    def test_gunicorn_port_login_e_health(self):
        with tempfile.TemporaryDirectory() as td:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));porta=sock.getsockname()[1]
            env=dict(os.environ,PORT=str(porta),ADMIN_USER=USUARIO,ADMIN_PASSWORD=SENHA,
                     SECRET_KEY=secrets.token_hex(32),DATA_DIR=str(Path(td)/'dados'),COOKIE_SECURE='0')
            logfile=Path(td)/'gunicorn.log'
            with logfile.open('w') as log:
                p=subprocess.Popen([sys.executable,'-m','gunicorn','--config','gunicorn.conf.py','wsgi:app'],cwd=ROOT,env=env,stdout=log,stderr=log)
                try:
                    url=f'http://127.0.0.1:{porta}';prazo=time.monotonic()+15
                    while True:
                        try:
                            with urllib.request.urlopen(url+'/health',timeout=1) as r:self.assertEqual(json.load(r),{'ok':True})
                            break
                        except (OSError,urllib.error.URLError):
                            if p.poll() is not None or time.monotonic()>prazo:self.fail('Gunicorn não iniciou: '+logfile.read_text())
                            threading.Event().wait(.05)
                    cookies=http.cookiejar.CookieJar();cliente=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
                    with cliente.open(url+'/login') as r:html=r.read().decode()
                    token=re.search(r'name="csrf" value="([^"]+)"',html).group(1)
                    from urllib.parse import urlencode
                    with cliente.open(urllib.request.Request(url+'/login',data=urlencode({'csrf':token,'usuario':USUARIO,'senha':SENHA}).encode())) as r:self.assertIn('Banco de',r.read().decode())
                    with cliente.open(url+'/api/inicio') as r:inicio=json.load(r)
                    self.assertTrue(inicio['online'])
                    req=urllib.request.Request(url+'/api/configurar',data=b'{"intervalo":10}',headers={'Content-Type':'application/json','X-Local-Token':inicio['token']})
                    with cliente.open(req) as r:self.assertEqual(r.status,200)
                finally:
                    p.terminate()
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:p.kill();p.wait()


if __name__=='__main__':unittest.main()
