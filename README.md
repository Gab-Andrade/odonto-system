# Odonto System

Sistema web de gestão odontológica: prontuário digital, odontograma 2D/3D, precificação
configurável, financeiro/estoque e inteligência clínica, otimizado para uso em tablet.

Visão, arquitetura e roadmap: [docs/PLANO.md](docs/PLANO.md).

## Estrutura

```
backend/    API FastAPI (monólito modular) + migrações Alembic + testes
dev.ps1     sobe o backend local (Windows); testes.ps1 roda lint e testes no odonto_test
docker/     scripts do Postgres (role da aplicação)
frontend/   React + Vite PWA (tablet-first), cliente tipado gerado do OpenAPI
docs/       documentação
```


## Rodando com Docker

```sh
docker compose up --build
```

- API e documentação interativa: http://localhost:8000/docs
- As migrações rodam automaticamente na subida da API.

Criar a primeira clínica e o usuário admin (a senha é pedida no terminal):

```sh
docker compose exec api python -m app.cli criar-clinica \
  --nome "Clínica Exemplo" --slug exemplo \
  --admin-email admin@exemplo.com.br --admin-nome "Nome do Admin"
```

## Rodando o backend sem Docker

Requer Python 3.12+ e um PostgreSQL 16 com o role da aplicação criado:

```sh
psql -U odonto -d odonto -v app_password=odonto_app -v owner=odonto -f docker/postgres/roles.sql
```

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Testando localmente (Windows, sem Docker)

### 1. PostgreSQL nativo

Com o PostgreSQL (16 ou mais novo) instalado como serviço, no `psql` como superusuário
(`postgres`):

```sql
CREATE ROLE odonto LOGIN PASSWORD 'odonto';           -- dono do schema (migrações)
CREATE DATABASE odonto OWNER odonto;
\c odonto
CREATE EXTENSION IF NOT EXISTS pg_trgm;               -- as migrações precisam das duas e
CREATE EXTENSION IF NOT EXISTS btree_gist;            -- o role odonto não é superusuário
```

Depois crie o role da aplicação (`odonto_app`, sem `BYPASSRLS`) com o script do projeto:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -d odonto `
  -v app_password=odonto_app -v owner=odonto -f docker/postgres/roles.sql
```

### 2. Backend e dados de demonstração

```powershell
cd backend
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env          # para testar com calma: ACCESS_TOKEN_MINUTES=480
cd ..
.\dev.ps1 -Demo                 # migra, cria os dados de demonstração e sobe a API
```

`.\dev.ps1` sozinho migra e sobe a API; `-Demo` roda antes `python -m app.cli demo`, que é
idempotente (pode rodar de novo sem duplicar nada) e usa a clínica do `--slug` (padrão
`teste`), criando-a se não existir. Ele cria:

- equipe: Dra. Beatriz e Dr. Rafael (dentistas), recepção e gestor, todos com e-mail
  `@example.com` e senha `demo-odonto-2026` (o comando lista os e-mails);
- pacientes: **Carlos** (adulto, 30 dentes, cáries, restaurações, canal, coroa e um
  ausente), **Laura** (4 anos, decídua, com responsável) e **Pedro** (9 anos, mista);
- a "Tabela Demo" de preços, um plano aprovado e um orçamento aguardando resposta do
  Carlos, a "Cadeira Demo" e consultas para amanhã e depois de amanhã;
- um modelo de anamnese publicado, a anamnese do Carlos (alergia e pressão alta viram
  alerta), um atendimento fechado com evolução e outro aberto há 3 dias (aparece em Alertas).

O comando recusa rodar com `ENVIRONMENT=production`.

### 3. Login no Swagger

1. Abra http://localhost:8000/docs.
2. `POST /auth/login` → *Try it out* com `{"email": "...", "password": "..."}`. Se o
   usuário estiver em mais de uma clínica, a resposta 409 lista as clínicas: repita
   enviando também `"clinic_id"`.
3. Copie o `access_token`, clique em **Authorize** (cadeado no topo) e cole só o token.
   Ele vale `ACCESS_TOKEN_MINUTES` (60 por padrão).

### 4. Roteiro curto do odontograma 3D

1. `GET /pacientes?busca=demo` → copie o `id` do Carlos (ou da Laura/Pedro).
2. `GET /odontograma/pacientes/{id}/arcada` → dentição e lista de dentes.
3. `GET /odontograma/pacientes/{id}/visualizacao` → cada dente com as cinco faces, o nome
   do nó 3D de cada face (`16_O` …), a cor resolvida e `hidden` (o 46 do Carlos, ausente).
4. `GET /odontograma/3d/arcada.glb?dentes=<lista da arcada separada por vírgula>` e
   `GET /odontograma/3d/dentes/{fdi}.glb` → modelo 3D.
5. Marque algo (`POST /odontograma/pacientes/{id}/eventos`) e veja a mudança em
   `/visualizacao` e em `/comparacao?de=...&ate=...`.

**Ver os `.glb`:** no Swagger, a resposta do GLB tem o link *Download file*. Salve como
`arcada.glb` e arraste para https://gltf-viewer.donmccurdy.com (roda no navegador; o
arquivo não sai da máquina). O painel *Scene* mostra os nós `dente_<fdi>` e as faces.

