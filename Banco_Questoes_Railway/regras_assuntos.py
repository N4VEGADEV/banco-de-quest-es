"""Pistas auditáveis de assunto, sempre no enunciado, nunca no gabarito.

Uma palavra numa alternativa não prova que a questão cobra aquele assunto.
Regras concorrentes são resolvidas pelo classificador, não pela ordem da lista.
"""
import re
import unicodedata


def normalizar(s):
    s = unicodedata.normalize('NFKD', str(s).lower())
    return ' '.join(''.join(c for c in s if not unicodedata.combining(c)).split())


PT = 'Língua Portuguesa'
MAT = 'Raciocínio Lógico-Matemático'
INF = 'Informática'
PUB = 'Legislação e Administração Pública'
BAN = 'Conhecimentos Bancários'

# Regexes operam em texto sem acentos. Não tentam descobrir a resposta correta.
REGRAS = {
    PT: [
        ('Semântica / Denotação e conotação', r'conotativ|denotativ|denotacao|conotacao|sentido (?:literal|figurado)'),
        ('Semântica / Homônimos e parônimos', r'paronim|homonim'),
        ('Semântica / Hiperônimos e hipônimos', r'hiperonim|hiponim'),
        ('Semântica / Figuras de linguagem', r'figuras? de linguagem|personificacao|metafora|hiperbole|eufemismo|metonimia|sinestesia'),
        ('Semântica / Sinônimos e antônimos', r'sinonim|antonim|substituid[oa].{0,85}(?:sentido|significado)|significado (?:semelhante|oposto|equivalente)|palavra.{0,80}(?:pode|poderia) ser substituida'),
        ('Concordância verbal', r'concordancia.{0,35}(?:verbal|verbo)|flexao.{0,30}(?:verbo|verbal)'),
        ('Concordância nominal', r'concordancia nominal'),
        ('Regência e crase', r'\bregencia\b|\bcrase\b|acento grave'),
        ('Colocação pronominal', r'colocacao pronominal|\bproclise\b|\benclise\b|\bmesoclise\b'),
        ('Pontuação', r'\bpontuacao\b|(?:\ba |\bas |\bda |\bdas |\buma |\bde )virgulas?\b|uso d[eo] (?:dois.pontos|ponto e virgula|travessao)'),
        ('Tipologia textual', r'tipologia textual|tipo textual|genero textual|tipos? de texto'),
        ('Coesão / Referenciação', r'\breferente (?:d[ao]s? |esta)|retomad[ao] pel[ao]|(?:coesao|coesiv).{0,100}(?:referente|retoma)|refere-se.{0,220}refere-se'),
        ('Coesão / Conectivos', r'relacao (?:coesiva|logica).{0,100}(?:paragraf|ideia|expressao|orac)|\bconectivos?\b|relacao entre as (?:duas )?ideias.{0,100}(?:palavra|expressao)'),
        ('Vozes verbais', r'voz (?:ativa|passiva|reflexiva)|vozes verbais'),
        ('Tempos e modos verbais', r'tempos? (?:e modos? )?verba[il]|modo (?:indicativo|subjuntivo|imperativo)|flexao.{0,35}(?:tempo|modo)|conjugacao verbal|emprego do gerundio'),
        ('Ortografia e acentuação', r'ortografia|acentuacao grafica|grafia correta|corretamente (?:grafad|acentuad)'),
        ('Sintaxe / Sujeito e predicado', r'sujeito (?:da|de uma|desta|do verbo)|tipo de sujeito|sujeito (?:oculto|indeterminado|simples|composto)|\bpredicado\b'),
        ('Sintaxe / Complementos e adjuntos', r'funcao sintatica|objeto direto|objeto indireto|complemento nominal|adjunto ad(?:nominal|verbial)'),
        ('Classes de palavras', r'classe (?:gramatical|de palavras)|classificacao morfologica'),
        ('Sintaxe / Orações e períodos', r'oracao.{0,30}reduzida|oracoes (?:coordenadas|subordinadas)|oracao (?:subordinada|adverbial|adjetiva|substantiva)'),
        ('Reescrita de frases', r'frase.{0,90}alteracao de sentido|reescrit[ao].{0,70}sentido|frases?.{0,35}reescrit[ao]'),
        ('Redação oficial', r'manual de redacao|redacao oficial|correspondencias? oficiais?'),
    ],
    MAT: [
        ('Probabilidade', r'(?:qual|calcule|determine).{0,45}probabilidade|probabilidade.{0,220}(?:e igual|sera de|corresponde|vale|e de|aproximadamente)'),
        ('Análise combinatória', r'analise combinatoria|permutac|numero de (?:maneiras|formas|possibilidades|apostas diferentes)|quantas (?:maneiras|formas|combinacoes)'),
        ('Sequências e progressões / PA', r'progressao aritmetica'),
        ('Sequências e progressões / PG', r'progressao geometrica'),
        ('Sequências e progressões / Padrões lógicos', r'sequencia (?:numerica|de numeros|de figuras)|padrao (?:logico|da sequencia)'),
        ('Matemática financeira', r'juros? (?:simples|compostos)|sistema (?:sac|de amortizacao)|taxas?.{0,30}equivalentes'),
        ('Estatística', r'\bmediana\b|\bvariancia\b|desvio.padrao|media (?:aritmetica|ponderada)|distribuicao (?:normal|binomial|de frequencias)'),
        ('Geometria', r'triangulo|quadrilatero|circunferencia|poligono|perimetro|volume (?:do|de um) (?:cilindro|cubo|cone)|area.{0,25}(?:retangulo|quadrado|circulo)'),
        ('Equações', r'sistema (?:linear|de equacoes)|equacao linear|equacao (?:do|de) (?:primeiro|segundo|1|2).{0,5}grau'),
        ('Funções', r'funcoes algebricamente|funcao (?:exponencial|logaritmica|afim|quadratica)|dominio da funcao|funcao f\(x\)'),
        ('Lógica proposicional / Conectivos e tabelas-verdade', r'tabela.verdade|valor (?:logico|de verdade)|proposic[aoe].{0,65}(?:verdadeir|fals)'),
        ('Lógica proposicional / Equivalências e negações', r'negacao (?:logica |d[ae] |da proposicao)|logicamente equivalent|equivalencia logica'),
        ('Lógica de argumentação / Diagramas', r'argumento (?:logico|valido)|premissas|silogismo|ora,.{0,90}logo'),
        ('Conjuntos', r'diagrama de venn|uniao.{0,30}conjuntos|intersecao.{0,30}conjuntos'),
        ('Regra de três', r'regra de tres|inversamente proporcionais'),
        ('Razão e proporção', r'razao entre|divisao proporcional|diretamente proporcionais'),
        ('Porcentagem', r'(?=.*(?:\d\s*%|percentual))(?=.*(?:quantos|quantas|qual (?:o valor|a soma)|porcentagem|percentual.{0,60}(?:e igual|sera|corresponde)))'),
        ('Grandezas e medidas', r'(?=.*(?:litros?|quilometros?|centimetros?|metros? cubicos?|cm3|m3))(?=.*(?:capacidade|conversao|converter))(?=.*(?:quantos|quantas|equivale|corresponde))'),
        ('Matrizes', r'\bmatriz(?:es)?\b|determinante.{0,40}(?:matriz|linha|coluna)'),
    ],
    INF: [
        ('Hardware', r'\bhardware\b|\bcpu\b|memoria ram|discos? rigidos?|placa.mae|\bperifericos\b'),
        ('Apresentações / PowerPoint', r'powerpoint|apresentacao(?:es)? de slides|slides?'),
        ('Windows', r'\bwindows\s*(?:7|8|10|11|server)\b'),
        ('Windows / Arquivos e pastas', r'explorador de arquivos|windows explorer'),
        ('Windows / Atalhos', r'(?=.*windows)(?=.*(?:atalho|combinacao de teclas))'),
        ('Linux', r'\blinux\b|\bubuntu\b|\bdebian\b'),
        ('Editores de texto / Word', r'(?:microsoft|ms) word|word (?:2007|2010|2013|2016|2019|2021|365)|(?:cursor|guia|comando).{0,45}(?:do|no) word'),
        ('Editores de texto / Writer', r'\bwriter\b'),
        ('Planilhas / Excel', r'\bexcel\b'),
        ('Planilhas / Calc', r'(?:libreoffice|br[ -]?office|openoffice) calc'),
        ('Correio eletrônico', r'\be-mails?\b|correio eletronico|protocolo (?:smtp|imap|pop3)|\boutlook\b'),
        ('Redes / Equipamentos e protocolos', r'\btcp/ip\b|\bipv[46]\b|\bintranet\b|rede local|redes? (?:de computadores|lan|wan)|protocolo (?:tcp|udp|dns|dhcp)'),
        ('Internet e navegadores', r'navegador|\bfirefox\b|google chrome|microsoft edge'),
        ('Segurança da informação / Malwares', r'virus de computador|software malicioso|\bmalware\b|\bransomware\b|\bspyware\b|cavalo de troia'),
        ('Segurança da informação / Engenharia social', r'engenharia social|\bphishing\b|\bsmishing\b|\bvishing\b'),
        ('Segurança da informação / Criptografia', r'\bcriptograf|assinatura digital|certificado digital|funcao hash|verificacao de integridade'),
        ('Segurança da informação / Backup', r'\bbackup\b|copias? de seguranca'),
        ('Segurança da informação / Princípios', r'pilares da seguranca|principios da seguranca da informacao|confidencialidade.{0,50}(?:integridade|disponibilidade)'),
        ('Ferramentas de colaboração', r'microsoft teams|google meet|\bvideoconferencia\b'),
        ('Proteção de dados / LGPD', r'\blgpd\b|lei geral de protecao de dados'),
        ('Bancos de dados', r'\bsql\b|\bsgbd\b|banco de dados (?:relacional|nao relacional)|chave (?:primaria|estrangeira)'),
        ('Programação e desenvolvimento', r'linguagem (?:de programacao|python|java)|orientacao a objetos|algoritmo de ordenacao|estrutura de dados'),
        ('Gestão de TI', r'\bitil\b|\bcobit\b|governanca de ti'),
        ('Computação em nuvem', r'computacao em nuvem|\bsaas\b|\bpaas\b|\biaas\b'),
    ],
    'Conhecimentos do IBGE': [
        ('Código de Ética do IBGE', r'codigo de etica.{0,120}(?:ibge|instituto brasileiro de geografia)|comissao de etica do ibge'),
        ('Domicílio e morador', r'domicilio (?:particular|coletivo|improvisado|permanente)|morador habitual'),
        ('Sigilo estatístico', r'sigilo estatistico|confidencialidade.{0,70}(?:censo|recenseamento)'),
    ],
    'Geografia': [
        ('Cartografia', r'\bcartograf|projecoes? cartografic|coordenadas? geograficas?|fusos? horarios?|latitude|longitude'),
        ('Geografia urbana', r'hierarquia urbana|rede urbana|metropolizacao|conurbacao'),
        ('População', r'transicao demografica|piramide etaria|taxa de fecundidade'),
    ],
    PUB: [
        ('Direitos humanos e inclusão', r'direitos humanos|estatuto (?:da igualdade racial|da juventude|do idoso|da pessoa com deficiencia)|lei.{0,15}(?:10\.741|12\.288|12\.852|13\.146)|acessibilidade|nome social|acoes afirmativas|assedio (?:moral|sexual)|decreto.{0,15}5\.904'),
        ('Legislação educacional', r'lei de diretrizes e bases|lei.{0,15}9\.394'),
        ('Princípios da Administração Pública', r'principio.{0,40}(?:administracao publica|constitucional da administracao)'),
        ('Regime dos servidores públicos', r'lei.{0,15}8\.112|regime juridico.{0,35}servidor'),
        ('Ética no serviço público', r'codigo de etica.{0,50}servidor|decreto.{0,15}1\.171'),
        ('Orçamento público', r'ciclo orcamentario|lei de diretrizes orcamentarias|lei orcamentaria anual|plano plurianual'),
    ],
    BAN: [
        ('Sistema financeiro', r'politica (?:monetaria|cambial)|taxa de cambio|regime cambial|mercado (?:de capitais|interbancario)|sistema financeiro nacional|banco central|conselho monetario nacional'),
        ('Produtos e serviços bancários', r'credito (?:pessoal|consignado)|emprestimo pessoal|garantia real|arranjo de pagamento|letras financeiras do tesouro|letras do tesouro nacional'),
        ('Legislação bancária', r'normativo sarb|codigo de conduta etica do (?:banco|banese)|lei.{0,15}(?:4\.595|9\.613)'),
        ('Governança e responsabilidade socioambiental', r'governanca corporativa|responsabilidade (?:social, ambiental|socioambiental)'),
        ('Atendimento e vendas', r'prospeccao.{0,60}(?:vendas|servicos bancarios)|tecnicas de vendas|segmentacao (?:comportamental|de mercado)|fidelizacao de clientes'),
    ],
    'História': [('História do Brasil', r'guerra do paraguai|era vargas|estado novo|colonizacao da america portuguesa|periodo regencial|abolicao da escravatura')],
    'Filosofia': [('História da filosofia', r'francis bacon|jean-paul sartre|friedrich nietzsche|\baristoteles\b|\bexistencialismo\b')],
    'Química': [
        ('Química orgânica', r'\biupac\b|esterificacao|funcional organico|funcoes organicas'),
        ('Estrutura atômica e ligações', r'numeros quanticos|eletrons de valencia|geometria molecular|camada de valencia'),
        ('Soluções e estequiometria', r'solucao aquosa|\bestequiometr|concentracao.{0,40}mol'),
        ('Química analítica', r'\bgravimetr|\btitulacao\b|cromatograf|potenciometr|eletrodo seletivo'),
        ('Química inorgânica', r'sal inorganico|neutralizacao total'),
        ('Segurança em laboratório', r'(?=.*(?:laboratorio|produtos quimicos|metais alcalinos))(?=.*(?:protecao|armazenamento|armazenad|estocad|rotulagem|seguranca))|diamante de hommel'),
    ],
    'Biologia': [
        ('Bioquímica', r'ciclo de krebs|metabolismo celular|serino.proteases|ligacao peptidica'),
        ('Microbiologia', r'controle de micro.organismos|esterilizacao|bacterias.{0,40}(?:cultura|gram)|virus.{0,50}(?:hospedeiro|infeccao)'),
    ],
    'Segurança do Trabalho': [
        ('Normas regulamentadoras', r'norma regulamentadora|\bnr[ -]?(?:[1-9]|[12][0-9]|3[0-8])\b'),
        ('Riscos ocupacionais', r'riscos ocupacionais|higiene ocupacional|agentes (?:fisicos|quimicos|biologicos).{0,60}trabalho'),
        ('Ergonomia e saúde ocupacional', r'\bergonomia\b|doencas ocupacionais'),
    ],
    'Administração Geral': [
        ('Teorias e funções da administração', r'teoria de sistemas|pensamento administrativo|mintzberg|funcoes administrativas'),
        ('Comportamento organizacional', r'motivacao no trabalho|equipe.{0,60}desmotivada|(?:estilos|teorias|tipos) de lideranca|lideranca (?:democratica|autocratica|situacional|transformacional)|sinergias positivas'),
        ('Comunicação organizacional', r'barreiras?.{0,35}comunicacao|sobrecarga de informacao|excesso de informacoes'),
        ('Arquivologia', r'arquivo.{0,30}documentos|arquivologia|tabela de temporalidade'),
    ],
}


