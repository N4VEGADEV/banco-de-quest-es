"""Integração exercitada com servidor HTTP simulado; nenhuma chave ou cobrança real."""
import base64
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from api_claude import ConfigAPI, ClienteClaude, ClassificadorAPI, ErroAPI, PADRAO, validar_config
from ia_comum import assinatura, pendente
from servidor import Aplicacao, handler

CHAVE='credencial-sintetica-para-testes-v13'
MODELO='claude-modelo-simulado'
CATALOGO={'Informática':['Hardware','Planilhas / Excel'],
          'Língua Portuguesa':['Semântica / Figuras de linguagem']}


def questao():
    return {'enunciado':'No Microsoft Excel, identifique a função que soma os valores.',
            'contexto':'Considere os valores da tabela.',
            'alternativas':{'A':'SOMA','B':'MÉDIA','C':'MÁXIMO','D':'MÍNIMO'},
            'revisao':'pendente','classificacao':'pendente'}


class ClienteFalso:
    config=dict(PADRAO,modelo=MODELO)
    def __init__(self):self.chamadas=[];self.retorno=None
    def classificar(self,prompt,schema):
        self.chamadas.append(json.loads(prompt))
        return self.retorno,{'entrada':100,'saida':25},MODELO


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.c=ConfigAPI(self.tmp.name)
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def test_chave_somente_na_sessao(self):
        p=self.c.salvar(dict(PADRAO,modelo=MODELO,chave=CHAVE))
        self.assertTrue(p['pronta']);self.assertNotIn(CHAVE,json.dumps(p))
        self.assertNotIn(CHAVE,self.c.arquivo.read_text())
        self.assertEqual(self.c.cliente().chave,CHAVE)
        self.assertFalse(ConfigAPI(self.tmp.name).publico()['chave_configurada'])
    def test_preservar_e_remover_chave(self):
        self.c.salvar(dict(PADRAO,modelo=MODELO,chave=CHAVE))
        self.c.salvar(dict(PADRAO,modelo='outro-modelo'))
        self.assertEqual(self.c.cliente().chave,CHAVE)
        self.c.salvar(dict(PADRAO,apagar_chave=True))
        with self.assertRaises(ValueError):self.c.cliente()
    def test_guardar_protegida_e_reabrir_com_dpapi_simulada(self):
        with patch('api_claude._dpapi',side_effect=lambda b,proteger=True:b'protegida' if proteger else CHAVE.encode()):
            self.c.salvar(dict(PADRAO,modelo=MODELO,chave=CHAVE,guardar_chave=True))
            raw=json.loads(self.c.arquivo.read_text())
            self.assertEqual(base64.b64decode(raw['chave_dpapi']),b'protegida')
            self.assertNotIn(CHAVE,self.c.arquivo.read_text())
            outra=ConfigAPI(self.tmp.name)
            self.assertEqual(outra.cliente().chave,CHAVE)
            self.assertNotIn('chave_dpapi',outra.publico())
    def test_nao_envia_chave_anterior_ao_mudar_fornecedor(self):
        self.c.salvar(dict(PADRAO,modelo=MODELO,chave=CHAVE))
        with self.assertRaisesRegex(ValueError,'fornecedor'):
            self.c.salvar(dict(PADRAO,base_url='https://outro.example',modelo=MODELO))
        self.assertEqual(self.c.publico()['base_url'],PADRAO['base_url'])
    def test_variavel_ambiente_limitada_a_api_oficial(self):
        with patch.dict(os.environ,ANTHROPIC_API_KEY=CHAVE):
            self.assertEqual(self.c.cliente().chave,CHAVE)
            self.c.salvar(dict(PADRAO,base_url='https://outro.example',apagar_chave=True))
            self.assertFalse(self.c.publico()['chave_configurada'])
    def test_config_corrompida_e_urls_invalidas(self):
        self.c.arquivo.write_text('[]');self.assertEqual(ConfigAPI(self.tmp.name).config,PADRAO)
        for url in ['http://fornecedor.example','https://usuario:chave@api.example',
                    'https://api.example?key=segredo','https://api.example/v1/messages',
                    'https://api.example/v1/chat/completions','https://api.example:abc']:
            with self.subTest(url=url),self.assertRaises(ValueError):validar_config(dict(PADRAO,base_url=url))
        self.assertEqual(validar_config(dict(PADRAO,base_url='http://127.0.0.1:8099/v1/'))['base_url'],'http://127.0.0.1:8099/v1')
    def test_chave_invalida_no_ambiente_nao_vaza_na_mensagem(self):
        with patch.dict(os.environ,ANTHROPIC_API_KEY=CHAVE+'\nconteúdo'):
            with self.assertRaises(ErroAPI) as cm:self.c.cliente()
            self.assertNotIn(CHAVE,str(cm.exception))


