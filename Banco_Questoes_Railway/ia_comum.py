"""Contrato da classificação: sem imports de IA ao abrir o banco."""
import hashlib
import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
MODELO_DIR = RAIZ / 'modelos' / 'classificador'
MODELO_REPO = 'Xenova/multilingual-e5-small'
MODELO_COMMIT = '761b726dd34fb83930e26aab4e9ac3899aa1fa78'
VERSAO_IA = '1.2-hibrido-1'
ARQUIVOS_MODELO = {
    'config.json': ('config.json',658,'cb99455288675345e1a4f411438d5d0adbba5fbd3a67ea4fb03c015433b996c1'),
    'tokenizer.json': ('tokenizer.json',17082730,'0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39'),
    'model.onnx': ('onnx/model_quantized.onnx',118308185,'f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193'),
}


def verificar_modelo(pasta):
    for nome,(_,tamanho,esperado) in ARQUIVOS_MODELO.items():
        p=Path(pasta)/nome
        if not p.is_file() or p.stat().st_size!=tamanho:
            raise ValueError('Modelo ausente ou incompleto. Execute INSTALAR_IA.bat novamente.')
        h=hashlib.sha256()
        with p.open('rb') as f:
            for bloco in iter(lambda:f.read(1024*1024),b''):h.update(bloco)
        if h.hexdigest()!=esperado:
            raise ValueError('Um arquivo do modelo está danificado ou é de outra versão. Execute INSTALAR_IA.bat novamente.')


def assinatura(q, somente_conteudo=False):
    campos = {k: q.get(k) for k in ('enunciado', 'contexto', 'alternativas', 'modo_visual', 'segmentos', 'segmentos_contexto')}
    # JSON do navegador transforma 70.0 em 70. A geometria não mudou e não
    # deve invalidar a classificação ao apenas conferir o conteúdo.
    for chave in ('segmentos','segmentos_contexto'):
        campos[chave]=[{**s,'bbox':[round(float(v),6) for v in s.get('bbox',[])]} for s in (q.get(chave) or [])]
    if not somente_conteudo:campos['revisao']=q.get('revisao')
    return hashlib.sha256(json.dumps(campos, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def catalogo_ia():
    base = json.loads((RAIZ / 'catalogo.json').read_text(encoding='utf-8'))
    desc = json.loads((RAIZ / 'ia_catalogo.json').read_text(encoding='utf-8'))
    extras = {'Língua Portuguesa':['Redação oficial'], 'Raciocínio Lógico-Matemático':['Funções','Grandezas e medidas'],
              'Informática':['Windows','Ferramentas de colaboração','Proteção de dados / LGPD']}
    for d, assuntos in extras.items():
        base.setdefault(d, []).extend(assuntos)
    for d in base:
        base[d] = list(dict.fromkeys('Semântica / Figuras de linguagem' if ' / Figuras de linguagem / ' in a else a for a in base[d]))
    return base, desc


def situacao_modelo(pasta=None):
    pasta = Path(pasta or MODELO_DIR)
    ausentes = [p for p in ('onnxruntime','tokenizers','numpy') if importlib.util.find_spec(p) is None]
    arquivos = all((pasta/n).is_file() and (pasta/n).stat().st_size==tamanho for n,(_,tamanho,_) in ARQUIVOS_MODELO.items())
    return {'disponivel': not ausentes and arquivos, 'dependencias_ausentes':ausentes,
            'arquivos_presentes':arquivos, 'modelo':MODELO_REPO, 'versao':VERSAO_IA,
            'mensagem':'Pronta para uso local em CPU.' if not ausentes and arquivos else 'Feche o aplicativo e execute INSTALAR_IA.bat uma vez, com internet.'}


def pendente(q, modo=None):
    if q.get('classificacao') == 'revisada' or q.get('revisao') == 'retida':
        return False
    a = q.get('analise_ia') or {}
    if a.get('metodo')=='api_claude' and a.get('assinatura')==assinatura(q):return False
    if a.get('codigo_motivo')=='falha_processamento':return True
    if modo=='hibrido' and not a.get('modelo'):return True
    return a.get('assinatura') != assinatura(q) or a.get('versao_motor') != VERSAO_IA
