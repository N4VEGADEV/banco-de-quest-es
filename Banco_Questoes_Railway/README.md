# Banco de Questões — Railway, acesso privado

Esta entrega adapta o Banco de Questões Local 1.3 para publicar no Railway com **uma conta de administrador**. Login, logout, sessões revogáveis, proteção das rotas, importação de PDFs, classificação por API, estudo, histórico e backups estão incluídos.

**Comece por [GUIA_RAILWAY.md](GUIA_RAILWAY.md).** Ele mostra como enviar esta pasta ao seu repositório, conectar o Railway, criar o volume, configurar as credenciais e gerar o endereço do site. Não envie o ZIP como único arquivo do repositório: envie a pasta extraída.

Credenciais são definidas em **Variables do Railway**, nunca neste README ou no código:

| Nome | Valor |
| --- | --- |
| `ADMIN_USER` | Seu nome de usuário, por exemplo `admin` |
| `ADMIN_PASSWORD` | Sua senha, com pelo menos 12 caracteres |
| `SECRET_KEY` | Texto aleatório com pelo menos 32 caracteres |
| `DATA_DIR` | `/data/acervo` |
| `PORT` | `8080` |

Conecte um volume ao serviço com **Mount Path `/data`**. O aplicativo usa a subpasta `/data/acervo`; banco e PDFs persistem nela entre publicações. A entrada pública é **Flask + Gunicorn**, configurada pelo `Dockerfile`. Não configure `ABRIR.bat`, `iniciar.py` ou `servidor.py` como comando de início do Railway.

Mantenha **uma réplica**. O pacote usa SQLite e um processo para coordenar importações e lotes. Não há cadastro público nem contas separadas de estudantes nesta entrega; seu acervo e progresso pertencem ao acesso administrativo privado.

Depois de entrar, use **Classificação → Configurar Claude / API**. Para manter a chave após reiniciar, defina `BANCO_API_KEY` nas Variables; modelo, protocolo e endereço podem ser configurados no aplicativo ou por `API_MODELO`, `API_PROTOCOLO` e `API_BASE_URL`. O guia explica esses campos. A classificação continua sujeita a conferência.

## Arquivos principais

- `Dockerfile`: instalação das dependências e início do servidor.
- `wsgi.py`, `online.py`, `gunicorn.conf.py`: servidor privado e autenticação.
- `servidor.py`, `banco.py`: operações reaproveitadas da versão local.
- `web/`, `templates/`: interface e página de entrada.
- `testes_online.py`: autenticação, restauração e execução real com Gunicorn.
- `GUIA_RAILWAY.md`: publicação e transferência de backup.
- `RELATORIO_RAILWAY.txt`: verificações e limites da validação.

## Testes

Com Python 3.12 e as dependências instaladas:

```bash
pip install -r requirements-railway.txt
python -m unittest testes testes_ia testes_v12 testes_api testes_online
```

Os testes de servidor Gunicorn exigem Linux. Não usam conta de hospedagem nem chave real de IA. Esta entrega foi exercitada localmente; a publicação efetiva será feita por você na sua conta do Railway.