class ClassificacaoTest(unittest.TestCase):
    def setUp(self):
        self.c=ClienteFalso();self.m=ClassificadorAPI(self.c,CATALOGO)
        self.id=next(i for i,par in self.m.catalogo.items() if par==('Informática','Planilhas / Excel'))
        self.c.retorno={'estado':'classificada','ids_assuntos':[self.id],'confianca':'alta',
                       'justificativa':'A questão cobra uma função de planilha.','evidencia':'Microsoft Excel'}
    def test_aplica_catalogo_e_exclui_dados_pessoais(self):
        q=dict(questao(),gabarito='A',anotacao='MINHA NOTA PRIVADA',historico=[1],explicacao='Comentário privado',id='ID-PRIVADO')
        r=self.m.classificar(q)
        self.assertEqual(r['estado'],'automatica');self.assertEqual(r['assuntos'],['Planilhas / Excel'])
        enviado=self.c.chamadas[0]['questao']
        self.assertEqual(set(enviado),{'enunciado','contexto','alternativas'})
        self.assertNotIn('PRIVAD',json.dumps(self.c.chamadas))
    def test_assunto_desconhecido_mistura_e_campos_extras_recusados(self):
        pt=next(i for i,par in self.m.catalogo.items() if par[0]=='Língua Portuguesa')
        for dados in [{'ids_assuntos':['INVENTADO']},{'ids_assuntos':[self.id,pt]},
                      {'gabarito':'A'},{'ids_assuntos':[]},{'estado':'outro'}]:
            with self.subTest(dados=dados):
                original=dict(self.c.retorno);self.c.retorno.update(dados)
                r=self.m.classificar(questao());self.c.retorno=original
                self.assertEqual(r['codigo_motivo'],'api_resposta_invalida');self.assertEqual(r['assuntos'],[])
    def test_confianca_baixa_ou_evidencia_ausente_ficam_para_revisao(self):
        for campo,valor in [('confianca','baixa'),('evidencia','palavra que não está na questão')]:
            with self.subTest(campo=campo):
                original=dict(self.c.retorno);self.c.retorno[campo]=valor
                self.assertEqual(self.m.classificar(questao())['estado'],'revisar');self.c.retorno=original
    def test_fora_catalogo_nao_forca_categoria(self):
        self.c.retorno.update(estado='fora_catalogo',ids_assuntos=[],evidencia='')
        r=self.m.classificar(questao())
        self.assertEqual(r['estado'],'fora_catalogo');self.assertEqual(r['assuntos'],[])
    def test_incompleta_e_extensa_nao_gastam_api(self):
        self.assertEqual(self.m.classificar(dict(questao(),enunciado=''))['estado'],'incompleta')
        self.assertEqual(self.m.classificar(dict(questao(),contexto='a'*61000))['codigo_motivo'],'texto_extenso')
        self.assertEqual(self.c.chamadas,[]);self.assertEqual(self.m.requisicoes,0)
    def test_sugestao_sem_assunto_e_resposta_invalida(self):
        self.c.retorno.update(estado='revisar',ids_assuntos=[],evidencia='')
        self.assertEqual(self.m.classificar(questao())['estado'],'revisar')
        self.c.retorno=None
        self.assertEqual(self.m.classificar(questao())['codigo_motivo'],'api_resposta_invalida')
    def test_retomada_mesma_questao_e_modelo(self):
        q=questao();q.update(analise_ia=self.m.classificar(q),classificacao='automatica')
        self.assertFalse(self.m.pendente(q));self.assertFalse(pendente(q,'hibrido'))
        q['enunciado']+=' Verifique também a operação.';self.assertTrue(self.m.pendente(q))
        q['classificacao']='revisada';self.assertFalse(self.m.pendente(q,True))
    def test_alterar_catalogo_permite_nova_analise(self):
        q=questao();q['analise_ia']=self.m.classificar(q)
        outro=ClassificadorAPI(self.c,dict(CATALOGO,Geografia=['Cartografia']))
        self.assertTrue(outro.pendente(q))