def pistas_assuntos(q):
    # Citações entre aspas são contexto, não o comando que cobra o conhecimento.
    s = re.sub(r'“[^”]*”|"[^\"]*"|‘[^’]*’', ' ', q.get('enunciado', ''))
    t = normalizar(s)
    pistas = []
    for d, regras in REGRAS.items():
        for a, pattern in regras:
            m = re.search(pattern, t)
            if m:
                pistas.append({'disciplina': d, 'assunto': a,
                               'evidencia': 'Pista no enunciado: ' + (m.group(0) or a)})
    # Perguntas linguísticas prevalecem sobre o tema da notícia/texto-base.
    portugues = [p for p in pistas if p['disciplina'] == PT]
    if portugues and all(p['assunto']=='Coesão / Conectivos' for p in portugues) and re.search(r'proposic|tabela.verdade|conectivos logicos',t):
        pistas=[p for p in pistas if p['disciplina']!=PT];portugues=[]
    if portugues:
        return portugues
    # Prefere o subtópico específico de Windows ao genérico, sem acumular tags.
    if any(p['assunto'].startswith('Windows /') for p in pistas):
        pistas = [p for p in pistas if p['assunto'] != 'Windows']
    if any(p['assunto'] == 'Segurança da informação / Criptografia' for p in pistas):
        pistas = [p for p in pistas if p['assunto'] != 'Segurança da informação / Princípios']
    if any(p['disciplina']=='Química' for p in pistas):
        pistas = [p for p in pistas if p['assunto'] != 'Geometria']
    if any(p['assunto']=='Código de Ética do IBGE' for p in pistas):
        pistas=[p for p in pistas if p['assunto']!='Ética no serviço público']
    return pistas


def pista_comando(q):
    pistas = pistas_assuntos(q)
    return dict(pistas[0], direta=True) if len(pistas) == 1 else None
