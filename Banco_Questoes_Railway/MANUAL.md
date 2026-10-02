# Banco de Questões 1.3.1 — Railway privado

Aplicativo independente para estudar questões de provas em PDF, com classificação explícita por assunto. Reaproveita os módulos de extração do banco anterior e substitui a seleção por dossiês por consultas às categorias cadastradas. O código-fonte completo do aplicativo acompanha o pacote.

## Publicação e acesso

Siga **GUIA_RAILWAY.md** para enviar o código ao GitHub, publicar pelo Dockerfile, conectar o volume `/data` e configurar sua conta. Acesse o endereço HTTPS do serviço e entre com seu usuário e senha de administrador. Este manual explica as funções de estudo depois do login.

O banco e os PDFs ficam em `/data/acervo`, no volume do Railway. A interface não carrega fontes ou scripts de terceiros. A classificação opcional por Claude envia o conteúdo textual das questões ao fornecedor configurado e exige chave e eventual saldo; consulte `GUIA_API_CLAUDE.md`. A classificação por regras funciona sem API. O modelo E5 da edição local não é instalado por este Dockerfile.

O pacote online tem uma conta privada de administrador. Não há cadastro público nem separação de histórico por estudante. Mantenha uma réplica do serviço.

## 1. Importar provas

Em **Provas e importação**, selecione um ou vários PDFs. Alternativamente, coloque arquivos em `provas_entrada` e clique em **Ler pasta provas_entrada**. Duas provas enviadas anteriormente pelo usuário estão nessa pasta para o primeiro teste.

Cada arquivo é identificado pelo conteúdo (SHA-256). Reimportar o mesmo PDF preserva as questões editadas e o histórico. A cópia original fica em `/data/acervo/fontes`; uma cópia ausente ou divergente pode ser restaurada enviando novamente o PDF íntegro. A interface confere sua integridade antes de exibi-la.

O processamento ocorre por arquivo. É possível parar depois do arquivo atual. Fechar a página não interrompe a importação; reiniciar ou publicar o serviço encerra o processo em andamento. Arquivos já concluídos permanecem gravados e podem ser reconhecidos numa nova importação.

Os perfis automáticos são herdados do projeto anterior: FGV, IBFC e Cesgranrio, com layouts específicos. PDFs digitalizados não passam por OCR. Em caso de layout não reconhecido, o PDF permanece acessível e você pode cadastrar suas questões manualmente. O erro exibido não significa que a prova não contém questões.

Em **Dados**, na linha da prova, ajuste o nome, a banca, o ano, o órgão, o cargo e a identificação do caderno/cor/tipo. A banca e o ano sugeridos pelo arquivo devem ser conferidos. PDFs diferentes que contêm a mesma questão não são unificados automaticamente.

## 2. Conferir conteúdo e classificar

Questões novas começam pendentes. A tela **Conferir / editar** mostra os campos extraídos e os recortes originais ao lado. Consulte também **Abrir PDF original**.

Há duas verificações independentes:

- **Conteúdo completo e conferido**: enunciado, alternativas, texto-base, imagens e formatação necessários estão disponíveis.
- **Classificação definida**: disciplina e pelo menos um assunto revisados por você ou classificados automaticamente pela IA local ou pela API configurada. A origem automática permanece visível.

Somente quando as duas estiverem concluídas a questão entra no filtro **Só prontas para resolver**. Uma questão retida continua editável, mas não entra em treinos e simulados.

O catálogo sugere nomes de categorias. Na hospedagem, a tela **Classificação** oferece regras e Claude por API em lote; consulte **GUIA_API_CLAUDE.md** para configuração e critérios. A opção de IA local permanece indisponível sem o modelo e suas dependências. É possível escrever novas disciplinas e assuntos. Separe assuntos com ponto e vírgula. Use `/` para indicar hierarquia, por exemplo:

`Semântica / Figuras de linguagem / Personificação`

Uma busca por `Semântica` inclui seus subassuntos. Uma busca por `Personificação` deve selecionar o caminho completo correspondente. A pesquisa por texto é independente e procura trechos normalizados, sem diferenciar acentos e maiúsculas.

