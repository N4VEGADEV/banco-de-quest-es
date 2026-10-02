"""Testes de regras e persistência. Registros sintéticos usados somente aqui."""
import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import date,timedelta
from pathlib import Path
from banco import Banco
from restaurar import validar_backup


class BancoTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=Banco(Path(self.tmp.name)/'dados')
        self.prova={'id':'a'*64,'arquivo':'fgv-2025-teste.pdf','banca':'FGV','paginas':3}
        self.b.registrar_prova(self.prova,[self.raw(i) for i in range(1,5)])

    def tearDown(self):self.tmp.cleanup()

    def raw(self,n):
        return {'id':str(n),'numero':n,'enunciado_candidato':'Registro sintético para teste de persistência. Metáfora aparece só como texto.',
                'alternativas_candidatas':{'A':'Alternativa A','B':'Alternativa B','C':'Alternativa C','D':'Alternativa D'},'contextos_candidatos':[],'segmentos':[]}

    def liberar(self,id='PDF-1',topic='Semântica / Figuras de linguagem / Personificação',key=''):
        q=self.b.questao(id)
        q.update(disciplina='Língua Portuguesa',assuntos=[topic],revisao='apta',classificacao='revisada',conferida=True,
                 status_gabarito='oficial' if key else 'sem',gabarito=key,fonte_gabarito='Fonte sintética de teste' if key else '')
        return self.b.salvar_questao(q)

    def test_importacao_nao_libera_nem_classifica(self):
        self.assertEqual(self.b.painel()['questoes']['prontas'],0)
        self.assertEqual(self.b.listar({'prontas':True})['total'],0)
        self.assertEqual(self.b.listar({})['total'],4)

    def test_filtro_tematico_nao_e_busca_de_palavra(self):
        self.liberar()
        self.assertEqual(self.b.listar({'assunto':'Semântica / Figuras de linguagem / Metáfora','prontas':True})['total'],0)
        self.assertEqual(self.b.listar({'assunto':'Semântica / Figuras de linguagem','prontas':True})['total'],1)
        self.assertEqual(self.b.listar({'texto':'metafora'})['total'],4)
        self.assertEqual(self.b.listar({'assunto':'Semântica / Figuras','prontas':True})['total'],0)

    def test_filtros_combinam_banca_ano_assunto(self):
        self.liberar()
        self.assertEqual(self.b.listar({'banca':'CESGRANRIO','prontas':True})['total'],0)
        self.assertEqual(self.b.listar({'banca':'FGV','ano':'2025','disciplina':'Língua Portuguesa','prontas':True})['total'],1)

    def test_nao_responder_pendente(self):
        with self.assertRaises(ValueError):self.b.responder({'id':'PDF-1','escolha':'A'})

    def test_gabarito_desconhecido_nao_vira_erro(self):
        self.liberar()
        r=self.b.responder({'id':'PDF-1','escolha':'A','tentativa_id':'one'})
        self.assertIsNone(r['tentativa']['correta'])
        self.assertEqual(self.b.painel()['resultados']['corrigidas'],0)
        self.assertEqual(self.b.painel()['resultados']['sem_gabarito'],1)

    def test_oficial_exige_fonte(self):
        q=self.b.questao('PDF-1');q.update(status_gabarito='oficial',gabarito='A',fonte_gabarito='')
        with self.assertRaises(ValueError):self.b.salvar_questao(q)

    def test_tentativa_idempotente_e_agenda(self):
        self.liberar(key='B')
        self.b.responder({'id':'PDF-1','escolha':'A','tentativa_id':'r1'})
        self.b.responder({'id':'PDF-1','escolha':'A','tentativa_id':'r1'})
        self.assertEqual(self.b.painel()['resultados']['tentativas'],1)
        self.assertEqual(self.b.historico()[0]['proxima'],(date.today()+timedelta(days=1)).isoformat())
        self.b.responder({'id':'PDF-1','escolha':'B','tentativa_id':'r2'})
        self.assertEqual(self.b.historico()[0]['proxima'],(date.today()+timedelta(days=7)).isoformat())
        self.assertEqual(self.b.listar({'situacao':'certas'})['total'],1)
        self.assertEqual(self.b.listar({'situacao':'erradas'})['total'],0)
        self.assertEqual(self.b.listar({'prontas':True,'evitar_recentes':True})['total'],0)

    def test_chute_certo_volta_amanha(self):
        self.liberar(key='B')
        r=self.b.responder({'id':'PDF-1','escolha':'B','chute':True})['tentativa']
        self.assertEqual(r['correta'],1)
        self.assertEqual(r['proxima'],(date.today()+timedelta(days=1)).isoformat())

    def test_gabarito_informado_nao_e_oficial(self):
        q=self.liberar(key='A');q['status_gabarito']='informado';self.b.salvar_questao(q)
        self.assertIsNone(self.b.responder({'id':'PDF-1','escolha':'A'})['tentativa']['correta'])

    def test_reimportacao_preserva_edicao_e_historico(self):
        self.liberar(key='B');self.b.responder({'id':'PDF-1','escolha':'B'})
        self.assertEqual(self.b.registrar_prova(self.prova,[self.raw(i) for i in range(1,5)]),0)
        self.assertEqual(self.b.questao('PDF-1')['gabarito'],'B')
        self.assertEqual(self.b.painel()['resultados']['acertos'],1)

    def test_edicao_concorrente(self):
        q=self.b.questao('PDF-1');self.b.salvar_questao(q)
        with self.assertRaises(ValueError):self.b.salvar_questao(q)

    def test_lote_atomico_com_questao_incompleta(self):
        q=self.b.questao('PDF-2');q['alternativas']={'A':'única'};self.b.salvar_questao(q)
        with self.assertRaises(ValueError):
            self.b.lote({'ids':['PDF-1','PDF-2'],'disciplina':'Língua Portuguesa','assuntos':['Semântica'],'classificacao':'revisada','revisao':'apta','conferida':True})
        self.assertEqual(self.b.questao('PDF-1')['disciplina'],'')

    def test_lote_todas_paginas(self):
        self.b.registrar_prova(self.prova,[self.raw(i) for i in range(1,251)])
        r=self.b.lote({'filtro':{},'esperado':250,'disciplina':'Língua Portuguesa','assuntos':['Interpretação de textos'],'classificacao':'revisada','revisao':'apta','conferida':True})
        self.assertEqual(r['alteradas'],250)
        self.assertEqual(self.b.listar({'prontas':True})['total'],250)
        self.assertEqual(len(self.b.listar({'prontas':True})['itens']),20)

    def test_lote_recusa_filtro_alterado(self):
        with self.assertRaises(ValueError):self.b.lote({'filtro':{},'esperado':3,'disciplina':'Errado'})

    def test_caderno_nao_duplica_e_exclusao_preserva_questoes(self):
        c=self.b.caderno({'nome':'Caderno de teste'})['id']
        for _ in range(2):self.b.caderno({'acao':'adicionar','id':c,'ids':['PDF-1','PDF-2']})
        self.assertEqual(self.b.cadernos()[0]['total'],2)
        self.assertEqual(self.b.listar({'caderno_id':c})['total'],2)
        self.b.caderno({'acao':'excluir','id':c})
        self.assertEqual(self.b.listar({})['total'],4)

    def test_simulado_oculta_key_e_congela_gabarito(self):
        q=self.liberar(key='B');self.liberar('PDF-2',key='A')
        s=self.b.criar_sessao({'filtro':{},'quantidade':2,'embaralhar':False})
        self.assertNotIn('gabarito',s['questoes'][0])
        self.b.responder_sessao({'id':s['id'],'questao_id':'PDF-1','escolha':'B'})
        self.assertEqual(self.b.painel()['resultados']['tentativas'],0)
        q['gabarito']='D';self.b.salvar_questao(q)
        done=self.b.finalizar(s['id']);self.assertEqual(done['resultados'][0]['correta'],1)
        self.assertEqual(done['questoes'][0]['gabarito'],'B')
        self.b.finalizar(s['id']);self.assertEqual(self.b.painel()['resultados']['tentativas'],1)
        self.assertEqual(len(done['resultados']),1) # em branco não é tentativa/erro

    def test_gabarito_previa_exige_coerencia_e_versao(self):
        b={'prova_id':self.prova['id'],'texto':'1;B\n2;X','fonte':'Fonte sintética','confirmado':True}
        p=self.b.gabarito_prever(b);b['itens']=p['itens'];self.b.gabarito_salvar(b)
        self.assertEqual(self.b.questao('PDF-1')['gabarito'],'B')
        self.assertEqual(self.b.questao('PDF-2')['status_gabarito'],'anulada')
        with self.assertRaises(ValueError):self.b.gabarito_salvar(b)
        with self.assertRaises(ValueError):self.b.gabarito_prever(dict(b,texto='1;A\n1;B'))
        with self.assertRaises(ValueError):self.b.gabarito_prever(dict(b,texto='99;A'))
        with self.assertRaises(ValueError):self.b.gabarito_prever(dict(b,texto='1;E'))

    def test_reabrir_preserva_dados(self):
        self.liberar(key='C');self.b.responder({'id':'PDF-1','escolha':'C'})
        self.b.pessoal({'id':'PDF-1','favorito':True,'anotacao':'Observação com acento.'})
        reopened=Banco(self.b.pasta)
        self.assertEqual(reopened.painel()['resultados']['acertos'],1)
        self.assertEqual(reopened.questao('PDF-1')['anotacao'],'Observação com acento.')

    def test_sanitizacao_da_visao_de_estudo(self):
        q=self.liberar(key='B');self.b.responder({'id':'PDF-1','escolha':'B'})
        q=self.b.publicar(self.b.questao('PDF-1'))
        self.assertNotIn('gabarito',q)
        self.assertNotIn('original',q)
        self.assertNotIn('gabarito',q['ultima'])


if __name__=='__main__':unittest.main(verbosity=2)
