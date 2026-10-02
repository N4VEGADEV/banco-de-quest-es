"""Importador experimental FGV/IBFC/Cesgranrio. Todo registro nasce pendente de revisão.

O texto extraído é uma representação de trabalho. PDF e coordenadas são a
referência. Nunca substitui silenciosamente trechos nem libera uma questão.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from leitura_isolada import executar
from fontes_pdf import restaurar, verificar
import fitz
from contextos import detectar_contextos, alternativas_horizontais


def linhas(page):
    result = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text = ''.join(s['text'] for s in line['spans']).strip()
            if text:
                result.append({'texto': text, 'bbox': list(line['bbox'])})
    return result


def detectar(page, banca):
    # Perfis de duas colunas presentes na amostra; outros layouts exigem revisão.
    result = []
    w, h = page.rect.width, page.rect.height
    origens = (w * .0715, w * .5235) if banca == 'FGV' else (w * .0605, w * .53)
    pattern = r'^(\d{1,3})$' if banca == 'FGV' else r'^(\d{1,3})\)'
    for line in linhas(page):
        match = re.match(pattern, line['texto'])
        x, y, _, _ = line['bbox']
        if match and 40 < y < h - 40 and min(abs(x - k) for k in origens) < 5:
            result.append({'numero': int(match.group(1)), 'coluna': int(x > w / 2),
                           'y': y, 'bbox_numero': line['bbox']})
    return sorted(result, key=lambda a: (a['coluna'], a['y']))


def extrair(path, destino):
    if 'cesgranrio' in path.name.lower():
        from cesgranrio import extrair_cesgranrio
        return extrair_cesgranrio(path,destino)
    content = path.read_bytes()
    sha = hashlib.sha256(content).hexdigest()
    doc = fitz.open(stream=content, filetype='pdf')
    capa = doc[0].get_text() if len(doc) else ''
    nome = path.name.lower()
    if 'CESGRANRIO' in capa.upper():
        doc.close()
        from cesgranrio import extrair_cesgranrio
        return extrair_cesgranrio(path,destino)
    # Nome é pista de perfil, não certificado de procedência oficial.
    if 'ibfc' in nome or 'IBFC' in capa:
        banca = 'IBFC'
    elif 'fgv' in nome or 'FGV' in capa:
        banca = 'FGV'
    else:
        raise ValueError('Banca/layout não reconhecido: ' + path.name)
    anchors = []
    for pno, page in enumerate(doc):
        # Capas: sem sequência de alternativas não constituem página de questões.
        txt = page.get_text()
        pattern = r'\([A-E]\)' if banca == 'FGV' else r'\b[a-e]\)'
        if len(re.findall(pattern, txt)) < 4:
            continue
        anchors.extend(dict(a, pagina=pno + 1) for a in detectar(page, banca))
    expected = 1
    aceitas, ignoradas = [], []
    for a in anchors:
        if a['numero'] == expected:
            aceitas.append(a)
            expected += 1
        else:
            ignoradas.append(a)
    if not aceitas:
        raise ValueError('Nenhuma sequência de questões detectada. Revisão de layout/OCR necessária.')
    (destino / 'fontes').mkdir(parents=True, exist_ok=True)
    target = destino / 'fontes' / (sha + '.pdf')
    if not target.exists():
        shutil.copyfile(path, target)
    contextos = detectar_contextos(doc, aceitas, banca)
    registros = []
    for i, anchor in enumerate(aceitas):
        seguinte = aceitas[i + 1] if i + 1 < len(aceitas) else None
        start = ((anchor['pagina'] - 1) * 2 + anchor['coluna'])
        end = ((seguinte['pagina'] - 1) * 2 + seguinte['coluna']) if seguinte else start
        segmentos, textos, flags = [], [], set()
        for loc in range(start, end + 1):
            pno, col = divmod(loc, 2)
            page = doc[pno]
            w, h = page.rect.width, page.rect.height
            top = anchor['y'] - 1 if loc == start else 45
            bottom = seguinte['y'] - 2 if seguinte and loc == end else h - 45
            for ctx in contextos:
                seg = ctx['segmentos'][0]
                if seguinte and loc == end and seg['pagina'] == pno+1 and seg['coluna'] == col+1 and abs(seg['bbox'][3] - (seguinte['y']-2)) < 1:
                    bottom = min(bottom,seg['bbox'][1])
            if bottom <= top:
                continue
            rect = fitz.Rect(30 if col == 0 else w / 2 + 8, top,
                             w / 2 - 8 if col == 0 else w - 30, bottom)
            text = page.get_text('text', clip=rect, sort=True).strip()
            if not text and not any(fitz.Rect(im['bbox']).intersects(rect) for im in page.get_image_info()):
                continue
            segmentos.append({'pagina': pno + 1, 'coluna': col + 1, 'bbox': list(rect)})
            textos.append(text)
            for image in page.get_image_info():
                if fitz.Rect(image['bbox']).intersects(rect):
                    flags.add('imagem_no_recorte')
            # Vetores podem ser gráficos ou tabelas. Não são automaticamente figuras úteis.
            for draw in page.get_drawings():
                r = draw['rect']
                if 10 < r.width < w * .48 and 10 < r.height < h * .8 and r.intersects(rect):
                    flags.add('elemento_vetorial_a_conferir')
        texto = '\n\n'.join(textos)
        sem_numero = re.sub(r'^\s*' + str(anchor['numero']) + r'\)?\s*', '', texto, count=1)
        pat = r'(?m)^[ \t]*\(([A-E])\)[ \t]*' if banca == 'FGV' else r'(?m)^[ \t]*([a-e])\)[ \t]*'
        marcas = list(re.finditer(pat, sem_numero))
        letras = [m.group(1).upper() for m in marcas]
        valid = letras in (list('ABCD'), list('ABCDE'))
        alternativas = {}
        enunciado = sem_numero[:marcas[0].start()].strip() if marcas else sem_numero
        if valid:
            for j, m in enumerate(marcas):
                stop = marcas[j+1].start() if j+1 < len(marcas) else len(sem_numero)
                alternativas[m.group(1).upper()] = sem_numero[m.end():stop].strip()
            if any(not v for v in alternativas.values()):
                flags.add('alternativa_sem_texto_verificar_imagem')
        else:
            horizontal = alternativas_horizontais(sem_numero) if banca == 'IBFC' else None
            if horizontal:
                enunciado, alternativas = horizontal
                flags.add('alternativas_em_colunas_reordenadas_por_rotulo')
            else:
                flags.add('marcadores_de_alternativas_incompletos_ou_ambiguos')
        if re.search(r'(?i)\b(?:o texto|do texto|autor|fragmento|trecho|sublinhad|destacad|figura|tabela|grafico|gráfico)', enunciado):
            flags.add('conferir_texto_base_ou_formatacao_visual')
        if len(segmentos) > 1:
            flags.add('questao_atravessa_coluna_ou_pagina')
        flags.add('conferir_fim_da_questao_e_cabecalhos')
        registros.append({'id': f'{sha[:16]}-{anchor["numero"]:03d}',
                          'prova_id': sha, 'numero': anchor['numero'], 'banca': banca,
                          'arquivo_original': path.name, 'pagina_inicial': anchor['pagina'],
                          'segmentos': segmentos, 'texto_extraido': texto,
                          'enunciado_candidato': enunciado, 'alternativas_candidatas': alternativas,
                          'contextos_candidatos': [ctx for ctx in contextos if anchor['numero'] in ctx['numeros']],
                          'alertas': sorted(flags), 'status': 'pendente', 'observacao': ''})
    return {'id': sha, 'arquivo': path.name, 'banca': banca, 'paginas': len(doc),
            'perfil': 'duas_colunas_amostra_v0.2', 'marcadores_ignorados': ignoradas,
            'questoes_detectadas': len(registros), 'origem_oficial_verificada': False}, registros


def importar(pasta, destino):
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / 'acervo.json'
    acervo = json.loads(arq.read_text(encoding='utf-8')) if arq.exists() else {'provas': [], 'questoes': [], 'falhas': []}
    conhecidos = {p['id'] for p in acervo['provas']}
    novos, repetidos = 0, 0
    def salvar_acervo():
        tmp=arq.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as f:json.dump(acervo,f,ensure_ascii=False,indent=2)
        tmp.replace(arq)
    def andamento(path,etapa):
        registro={'arquivo':str(path),'etapa':etapa}
        (destino/'ultima_importacao.json').write_text(json.dumps(registro,ensure_ascii=False,indent=2),encoding='utf-8')
        print(etapa+': '+path.name,flush=True)
    for path in sorted(pasta.rglob('*')):
        if path.suffix.lower() != '.pdf':
            continue
        andamento(path,'Calculando identificação')
        try:
            with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        except OSError as e:
            acervo['falhas']=[f for f in acervo['falhas'] if f.get('arquivo')!=path.name]
            acervo['falhas'].append({'arquivo':path.name,'erro':'Falha ao ler arquivo: '+str(e)})
            salvar_acervo();continue
        relativo=str(path.relative_to(pasta))
        acervo['falhas']=[f for f in acervo['falhas'] if not (
            f.get('sha256')==sha or f.get('caminho_relativo')==relativo or
            (not f.get('sha256') and not f.get('caminho_relativo') and f.get('arquivo')==path.name))]
        if sha in conhecidos:
            fonte=destino/'fontes'/(sha+'.pdf')
            try:
                if verificar(fonte,sha):
                    andamento(path,'Restaurando cópia ausente ou divergente do PDF')
                    restaurar(path,fonte,sha)
            except (OSError,ValueError) as e:
                acervo['falhas'].append({'arquivo':path.name,'sha256':sha,'erro':'Falha ao restaurar PDF: '+str(e)})
                salvar_acervo()
            repetidos += 1
            continue
        try:
            andamento(path,'Extraindo em processo isolado')
            prova, questoes = executar(path, destino)
        except Exception as e:
            acervo['falhas'].append({'arquivo': path.name, 'caminho_relativo': relativo, 'sha256': sha, 'erro': str(e)})
            salvar_acervo()
            continue
        acervo['provas'].append(prova)
        acervo['questoes'].extend(questoes)
        conhecidos.add(sha)
        novos += 1
        if novos % 5 == 0:salvar_acervo()
    salvar_acervo()
    andamento(arq,'Importação concluída')
    return novos, repetidos, len(acervo['questoes'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('pasta', type=Path)
    p.add_argument('--destino', type=Path, default=Path(__file__).resolve().parent / 'dados' / 'extracao')
    args = p.parse_args()
    if not args.pasta.is_dir():
        p.error('A pasta de provas não existe')
    print(importar(args.pasta, args.destino))
