"""Regressões de comportamento da versão 1.2. Sem download de modelo."""
import tempfile
import unittest
from pathlib import Path
from banco import Banco
from classificador import Classificador
from ia_comum import assinatura, VERSAO_IA, pendente
from regras_assuntos import pista_comando


class MotorTest(unittest.TestCase):
    def setUp(self):self.m=Classificador(usar_modelo=False)

    def q(self,texto,**kw):
        return dict(enunciado=texto,alternativas=dict(A='a',B='b',C='c',D='d'),revisao='pendente',**kw)

    def test_visual_nao_bloqueia_assunto(self):
        q=self.q('Em uma progressão geométrica, determine o quinto termo.',modo_visual=True)
        r=self.m.classificar(q)
        self.assertEqual(r['estado'],'automatica')
        self.assertIn('PG',r['assuntos'][0]);self.assertTrue(r['alertas_conteudo'])
        self.assertEqual(q['revisao'],'pendente')

    def test_alternativa_faltando_nao_inventa_conteudo(self):
        q=self.q('A fórmula no Microsoft Excel foi copiada. Qual o resultado?');q['alternativas']={}
        r=self.m.classificar(q)
        self.assertEqual(r['assuntos'],['Planilhas / Excel']);self.assertTrue(r['alertas_conteudo'])
        self.assertEqual(q['alternativas'],{})

    def test_enunciado_ausente_nao_recebe_tag_das_alternativas(self):
        q=self.q('');q['alternativas']['A']='Microsoft Excel e hardware'
        self.assertEqual(self.m.classificar(q)['estado'],'incompleta')

    def test_probabilidade_incidental_nao_vira_matematica(self):
        r=self.m.classificar(self.q('O financiamento aumenta a probabilidade de pagamento da dívida. Essas práticas são denominadas:'))
        self.assertNotIn('Probabilidade',r['assuntos']);self.assertNotEqual(r['estado'],'automatica')

    def test_gabarito_e_contexto_nao_mudam_regra_linguistica(self):
        q=self.q('O verbo empregado em sentido conotativo está no trecho:',contexto='Uma notícia sobre vírus, backup e segurança digital.')
        a=self.m.classificar(q);q.update(gabarito='A',fonte_gabarito='fixture',anotacao='hardware')
        b=self.m.classificar(q)
        self.assertEqual(a['assuntos'],['Semântica / Denotação e conotação']);self.assertEqual(a,b | {'segundos':a['segundos']})

    def test_conectivos_logicos_nao_sao_coesao_portugues(self):
        r=self.m.classificar(self.q('Considere os conectivos lógicos e determine o valor lógico das proposições.'))
        self.assertEqual(r['disciplina'],'Raciocínio Lógico-Matemático')

    def test_virgula_de_numero_decimal_nao_vira_pontuacao(self):
        q=self.q('Considerando PI igual a 3,14 (três vírgula quatorze), qual o perímetro do círculo?')
        self.assertEqual(self.m.classificar(q)['assuntos'],['Geometria'])

    def test_lideranca_em_custos_nao_e_lideranca_de_equipe(self):
        q=self.q('A direção do banco adotou estratégia de liderança em custo baixo. Como colocar a estratégia em prática?')
        self.assertNotIn('Comportamento organizacional',self.m.classificar(q)['assuntos'])

    def test_mencao_em_citacao_nao_define_assunto(self):
        self.assertIsNone(pista_comando(self.q('No texto “vírus de computador e backup”, qual a opinião do narrador?')))

    def test_codigo_ibge_tem_prioridade_sobre_generico(self):
        r=self.m.classificar(self.q('De acordo com o Código de Ética Profissional do Servidor Público do Instituto Brasileiro de Geografia e Estatística (IBGE), assinale a alternativa.'))
        self.assertEqual(r['disciplina'],'Conhecimentos do IBGE')

    def test_cabecalho_opcional_e_conflito_ingles(self):
        q=self.q('Qual é a característica de um vírus de computador?')
        self.assertEqual(self.m.classificar(q)['estado'],'automatica')
        self.assertEqual(self.m.classificar(q,{'disciplina':'Língua Inglesa'})['estado'],'revisar')


class PersistenciaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=Banco(Path(self.tmp.name))
        self.b.registrar_prova({'id':'a'*64,'arquivo':'prova.pdf'},[{'id':'fixture','numero':1,'enunciado_candidato':'Qual o comportamento do sistema operacional Windows 11?','alternativas_candidatas':dict(A='a',B='b',C='c',D='d')}])
        self.q=self.b.questao('PDF-fixture')
    def tearDown(self):self.tmp.cleanup()
    def resultado(self,q,estado='automatica',**kw):
        return dict(assinatura=assinatura(q),versao_motor=VERSAO_IA,estado=estado,disciplina='Informática',assuntos=['Windows'],motivo='Fixture',**kw)
    def test_reanalise_inconclusiva_retira_auto_anterior_mas_guarda_registro(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado(self.q))
        q=self.b.questao(self.q['id']);self.b.salvar_analise_ia(q['id'],q['versao'],self.resultado(q,'revisar'))
        q=self.b.questao(q['id'])
        self.assertEqual(q['classificacao'],'pendente');self.assertEqual(q['assuntos'],[])
        self.assertEqual(q['analise_ia']['classificacao_anterior']['assuntos'],['Windows'])
    def test_editar_tag_automatica_vira_manual(self):
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],self.resultado(self.q))
        q=self.b.questao(self.q['id']);q=self.b.salvar_questao(dict(q,assuntos=['Hardware']))
        self.assertEqual(q['classificacao'],'revisada');self.assertFalse(pendente(q,'hibrido'))
    def test_regras_podem_ser_complementadas_por_modelo(self):
        q=dict(self.q,analise_ia=self.resultado(self.q,'revisar',modelo=''))
        self.assertFalse(pendente(q,'regras'));self.assertTrue(pendente(q,'hibrido'))
    def test_alertas_e_fora_catalogo_tem_filtros_separados(self):
        r=self.resultado(self.q,'fora_catalogo',alertas_conteudo=['Conferir figura'])
        self.b.salvar_analise_ia(self.q['id'],self.q['versao'],r)
        self.assertEqual(self.b.listar({'ia':'fora_catalogo'})['total'],1)
        self.assertEqual(self.b.listar({'ia':'alertas_conteudo'})['total'],1)
        self.assertEqual(self.b.resumo_ia()['fora_catalogo'],1)
    def test_diagnostico_nao_expoe_resposta_ou_anotacao(self):
        self.b.pessoal({'id':self.q['id'],'anotacao':'Anotação privada'})
        r=self.b.relatorio_ia()[0]
        self.assertNotIn('anotacao',r);self.assertNotIn('gabarito',r);self.assertNotIn('enunciado',r)


if __name__=='__main__':unittest.main()