### 5. Testes de integração locais

Use um banco **separado**, `odonto_test` (os testes o apagam e recriam a cada execução;
nunca aponte para o `odonto`). Como `postgres`:

```sql
CREATE DATABASE odonto_test OWNER odonto;
\c odonto_test
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
GRANT USAGE ON SCHEMA public TO odonto_app;
ALTER DEFAULT PRIVILEGES FOR ROLE odonto IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO odonto_app;
ALTER DEFAULT PRIVILEGES FOR ROLE odonto IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO odonto_app;
-- alguns testes conferem a mensagem "permission denied"; com o Postgres em português
-- ela viria traduzida:
ALTER DATABASE odonto_test SET lc_messages = 'C';
```

Depois, `.\testes.ps1` roda o lint e todos os testes (argumentos vão para o pytest).

### 6. Frontend

Requer Node.js 20+ (testado com o 26). Com a API rodando (`.\dev.ps1`), em outro terminal:

```powershell
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Ou tudo de uma vez: `.\dev.ps1 -Demo -Front` (abre o `npm run dev` em outra janela).

O Vite repassa `/api/*` para a API em `localhost:8000`, então não há CORS no
desenvolvimento. Entre com um usuário da demonstração (ex.: `beatriz.demo@example.com`,
senha `demo-odonto-2026`) ou com o admin da clínica.

| Comando | O que faz |
|---|---|
| `npm run dev` | servidor de desenvolvimento |
| `npm run lint` | ESLint |
| `npm run build` | checagem de tipos + build de produção (com o service worker do PWA) |
| `node scripts/conferir-glb.mjs arquivo.glb` | confere um .glb da arcada com o mesmo carregador do app (nós e faces) |
| `npm run atualizar-api` | exporta o OpenAPI do backend (`python -m app.cli openapi`) e regenera `src/api/schema.d.ts` |

O cliente da API é gerado do OpenAPI (`openapi-typescript` + `openapi-fetch`): ao mudar uma
rota do backend, rode `npm run atualizar-api` e commite `openapi.json` e `schema.d.ts` (o
CI confere os dois). A sessão fica no `sessionStorage` (some ao fechar o navegador) e o PWA
só guarda o app em cache, nunca dados da API.

O que dá para testar no navegador:

| Tela | Situação |
|---|---|
| Login com escolha de clínica, menu por papel, início (agenda do dia e alertas) | pronta |
| Pacientes: busca, cadastro/edição (responsável para menor), consentimentos LGPD, consultas do paciente | pronta |
| Agenda do dia por dentista: agendar (toque no horário), bloquear, confirmar, falta, cancelar, remarcar, iniciar atendimento | pronta |
| Alertas: lista por regra, dispensar/voltar a mostrar, configurar regras (admin/gestor) | pronta |
| Prontuário: anamnese (formulário do modelo publicado, alertas no cabeçalho), atendimentos com evolução, adendo, fechar e imprimir para assinar à mão | pronta |
| Odontograma 2D: marcação em 2 toques (item da legenda → face ou dente), remover tocando de novo, ver como estava numa data, vincular ao atendimento, arcada | pronta |
| Odontograma 3D (mesmos dados do 2D): faces pintadas pelos nós do .glb, dente ausente escondido, raízes opcionais, toque para marcar | pronta |
| Raio-X: anexar DICOM, lista com metadados, baixar o .dcm, invalidar | pronta |
| Planos e orçamentos: procedimentos da tabela, a fazer/feito no odontograma, desconto, emitir, decisão parcial, realizar no atendimento, duplicar, imprimir | pronta |
| Financeiro do paciente: extrato, parcelar orçamento aprovado, registrar recebimento | pronta |
| Gestão: visão geral (com comparação mês a mês, metas e alertas), equipe, tendências em gráficos (com tabela), metas; dentista vê o próprio desempenho | pronta |
| Precificação: tabelas (fixa, herdada com ajuste, calculada), versões, edição dos itens no rascunho, importação .csv/.xlsx com mapeamento, erros e diferenças, publicar, exportar .xlsx, atribuições e simulação com memória de cálculo | pronta |

## Testes

```sh
cd backend
pytest                         # unitários; os de integração são pulados sem banco
ruff check . && ruff format --check .
```

Os testes de integração (isolamento entre clínicas, login, auditoria) rodam quando
`TEST_DATABASE_URL` e `TEST_MIGRATIONS_DATABASE_URL` apontam para um banco de teste
(**ele é apagado e recriado a cada execução**). No GitHub Actions eles rodam sempre.

## Decisões de segurança da fundação

- **Isolamento por clínica com Row-Level Security.** A aplicação conecta com o role
  `odonto_app` (sem superusuário, sem `BYPASSRLS`, sem ser dono das tabelas). Toda tabela
  com `clinic_id` recebe a policy via `app.core.rls.enable_tenant_rls` na migração.
- **Acesso revogável na hora.** O token JWT identifica usuário e clínica, mas o papel
  e o vínculo ativo são conferidos no banco a cada requisição.
- **Auditoria append-only.** `audit_logs` não aceita UPDATE/DELETE pelo role da aplicação.
- **Senhas com argon2id.** O login leva o mesmo tempo para e-mail inexistente, para não
  revelar quais e-mails estão cadastrados.