Classifique a habilidade realmente cobrada. A presença de “metáfora” em uma alternativa, por exemplo, não torna necessariamente a questão uma questão de metáfora. Questões que cobram vários conteúdos podem receber mais de um assunto.

Os avisos da extração são sinais para conferência; não provam que uma questão esteja correta ou incompleta. Para questões visuais, marque **Exibir recortes originais ao abrir a questão**. Se um recorte omitir informações, acrescente páginas inteiras da questão ou do texto-base. O texto editável pode manter uma descrição das alternativas que são imagens, preservando sempre a referência visual no PDF.

**Cadastro manual:** primeiro importe a prova; depois use **Cadastrar pelo PDF**, escolha a prova, informe o número e preencha o conteúdo. Há suporte a A/B (por exemplo, Certo/Errado), A–D e A–E. Para A/B, preencha explicitamente o que cada letra significa.

## 3. Trabalhar em lote

Filtre o conjunto desejado e clique em **Selecionar todo o filtro**. Isso alcança todas as páginas, sem exigir seleção de 100 em 100.

Você pode atribuir disciplina, acrescentar ou substituir assuntos, revisar a classificação e alterar a conferência do conteúdo. Campos em branco preservam os valores atuais. Para liberar conteúdo, declare a conferência de todas as questões selecionadas. Não é uma conferência automática.

Se uma validação falhar, todo o lote é revertido. O aplicativo também exige uma nova seleção caso o total do filtro tenha mudado entre seleção e aplicação. Reclassificar uma questão não apaga respostas anteriores.

## 4. Cadastrar gabaritos

Em **Provas e importação → Gabarito**, escolha a prova e cole uma linha por questão:

```text
1;A
2;C
3;X
```

Essas linhas são apenas exemplo de formato. **Não são gabaritos das provas incluídas.** X significa anulada. Também é aceito `1 A`. Não há reconhecimento automático de PDF de gabarito nesta versão.

Informe a fonte oficial e confira cargo, ano, número, tipo/cor de caderno e eventual versão definitiva. Gere a prévia, confira as alterações e confirme o vínculo antes de salvar. Números repetidos, questões ausentes e alternativas inexistentes são recusados. Você também pode cadastrar um gabarito individual no editor.

Os estados disponíveis são:

- **Oficial conferido**: utilizado para correção e aproveitamento.
- **Informado, não oficial**: exibido depois da tentativa, mas não entra no cálculo de acertos.
- **Sem gabarito**: a tentativa é salva sem acerto/erro.
- **Anulada**: não gera acerto/erro.

“Oficial” é uma declaração de quem cadastra e confere a fonte, não uma verificação externa automática. Comentários de resolução também são conteúdo cadastrado, não explicações geradas ou validadas pelo aplicativo.

Cada tentativa preserva o gabarito usado naquele momento. Cadastrar ou corrigir um gabarito depois não recalcula o passado. Refaça a questão para registrar uma nova tentativa corrigida.

## 5. Resolver e revisar

Os filtros combinam critérios de banca, ano, prova, disciplina, assunto, caderno, gabarito e respostas. A condição das respostas considera a **última tentativa** daquela questão. Os totais do painel consideram **todas as tentativas**, enquanto “questões respondidas” conta questões distintas.

Abra **Responder**, marque uma alternativa e clique em **Responder**. O resultado e os comentários cadastrados aparecem depois da tentativa. Você pode marcar chute/dúvida, favoritar e registrar anotações.

- Erro ou chute: revisão disponível no dia seguinte.
- Acerto: revisão em 7 a 10 dias, conforme a preferência.
- Sem gabarito oficial: sem acerto/erro; só é agendada para o dia seguinte se marcada como chute.

O intervalo não bloqueia o acesso manual. Ative **Respeitar intervalo de revisão** para aplicá-lo ao filtro. **Revisão disponível hoje** reúne o que já venceu. As datas seguem o relógio local do computador.

## 6. Cadernos e simulados

Crie um caderno e adicione a seleção feita na tela Questões. A mesma questão pode entrar em vários cadernos, sem duplicar o registro. Excluir um caderno preserva as questões e suas respostas. Para retirar itens de um caderno, selecione-os na página exibida.

