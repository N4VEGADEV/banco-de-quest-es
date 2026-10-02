"""Regressões da classificação; fixtures sintéticas não entram no acervo."""
import tempfile
import unittest
from pathlib import Path
from banco import Banco
from classificador import pista_comando, motivo_incompleta
from ia_comum import assinatura, pendente, VERSAO_IA, verificar_modelo


class ClassificacaoTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=Banco(Path(self.tmp.name)/'dados')
        self.b.registrar_prova({'id':'b'*64,'arquivo':'teste-2026.pdf'},[{'id':'ia1','numero':1,
            'enunciado_candidato':'Verificação sintética de persistência de uma questão completa.',
            'alternativas_candidatas':dict(A='primeira',B='segunda',C='terceira',D='quarta')}])
        self.q=self.b.questao('PDF-ia1')

    def tearDown(self):self.tmp.cleanup()

    def resultado(self,q=None,estado='automatica'):
        return dict(assinatura=assinatura(q or self.q),versao_motor=VERSAO_IA,estado=estado,
                    disciplina='Língua Portuguesa',assuntos=['Pontuação'],motivo='Fixture de teste')

    def test_ia_classifica_sem_liberar_conteudo_ou_gabarito(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado())
        q=self.b.questao(self.q['id'])
        self.assertEqual(q['classificacao'],'automatica');self.assertEqual(q['revisao'],'pendente')
        self.assertEqual(q['gabarito'],'');self.assertEqual(self.b.listar({'prontas':True})['total'],0)
        self.assertEqual(self.b.listar({'classificacao':'automatica'})['total'],1)
        self.assertFalse(pendente(q))

    def test_conferencia_posterior_preserva_assunto_automatico(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado())
        q=self.b.questao(self.q['id']);q.update(revisao='apta',conferida=True)
        q=self.b.salvar_questao(q)
        self.assertEqual(q['classificacao'],'automatica');self.assertEqual(q['assuntos'],['Pontuação'])
        self.assertEqual(self.b.listar({'prontas':True})['total'],1)
        self.assertIsNone(self.b.responder({'id':q['id'],'escolha':'A'})['tentativa']['correta'])

    def test_geometria_igual_apos_json_do_navegador_preserva_ia(self):
        q=self.b.salvar_questao(dict(self.q,segmentos=[{'pagina':1,'bbox':[0.0,0.0,100.0,100.0]}]))
        self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q));q=self.b.questao(q['id'])
        q.update(segmentos=[{'pagina':1,'bbox':[0,0,100,100]}],revisao='apta',conferida=True)
        q=self.b.salvar_questao(q)
        self.assertEqual(q['classificacao'],'automatica');self.assertEqual(q['assuntos'],['Pontuação'])

    def test_modelo_nao_sobrescreve_classificacao_manual(self):
        q=self.q;q.update(disciplina='Informática',assuntos=['Hardware'],classificacao='revisada')
        q=self.b.salvar_questao(q)
        self.assertEqual(self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q)),'preservada')
        self.assertEqual(self.b.questao(q['id'])['assuntos'],['Hardware'])

    def test_edicao_durante_analise_nao_e_perdida(self):
        r=self.resultado();versao=self.q['versao']
        q=self.b.salvar_questao(dict(self.q,enunciado='Um enunciado alterado durante a análise local.'))
        self.assertEqual(self.b.salvar_analise_ia(q['id'],versao,r),'preservada')
        self.assertNotIn('analise_ia',self.b.questao(q['id']))

    def test_anotacoes_favoritos_e_gabarito_preservados(self):
        self.b.pessoal({'id':self.q['id'],'anotacao':'Minha anotação','favorito':True})
        q=self.b.salvar_questao(dict(self.q,status_gabarito='oficial',gabarito='A',fonte_gabarito='Fixture oficial de teste'))
        self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q));q=self.b.questao(q['id'])
        self.assertEqual(q['anotacao'],'Minha anotação');self.assertEqual(q['favorito'],1)
        self.assertEqual(q['gabarito'],'A');self.assertEqual(q['fonte_gabarito'],'Fixture oficial de teste')

    def test_mudar_texto_invalida_classificacao_automatica(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado())
        q=self.b.questao(self.q['id']);q['enunciado']='Um novo texto que poderá cobrar outro conteúdo.'
        q=self.b.salvar_questao(q)
        self.assertEqual(q['classificacao'],'pendente');self.assertEqual(q['assuntos'],[])
        self.assertTrue(pendente(q));self.assertNotIn('analise_ia',q)

    def test_campos_manuais_pendentes_tambem_sao_preservados(self):
        q=self.b.salvar_questao(dict(self.q,disciplina='Informática',assuntos=['Windows']))
        self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q));q=self.b.questao(q['id'])
        self.assertEqual(q['assuntos'],['Windows']);self.assertEqual(q['analise_ia']['estado'],'revisar')

    def test_sugestao_nao_preenche_assuntos_e_filtro_funciona(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado(estado='revisar'))
        q=self.b.questao(self.q['id']);self.assertEqual(q['assuntos'],[])
        self.assertEqual(self.b.listar({'ia':'revisar'})['total'],1)
        self.assertFalse(pendente(q))

    def test_conferir_visual_permite_nova_analise(self):
        q=self.b.salvar_questao(dict(self.q,modo_visual=True))
        self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q,'incompleta'))
        q=self.b.questao(q['id']);self.assertFalse(pendente(q))
        q=self.b.salvar_questao(dict(q,revisao='apta',conferida=True))
        self.assertTrue(pendente(q))

    def test_palavras_so_nas_alternativas_nao_definem_assunto(self):
        q={'enunciado':'Identifique as formas de coesão que retomam a cartilha no texto.',
           'alternativas':{'A':'Homônimo','B':'Parônimo','C':'Hiperônimo','D':'Sinônimo'}}
        self.assertEqual(pista_comando(q)['assunto'],'Coesão / Referenciação')
        self.assertNotIn(pista_comando(q)['assunto'],['Semântica / Homônimos e parônimos','Semântica / Hiperônimos e hipônimos'])
        self.assertIsNone(pista_comando({'enunciado':'No texto sobre "metáfora e hipérbole", qual a opinião do autor?'}))

    def test_comando_explicito_portugues_nao_segue_assunto_do_texto(self):
        q={'enunciado':'O verbo empregado em sentido conotativo está no trecho:',
           'contexto':'Um vírus atacou os computadores e todos fizeram backup.'}
        self.assertEqual(pista_comando(q)['assunto'],'Semântica / Denotação e conotação')

    def test_arquivo_modelo_incompleto_e_rejeitado(self):
        with self.assertRaises(ValueError):verificar_modelo(self.tmp.name)


if __name__=='__main__':unittest.main()