class Fornecedor(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def enviar(self,dados,status=200):
        raw=json.dumps(dados).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.server.chamadas.append((self.path,dict(self.headers),None))
        self.enviar({'data':[{'id':MODELO,'display_name':'Claude simulado'}],'has_more':False})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.chamadas.append((self.path,dict(self.headers),body))
        acao=self.server.acoes.pop(0) if self.server.acoes else 'ok'
        if acao=='aguardar':self.server.entrou.set();self.server.liberar.wait(5)
        if acao=='429':return self.enviar({'error':{'message':'ERRO COM CHAVE '+CHAVE}},429)
        if acao=='redirect':
            self.send_response(302);self.send_header('Location','/captura');self.send_header('Content-Length','0');self.end_headers();return
        prompt=json.loads(body['messages'][-1]['content'])
        id=next(x['id'] for x in prompt['catalogo'] if 'Excel' in x['assunto'])
        saida={'estado':'classificada','ids_assuntos':[id],'confianca':'alta',
               'justificativa':'A função pedida é uma operação de planilha.','evidencia':'Microsoft Excel'}
        if self.path.endswith('/chat/completions'):
            dados={'choices':[{'finish_reason':'stop','message':{'content':'```json\n'+json.dumps(saida)+'\n```'}}],
                   'model':MODELO,'usage':{'prompt_tokens':120,'completion_tokens':45}}
        else:
            dados={'content':[{'type':'tool_use','name':'registrar_classificacao','input':saida}],
                   'stop_reason':'tool_use','model':MODELO,'usage':{'input_tokens':120,'output_tokens':45}}
        if acao=='invalida':dados['content']=None;dados['choices']=None;dados['usage']='inválido'
        if acao=='truncada':dados['stop_reason']='max_tokens'
        self.enviar(dados)


class TransporteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=ThreadingHTTPServer(('127.0.0.1',0),Fornecedor)
        cls.s.chamadas=[];cls.s.acoes=[];cls.s.entrou=threading.Event();cls.s.liberar=threading.Event()
        cls.t=threading.Thread(target=cls.s.serve_forever,daemon=True);cls.t.start()
        cls.url=f'http://127.0.0.1:{cls.s.server_port}'
    @classmethod
    def tearDownClass(cls):cls.s.shutdown();cls.s.server_close();cls.t.join()
    def setUp(self):
        self.s.chamadas.clear();self.s.acoes.clear();self.s.entrou.clear();self.s.liberar.clear()
        self.tmp=tempfile.TemporaryDirectory();self.app=Aplicacao(Path(self.tmp.name)/'dados')
        self.config=dict(PADRAO,base_url=self.url,modelo=MODELO,chave=CHAVE)
        self.app.ia.configurar_api(self.config)
    def tearDown(self):
        self.s.liberar.set();self.app.ia.encerrar();self.esperar();self.tmp.cleanup()
    def motor(self,protocolo='anthropic'):
        return ClassificadorAPI(ClienteClaude(dict(self.config,protocolo=protocolo,base_url=self.url+'/v1'),CHAVE),CATALOGO)
    def esperar(self):
        prazo=time.monotonic()+10
        while self.app.ia.job['ativo'] and time.monotonic()<prazo:threading.Event().wait(.02)
        self.assertFalse(self.app.ia.job['ativo'],'Lote não encerrou no teste')
    def acervo(self):
        qs=[dict(id=f'{n:02d}',numero=n,enunciado_candidato=questao()['enunciado'],
                 alternativas_candidatas=questao()['alternativas']) for n in range(1,6)]
        self.app.banco.registrar_prova({'id':'c'*64,'arquivo':'fixture.pdf'},qs)
        q=self.app.banco.questao('PDF-03')
        self.app.banco.salvar_questao(dict(q,disciplina='Informática',assuntos=['Hardware'],classificacao='revisada'))
        q=self.app.banco.questao('PDF-04');self.app.banco.salvar_questao(dict(q,revisao='retida'))
        q=self.app.banco.questao('PDF-05')
        self.app.banco.salvar_questao(dict(q,disciplina='Informática',assuntos=['Hardware'],classificacao='automatica'))
    def iniciar(self,**kw):
        return self.app.ia.iniciar(dict(modo='api',threads=2,limite=25,**kw))
    def test_autenticacao_lista_modelos_sem_enviar_questoes(self):
        r=self.app.ia.testar_api();self.assertEqual(r['modelos'][0]['id'],MODELO)
        path,h,body=self.s.chamadas[0]
        self.assertEqual(path,'/v1/models');self.assertEqual(h['X-Api-Key'],CHAVE)
        self.assertEqual(h['Anthropic-Version'],'2023-06-01');self.assertIsNone(body)
    def test_native_tool_choice_e_payload(self):
        r=self.motor().classificar(questao());self.assertEqual(r['estado'],'automatica')
        path,h,body=self.s.chamadas[0]
        self.assertEqual(path,'/v1/messages');self.assertEqual(body['model'],MODELO)
        self.assertEqual(body['tool_choice'],{'type':'tool','name':'registrar_classificacao'})
        self.assertNotIn(CHAVE,json.dumps(body));self.assertEqual(r['uso_tokens']['entrada'],120)
    def test_formato_compativel_sem_duplicar_v1(self):
        r=self.motor('openai').classificar(questao());self.assertEqual(r['assuntos'],['Planilhas / Excel'])
        path,h,body=self.s.chamadas[0]
        self.assertEqual(path,'/v1/chat/completions');self.assertEqual(h['Authorization'],'Bearer '+CHAVE)
        self.assertNotIn('X-Api-Key',h);self.assertEqual(r['uso_tokens']['saida'],45)
    def test_erros_http_sem_vazar_chave_ou_seguir_redirect(self):
        for acao in ['429','redirect']:
            with self.subTest(acao=acao):
                self.s.acoes[:]=[acao];antes=len(self.s.chamadas)
                with self.assertRaises(ErroAPI) as cm:self.motor().classificar(questao())
                self.assertNotIn(CHAVE,str(cm.exception));self.assertEqual(len(self.s.chamadas),antes+1)
    def test_resposta_truncada_ou_malformada_nao_aplica_assunto(self):
        for acao in ['invalida','truncada']:
            with self.subTest(acao=acao):
                self.s.acoes[:]=[acao];r=self.motor().classificar(questao())
                self.assertEqual(r['estado'],'revisar');self.assertEqual(r['assuntos'],[])
    def test_lote_pausa_em_429_e_retoma_sem_repetir_concluidas(self):
        self.acervo();self.s.acoes[:]=['ok','429'];self.iniciar();self.esperar()
        j=self.app.ia.job
        self.assertTrue(j['pausada']);self.assertIn('429',j['erro']);self.assertEqual(j['requisicoes'],2)
        self.assertEqual(self.app.banco.questao('PDF-01')['assuntos'],['Planilhas / Excel'])
        self.assertNotIn('analise_ia',self.app.banco.questao('PDF-02'))
        self.iniciar();self.esperar();self.assertEqual(self.app.ia.job['feitos'],1)
        self.assertEqual(len(self.s.chamadas),3)
        self.assertEqual(self.app.banco.questao('PDF-03')['assuntos'],['Hardware'])
        self.assertEqual(self.app.banco.questao('PDF-04')['revisao'],'retida')
        self.assertEqual(self.app.banco.questao('PDF-05')['assuntos'],['Hardware'])
        arquivos=[p for p in self.app.pasta.glob('*') if p.is_file()]
        for p in arquivos:self.assertNotIn(CHAVE.encode(),p.read_bytes())
    def test_edicao_durante_requisicao_e_pausa_preservam_dados(self):
        self.acervo();self.s.acoes[:]=['aguardar'];self.iniciar()
        self.assertTrue(self.s.entrou.wait(5))
        with self.assertRaisesRegex(ValueError,'Pause'):self.app.ia.configurar_api(self.config)
        q=self.app.banco.questao('PDF-01')
        self.app.banco.salvar_questao(dict(q,disciplina='Informática',assuntos=['Hardware'],classificacao='revisada'))
        self.app.ia.pausar();self.s.liberar.set();self.esperar()
        self.assertEqual(self.app.banco.questao('PDF-01')['assuntos'],['Hardware'])
        self.assertEqual(self.app.ia.job['preservadas'],1);self.assertTrue(self.app.ia.job['pausada'])
        self.assertEqual(len(self.s.chamadas),1)
        self.assertNotIn('analise_ia',self.app.banco.questao('PDF-02'))
    def test_opcao_reclassificar_automaticas_preserva_manuais(self):
        self.acervo();self.iniciar(somente_pendentes=False);self.esperar()
        self.assertEqual(self.app.ia.job['feitos'],3)
        self.assertEqual(self.app.banco.questao('PDF-05')['assuntos'],['Planilhas / Excel'])
        self.assertEqual(self.app.banco.questao('PDF-03')['classificacao'],'revisada')
    def test_backup_exclui_config_e_chave(self):
        self.acervo();self.iniciar();self.esperar()
        with zipfile.ZipFile(self.app.backup()) as z:
            self.assertNotIn('dados/api_config.json',z.namelist())
            for nome in z.namelist():self.assertNotIn(CHAVE.encode(),z.read(nome))
            self.assertIn(b'api_claude',z.read('dados/banco.sqlite'))
    def test_rotas_locais_end_to_end_e_token_obrigatorio(self):
        self.acervo();srv=ThreadingHTTPServer(('127.0.0.1',0),handler(self.app))
        t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
        url=f'http://127.0.0.1:{srv.server_port}'
        def req(rota,body=None,token=True):
            data=json.dumps(body).encode() if body is not None else None
            h={'Content-Type':'application/json'}
            if token:h['X-Local-Token']=self.app.token
            with urllib.request.urlopen(urllib.request.Request(url+rota,data=data,headers=h),timeout=5) as r:return json.load(r)
        try:
            with self.assertRaises(urllib.error.HTTPError):req('/api/ia/configurar-api',self.config,False)
            publico=req('/api/ia/configurar-api',self.config)
            self.assertNotIn(CHAVE,json.dumps(publico));self.assertTrue(publico['pronta'])
            self.assertTrue(req('/api/ia/testar-api',{})['ok'])
            req('/api/ia/iniciar',{'modo':'api','limite':25,'threads':2});self.esperar()
            estado=req('/api/ia')
            self.assertEqual(estado['job']['automaticas'],2)
            self.assertNotIn(CHAVE,json.dumps(estado));self.assertEqual(estado['job']['threads'],1)
            self.assertEqual(estado['job']['tokens_entrada'],240)
            q=req('/api/questao?id=PDF-01&editar=1')
            self.assertEqual(q['analise_ia']['metodo'],'api_claude');self.assertEqual(q['gabarito'],'')
            self.assertEqual(q['revisao'],'pendente')
        finally:srv.shutdown();srv.server_close();t.join()


if __name__=='__main__':unittest.main()