Crie simulados a partir dos filtros atuais na tela Questões, ou de todo o acervo pronto na tela Simulados. Defina o nome, a quantidade máxima (até 300), a ordem aleatória e se deseja somente gabaritos oficiais. Se houver menos questões disponíveis, o simulado terá esse total menor.

Respostas são gravadas ao clicar **Salvar e avançar**, ao navegar entre os números ou sair pelos botões de navegação. Se fechar a aba imediatamente depois de marcar uma opção, sem salvar/navegar, essa alteração ainda não foi gravada. Use o contador de respostas salvas para confirmar.

O simulado pode ser retomado. Seu conteúdo e gabaritos ficam congelados na criação; alterações posteriores no banco não modificam a sessão. O cronômetro mostra o tempo transcorrido desde o início, incluindo pausas. Não há encerramento automático por tempo.

Ao finalizar, só as questões respondidas geram tentativas. Questões em branco e respostas sem gabarito oficial não entram no aproveitamento. Uma segunda finalização não duplica as tentativas.

## 7. Backup e restauração

**Dados e backup → Criar e baixar backup** reúne o banco SQLite e os PDFs, com respostas, categorias, notas, favoritos, cadernos e simulados. A pasta de backups do serviço fica em `/data/acervo/backups`. Baixe também o ZIP e guarde uma cópia no seu computador.

Resultados da API entram no backup. Sua chave e a configuração da API ficam fora dele; configure novamente após restaurar em uma instalação nova.

Para restaurar no Railway, siga a seção 7 de **GUIA_RAILWAY.md**. O restaurador valida a estrutura, o banco e os hashes dos PDFs antes de substituir os dados, na inicialização do serviço. A pasta anterior é preservada no volume como `dados_antes_restauracao_DATA_HORA`.

A exportação JSON da tela Questões contém os registros selecionados pelo filtro, inclusive gabaritos cadastrados. É útil para consultar o conteúdo em outro programa, mas **não substitui o backup completo**. Não há importação desse JSON nesta versão.

## Limites desta entrega

- A classificação local usa E5 quantizado, comandos explícitos e cabeçalhos; é um piloto conservador. Claude por API é opcional e valida respostas contra o catálogo. Ambos podem errar; assuntos incertos ficam como sugestões. Não há inferência por dossiê nem geração de respostas ou gabaritos.
- A extração não é universal, não faz OCR e não comprova integridade sem revisão. A nova integração foi validada em duas amostras Cesgranrio, não em todas as provas do acervo anterior.
- Não foi implementada migração automática do histórico do aplicativo principal. Os projetos têm bancos e pastas independentes.
- Não há cópia do acervo, comentários de professores, comunidade ou conteúdo do Qconcursos.
- A integração API foi exercitada com fornecedor HTTP simulado. O acesso privado passou nos testes locais, inclusive com Gunicorn real; a imagem Docker, a publicação na sua conta Railway e a conexão com sua chave ainda precisam ser confirmadas.
- O painel registra progresso; não pretende reproduzir cada recurso da plataforma usada como referência.

## Para quem quiser manter o código

`banco.py` contém o modelo e as regras; `servidor.py` contém as rotas reaproveitadas da edição local. `online.py` protege essas rotas com login; `wsgi.py` e `gunicorn.conf.py` configuram o servidor público. `web/` e `templates/` contêm a interface. Os módulos `importador.py`, `cesgranrio.py`, `contextos.py`, `leitura_isolada.py`, `recorte_isolado.py` e `fontes_pdf.py` foram reaproveitados do projeto anterior.

Execute `python -m unittest testes testes_ia testes_v12 testes_api testes_online` para os testes de regras,
persistência, classificador híbrido, integração de API e acesso privado. Esses testes usam dados sintéticos
temporários, sem alterar a pasta de dados do aplicativo.

A dependência de leitura de PDF é PyMuPDF 1.26.6, instalada durante a construção da imagem Docker. Mais informações: https://pypi.org/project/PyMuPDF/1.26.6/ e https://github.com/pymupdf/PyMuPDF.

## Transferir a edição local

Consulte a seção 7 de `GUIA_RAILWAY.md` antes de transferir uma instalação com histórico.
Os backups das versões 1.0 a 1.3 são aceitos sem reimportar PDFs. O modelo da IA local não
entra no backup; os resultados já salvos entram normalmente.
