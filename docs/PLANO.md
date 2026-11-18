# Odonto System — Plano de Arquitetura e Produto

> Documento vivo. Registra a visão do produto, a arquitetura, a stack escolhida e o roadmap.
> Última atualização: 2026-11-18

## Sumário

1. [Visão do produto](#1-visão-do-produto)
2. [Arquitetura](#2-arquitetura)
3. [Stack tecnológica](#3-stack-tecnológica)
4. [Módulos](#4-módulos)
5. [Precificação — módulo-chave](#5-precificação--módulo-chave)
6. [Requisitos não funcionais](#6-requisitos-não-funcionais)
7. [Estrutura do repositório](#7-estrutura-do-repositório)
8. [Roadmap](#8-roadmap)
9. [Backlog / Stand-by](#9-backlog--stand-by)
10. [Decisões registradas](#10-decisões-registradas)

---

## 1. Visão do produto

Sistema web de gestão odontológica focado em:

- **Experiência clínica moderna**: uso fluido em tablet, na cadeira de atendimento.
- **Gestão estratégica do consultório**: precificação real, estoque e indicadores.
- **Personalização em alto nível**: a clínica configura tabelas, fórmulas, legendas e formulários **sem mexer em código**.

Módulos principais:

1. Prontuário digital (cadastro, anamnese, evolução clínica)
2. Odontograma interativo (2D + 3D genérico)
3. Gestão financeira, estoque e **precificação configurável**
4. Inteligência clínica (alertas, análise preditiva, raio-X)
5. Interface dedicada para tablet
6. **Painel do gestor** (acompanhamento da clínica e da equipe — seção 4.8)

Dois módulos ficaram de fora do levantamento inicial e foram incorporados porque ligam os demais:

- **Agenda**: os alertas de retorno, as faltas e a produtividade dependem dela.
- **Plano de tratamento e orçamento**: um achado no odontograma vira um item do plano, que vira orçamento, que vira lançamento financeiro e baixa de estoque.

---

## 2. Arquitetura

O sistema é um **monólito modular**, com **workers assíncronos** para o processamento pesado.

- Há um único backend Python, organizado em domínios com fronteiras claras.
- Microsserviços ficam fora até existir uma necessidade real. As fronteiras bem definidas permitem extrair um serviço depois.

```
┌──────────────────────────── Tablet / Desktop ─────────────────────────────┐
│  PWA React + TypeScript                                                   │
│  ├─ UI clínica (Tailwind + Radix/shadcn, otimizada para toque)            │
│  ├─ Odontograma 2D (SVG) + 3D genérico (React Three Fiber)                │
│  └─ Viewer de raio-X (Cornerstone3D)                                      │
└───────────────┬───────────────────────────────────────┬───────────────────┘
                │ REST/JSON (OpenAPI → cliente TS gerado) │ DICOMweb
┌───────────────▼───────────────────────┐   ┌───────────▼──────────────┐
│  API FastAPI (monólito modular)       │   │  Orthanc (PACS/DICOM)    │
│  pacientes · prontuario · odontograma │   └──────────────────────────┘
│  agenda · tratamento · financeiro     │
│  estoque · precificacao · imagens     │──── Redis (cache, filas)
│  inteligencia · auth                  │
└───────┬───────────────────┬───────────┘
        │                   │ tarefas
┌───────▼────────┐   ┌──────▼──────────────────────────────┐
│ PostgreSQL 16  │   │ Workers Celery                      │
│ (RLS por       │   │ · importação de planilhas           │
│  clínica)      │   │ · alertas de retorno / jobs de ML   │
└────────────────┘   │ · notificações (WhatsApp/e-mail)    │
                     └──────┬──────────────────────────────┘
                     ┌──────▼──────────────────────────┐
                     │ Object Storage S3 (MinIO no dev)│
                     │ anexos, raio-X, planilhas       │
                     └─────────────────────────────────┘
```

---

## 3. Stack tecnológica

### Backend (Python)

| Camada | Escolha | Motivo |
|---|---|---|
| Framework | **FastAPI** + Pydantic v2 | Tipado e assíncrono. Gera OpenAPI, do qual sai um cliente TypeScript tipado. |
| ORM / migrações | **SQLAlchemy 2.0** + Alembic | Maduro e adequado a um domínio complexo. |
| Banco | **PostgreSQL 16** | JSONB para formulários e campos configuráveis. Row-Level Security para multi-tenant. |
| Filas | **Celery + Redis** (+ Celery Beat) | Tarefas pesadas e agendadas. |
| Arquivos | Disco local no desenvolvimento; **S3-compatível** em produção (AWS S3 sa-east-1, Cloudflare R2, Backblaze B2, MinIO), trocado por configuração (`STORAGE_BACKEND`) | Já implementado em `app/core/storage.py`: mesma interface e mesmas chaves nos dois. URL pré-assinada fica para quando houver arquivos grandes. |
| Auth | **Keycloak** (OIDC) ou fastapi-users + JWT | Controle de acesso por papéis (RBAC): dentista, ASB, recepção, gestor, admin. |
| Testes | pytest, factory-boy, Playwright (E2E) | |

Django + DRF foi considerado. FastAPI venceu porque o núcleo do sistema é uma API servindo um frontend rico, e porque a tipagem de ponta a ponta reduz bugs em dado clínico.

### Frontend

- **React + TypeScript + Vite**, entregue como **PWA**: instala no tablet e permite modo offline parcial no futuro.
- **TanStack Query** para dados do servidor e **Zustand** para estado local.
- **Tailwind + Radix/shadcn/ui**, com alvos de toque de no mínimo 44px e layout pensado para tablet na horizontal.
- **React Hook Form + Zod** para formulários.
- **AG Grid Community** ou **TanStack Table** para grades editáveis (tabelas de preço, estoque).

#### O frontend em linguagem simples

Vite e PWA não são linguagens. A linguagem é uma só: **TypeScript** (JavaScript, a única
linguagem que o navegador entende, com tipos que dizem o formato de cada dado).

| Peça | O que é | Por que foi escolhida |
|---|---|---|
| **TypeScript** | A linguagem do frontend | Os tipos são gerados da própria API (`openapi.json`): se o backend muda um campo e o front não acompanha, o erro aparece antes de rodar, não na frente do dentista |
| **React** | Biblioteca para montar a tela em pedaços reutilizáveis (botão, cartão do paciente, dente) | A mais usada: mais exemplos, ajuda e bibliotecas prontas, inclusive a do 3D (React Three Fiber) |
| **Vite** | Ferramenta de trabalho: `npm run dev` abre o site e recarrega a cada mudança; `npm run build` gera os arquivos finais | Padrão atual para React, rápido e quase sem configuração; no desenvolvimento repassa `/api` para o backend |
| **PWA** | Site que pode ser "instalado" no tablet (ícone na tela inicial, tela cheia, como um app) | Atende ao uso em tablet sem fazer um app de loja (Android/iOS), que seria outro projeto, com outra linguagem e custo de publicação |
| **Tailwind** | Jeito de escrever o visual (cores, tamanhos) direto nos componentes | Facilita o modo claro/escuro e os botões grandes para toque |

Para testar não é preciso conhecer nada disso: com a API no ar, `npm run dev` na pasta
`frontend` (ou `.\dev.ps1 -Demo -Front` na raiz) e abrir http://localhost:5173. Para mexer no
código, o que vale aprender é TypeScript e React.

### 3D (odontograma genérico)

| Uso | Biblioteca |
|---|---|
| Renderização web | **Three.js via React Three Fiber + drei** |
| Formato servido | **glTF/GLB** com compressão Draco/meshopt |
| Modelagem | Blender: cada dente é uma malha nomeada pela **notação FDI**, e cada face é um submesh próprio |

### Imagens / Raio-X

- **Orthanc** (servidor DICOM / DICOMweb), **pydicom** e **Cornerstone3D** (ou OHIF).
- Aceita também JPEG/PNG exportados por sensores intraorais.

### Inteligência clínica

- **pandas, scikit-learn, LightGBM, lifelines** (análise de sobrevivência para retorno e abandono).
- **MLflow** quando houver modelos em produção.

### Observabilidade e infraestrutura

- Sentry e OpenTelemetry.
- Docker Compose para o desenvolvimento e GitHub Actions para CI.
- Hospedagem no Brasil (ex.: AWS sa-east-1).

---

## 4. Módulos

### 4.1 Prontuário digital

- Cadastro completo do paciente.
- **Anamnese configurável**: a clínica monta o próprio formulário, guardado em JSONB e versionado.
- **Evolução clínica imutável**: correções entram como adendos, nunca como edição. Cada evolução fica vinculada ao atendimento, ao dentista e à data.
- Anexos genéricos (PDF, imagens, STL etc.) no object storage.

### 4.2 Odontograma

- **Odontograma 2D (SVG)**: marcação rápida, em 2 toques, para o dia a dia na cadeira.
- **Odontograma 3D genérico**: visualização e **comunicação com o paciente**.
- Os dois leem e gravam o **mesmo modelo de dados**.
- **Arcadas montadas por composição.** Os dentes individuais (FDI 11–48 permanentes, 51–85 decíduos) são combinados conforme a configuração: dentição decídua, mista, ou permanente com 0 a 4 terceiros molares.
- **Marcação por face**: M, D, O/I, V, L/P.
- **Legenda de cores personalizável por clínica**, armazenada como dado. Cada status tem cor, ícone e tipo: patologia, planejado ou realizado.
- **Histórico por evento.** Cada marcação é um registro com data, autor e atendimento, o que permite ver o odontograma em qualquer data e comparar antes e depois.

### 4.3 Agenda

- Agenda por dentista, cadeira e unidade.
- Confirmação e lembretes (WhatsApp Business API / e-mail).
- Registro de faltas (no-show), que alimenta a inteligência clínica.

### 4.4 Plano de tratamento e orçamento

- Itens gerados a partir do odontograma.
- Preço resolvido pelo módulo de precificação (seção 5) e **congelado** no orçamento.
- Aprovação pelo paciente, que gera os lançamentos financeiros.

### 4.5 Financeiro e estoque

- Contas a receber e a pagar, parcelamento e formas de pagamento.
- **Estoque por lote e validade**, com rastreabilidade de implantes e materiais.
- **Ficha técnica por procedimento** (materiais × quantidade), com baixa automática do estoque ao realizar o procedimento.
- **Repasse/comissão de dentistas** usando o mesmo mecanismo de tabelas da precificação (seção 5.6).

### 4.6 Inteligência clínica

- **Fase inicial, alertas por regra**: "profilaxia há mais de 6 meses", "tratamento de canal sem retorno", "orçamento aprovado sem agendamento".
- **Fase posterior, ML**: previsão de faltas e de abandono de tratamento, quando já houver dados acumulados.
- Integração do raio-X ao prontuário, com metadados de dente, data e tipo (periapical, interproximal, panorâmica, tomografia).

### 4.7 UX/UI para tablet

- Fluxos de atendimento com o mínimo de digitação.
- Modo "cadeira": tela focada no paciente em atendimento, com odontograma, evolução e plano.
- Funciona em modo claro e escuro, com contraste adequado para o ambiente clínico.

### 4.8 Painel do gestor

> Um só painel que escala: no consultório de um dentista, é o "como está meu consultório hoje";
> numa clínica com vários dentistas e unidades, é onde o dono acompanha a equipe.
> A diferença é o nível de detalhe, não a ferramenta.

**Princípios**

- **Funciona sem configurar nada.** Os indicadores saem dos dados que a clínica já registra (agenda, orçamentos, financeiro, estoque). Metas são opcionais.
- **Começa pelo que pede ação**, não por gráficos: o que está atrasado, pendente ou acabando.
- **Escala por camadas.** Clínica pequena vê a visão geral. Com mais de um dentista ou unidade, aparecem os filtros e comparativos por profissional e por unidade.
- **Cada um vê o seu.** Admin e gestor veem a clínica inteira. O dentista vê "meu desempenho" (só os próprios números), o que também serve ao dono-dentista de um consultório pequeno.

**Visão geral (todas as clínicas, inclusive as pequenas)**

- Agenda do dia: atendimentos, confirmações pendentes, horários vagos.
- Faturamento do mês: realizado × previsto × meta (se houver).
- Orçamentos: emitidos, aprovados, aguardando resposta há mais de N dias.
- Pacientes para retorno (recall) e tratamentos parados.
- Contas a receber em atraso.
- Estoque: itens abaixo do mínimo e lotes perto do vencimento.

**Equipe (clínicas com vários profissionais)**

- Produção por dentista: procedimentos realizados e valor produzido.
- Conversão de orçamentos e ticket médio por dentista.
- Ocupação da agenda (por dentista e por cadeira) e faltas de pacientes.
- Tempo real × tempo previsto por procedimento (vem da ficha técnica da precificação).
- Margem por procedimento e por dentista (vem da precificação por custo).
- Repasse/comissão a pagar no período.
- Pendências clínicas: evoluções sem assinatura, prontuários incompletos.
- Comparativo entre unidades.

**Cuidados**

- **Acompanhamento, não vigilância.** O painel mostra indicadores de operação e resultado. A trilha de "quem fez o quê" continua na auditoria (LGPD), com acesso restrito. A equipe deve saber quais números são acompanhados.
- **Números explicáveis.** Todo indicador mostra de onde veio (ex.: "produção = procedimentos realizados no período, pelo preço congelado do orçamento").
- **Dados de pacientes agregados.** O painel não expõe dados clínicos individuais. Para ver um paciente, o gestor abre o prontuário, e esse acesso fica auditado.

**Como se encaixa na arquitetura**

- Módulo `painel` somente leitura, que consome os services dos outros módulos. Não tem tabelas próprias, exceto metas e preferências do painel.
- Agregações em SQL. Se houver *views*, elas são criadas com `security_invoker = true`: por padrão, uma view do PostgreSQL roda com os privilégios do dono e **ignora o RLS**. *Materialized views* não aplicam RLS e ficam fora; cache, se necessário, vai para Redis com chave por clínica.
- Entra em versões: v1 com a visão geral assim que agenda, orçamento e financeiro existirem (Fase 3); a parte de equipe evolui junto com repasse e precificação por custo; alertas e tendências chegam com a inteligência clínica (Fase 5).

---

## 5. Precificação — módulo-chave

> O sistema não "tem" uma tabela de preços. Ele tem um **mecanismo de tabelas**: a clínica cria quantas quiser, atribui a quem quiser e define as regras de cálculo, tudo pela interface e sem código.

### 5.1 Conceitos

| Conceito | Descrição |
|---|---|
| **Tabela de Preço** | Conjunto versionado de itens. Tipo: **preço fixo** ou **calculado por fórmula**. Tem vigência (início/fim) e status (rascunho → ativa → arquivada). |
| **Atribuição (escopo)** | A quem a tabela se aplica: clínica, unidade, **dentista**, convênio ou campanha. Uma tabela pode ser atribuída a vários escopos. |
| **Herança** | Uma tabela pode derivar de outra. Ex.: "Tabela Dr. Carlos = Tabela Base + 15%, exceto implantes (valor próprio)". |
| **Item** | Código do procedimento, descrição, categoria, preço *ou* parâmetros de custo (tempo, materiais), e **campos extras definidos pela clínica**. |
| **Regras de ajuste** | Desconto à vista, acréscimo no parcelamento, arredondamento (",90" ou múltiplo de 10), piso mínimo. |
| **Perfil de importação** | Mapeamento salvo de "coluna da planilha → campo do sistema", reutilizável. |

### 5.2 Resolução do preço

No orçamento, o preço de cada item segue uma **cadeia de prioridade configurável pela clínica**. Padrão sugerido:

```
Convênio do paciente → Tabela do dentista → Tabela da unidade → Tabela padrão da clínica
```

- A resolução é **por item**. Se o procedimento não existe na tabela do dentista, o sistema cai para a próxima da cadeia.
- **Regra inegociável:** o orçamento **congela** o preço, a tabela, a versão e a memória de cálculo usadas. Uma mudança posterior na tabela não altera orçamentos já emitidos.

### 5.3 Importação de CSV/Excel

```
Upload → Detecção → Mapeamento → Validação/Prévia → Diff → Publicar versão
```

1. **Upload** de `.csv`, `.xlsx` ou `.xls`, com escolha da aba.
2. **Detecção automática** de encoding (UTF-8 ou Latin-1), separador (`;` ou `,`) e formato numérico brasileiro (`1.234,56`, `R$ 150,00`).
3. **Mapeamento de colunas** em tela, com sugestão automática pelo nome do cabeçalho. Colunas que não correspondem a nenhum campo podem virar **campos personalizados**. O mapeamento é salvo como perfil.
4. **Prévia com validação linha a linha.** Ex.: "linha 47: preço vazio", "linha 52: código duplicado". O usuário escolhe ignorar as linhas com erro ou corrigir e reenviar.
5. **Diff contra a versão atual**: itens novos, alterados (valor antigo → novo) e removidos.
6. **Publicação** como nova versão: imediata, como rascunho ou agendada para uma vigência futura.

Complementos:

- **Exportação** da tabela atual para Excel, para o fluxo editar e reimportar.
- **Planilha-modelo** para download, com as colunas esperadas e exemplos.
- Arquivos grandes são processados em segundo plano (Celery), com progresso visível.

### 5.4 Fórmulas configuráveis

As tabelas calculadas usam **variáveis nomeadas**. Algumas são do sistema, outras são criadas pela clínica:

```
custo_materiais = soma(ficha técnica × custo do insumo no estoque)
custo_hora      = custos_fixos_mensais / horas_produtivas_mes
custo_clinico   = custo_hora × tempo_horas
pro_labore      = valor fixo ou % (configurável por dentista)

preco = (custo_materiais + custo_clinico + pro_labore) / (1 − impostos − taxa_cartao − margem)
```

- **O padrão é o "preço por dentro".** Impostos, taxa de cartão e margem incidem sobre o preço de venda, não sobre o custo. Somar percentuais ao custo subprecifica.
- **As fórmulas são avaliadas com segurança**, por um interpretador restrito com variáveis e funções em lista branca. **Nunca com `eval()`.**
- **O editor de fórmulas** tem autocompletar das variáveis e um "testar com o procedimento X", que mostra a memória de cálculo passo a passo.
- **Parâmetros por dentista**: pró-labore, margem e hora clínica próprios, aplicados sobre a mesma ficha técnica.

### 5.5 Permissões

- Quem pode criar, editar e publicar tabelas é configurável por papel.
- A visibilidade de custos e margens é configurável. Ex.: o dentista vê só o preço final, e o gestor vê a composição completa.
- Toda publicação de versão fica auditada, com quem publicou, quando e o arquivo de origem.

### 5.6 Repasse / comissão de dentistas

O repasse (percentual ou valor fixo por procedimento e por dentista, opcionalmente descontando material e taxa de cartão) usa **o mesmo mecanismo**: tabelas, atribuição por dentista, importação de planilha e fórmulas.

### 5.7 Modelo de dados (núcleo)

```
price_table          (id, clinic_id, name, kind[fixed|formula], parent_table_id,
                      inherit_rule jsonb, status, created_by)
price_table_version  (id, table_id, version, valid_from, valid_to, source_file_id,
                      published_at, published_by)
price_item           (id, version_id, procedure_code, description, category,
                      price numeric(12,2) null, params jsonb, custom_fields jsonb)
price_assignment     (id, table_id, scope_type[clinic|unit|dentist|insurer], scope_id, priority)
pricing_formula      (id, clinic_id, name, expression, variables jsonb)
pricing_variable     (id, clinic_id, key, value, scope_type, scope_id)
import_profile       (id, clinic_id, name, column_map jsonb, parse_options jsonb)
import_job           (id, file_id, profile_id, status, report jsonb)
quote_item           (..., unit_price, price_table_version_id, calc_trace jsonb)
```

### 5.8 Bibliotecas

| Necessidade | Biblioteca |
|---|---|
| Leitura de Excel e CSV | **pandas** + **python-calamine** |
| Geração de Excel (exportação e modelo) | **openpyxl** |
| Detecção de encoding | **charset-normalizer** |
| Validação de linhas | **Pydantic v2** |
| Fórmulas seguras | **simpleeval** (lista branca) |
| Dinheiro | `decimal.Decimal` em todo o fluxo; `numeric(12,2)` no Postgres |

---

## 6. Requisitos não funcionais

- **LGPD**: dado de saúde é dado sensível.
  - Consentimento registrado.
  - Criptografia em trânsito e em repouso.
  - **Log de auditoria de quem acessou cada prontuário.**
  - Dados hospedados no Brasil.
- **Prontuário eletrônico (CFO)**: para dispensar o papel, exige assinatura digital **ICP-Brasil** e guarda de longo prazo. Por isso as evoluções clínicas são imutáveis.
- **Multi-tenant**: isolamento por clínica via `clinic_id` + Row-Level Security no PostgreSQL.
- **Backups**: backups do Postgres automatizados e **restaurados periodicamente em teste**.
- **Desempenho no tablet**: carregamento inicial enxuto, modelos 3D comprimidos e cache via PWA.
- **Segurança de acesso: pendências antes de produção** (levantadas na documentação de [identidade](tecnico/identidade.md)):
  - **Proteção contra força bruta no login**: hoje não há limite de tentativas. Avaliar rate limit por IP + e-mail e bloqueio temporário após falhas seguidas.
  - **Auditoria de login com falha**: só o login bem-sucedido é registrado, porque `audit_logs` exige `clinic_id`. Definir onde gravar tentativas falhas (ex.: tabela global de eventos de segurança, sem dados de clínica).
  - **CLI `criar-clinica` com e-mail já cadastrado**: o usuário existente é reaproveitado e a senha digitada é **ignorada sem aviso**. Avisar e exigir confirmação explícita para vincular o usuário existente.
  - **Recuperação de senha**: não existe. Hoje depende de intervenção manual.
  - **Política de senha**: o mínimo de 10 caracteres só é validado na CLI. Centralizar a regra quando houver cadastro e troca de senha pela API.

---

## 7. Estrutura do repositório

```
odonto-system/
├─ backend/
│  ├─ app/
│  │  ├─ core/            # config, db, auth, tenancy, auditoria
│  │  ├─ modules/
│  │  │  ├─ pacientes/
│  │  │  ├─ prontuario/
│  │  │  ├─ odontograma/
│  │  │  ├─ agenda/
│  │  │  ├─ tratamento/
│  │  │  ├─ financeiro/
│  │  │  ├─ estoque/
│  │  │  ├─ precificacao/
│  │  │  ├─ imagens/
│  │  │  ├─ inteligencia/
│  │  │  └─ painel/       # painel do gestor (somente leitura)
│  │  │     (cada módulo: models.py, schemas.py, service.py, router.py)
│  │  └─ workers/         # tarefas Celery
│  ├─ alembic/
│  └─ tests/
├─ frontend/              # React + Vite PWA
├─ assets-3d/             # fontes .blend + GLBs exportados
├─ docs/                  # documentação (este arquivo)
└─ docker-compose.yml     # postgres, redis, minio, orthanc, api, worker
```

---

## 8. Roadmap

| Fase | Escopo |
|---|---|
| **0 – Fundação** | Monorepo, Docker Compose, auth + RBAC, multi-tenant com RLS, auditoria, CI |
| **1 – Precificação** | Tabelas versionadas, importação CSV/Excel com mapeamento e diff, cadeia de prioridade, fórmulas com memória de cálculo, exportação |
| **2 – MVP clínico** | Pacientes, anamnese configurável, evolução clínica, agenda, odontograma 2D, legenda personalizável |
| **3 – Gestão** | Plano de tratamento → orçamento → financeiro; estoque por lote; ficha técnica; repasse de dentistas; **painel do gestor v1** (visão geral e "meu desempenho") |
| **4 – Odontograma 3D** | Biblioteca GLB (FDI, decídua/permanente/mista, 0–4 sisos), sincronizada com o 2D — **backend concluído** (arcada por paciente, GLB gerado por código, visualização 2D/3D, comparação antes/depois); visualizador espera o frontend |
| **5 – Inteligência** | Raio-X/DICOM no prontuário, alertas por regra, painel do gestor com equipe completa, metas, alertas e tendências — **backend concluído** (alertas calculados na hora e configuráveis por clínica, painel com equipe/metas/tendências, exames DICOM com metadados via pydicom); WhatsApp em stand-by (pago); visualizador DICOM e Orthanc depois |
| **Frontend** | React + Vite PWA em `frontend/`, construído em partes (2026-11-18): base/login/menu, pacientes e agenda, alertas, prontuário (anamnese, atendimento, evolução, raio-X), odontograma 2D e 3D, planos e financeiro do paciente, gestão (painel, equipe, tendências, metas) e precificação (tabelas, importação, atribuições, simulação). Falta: editor de modelos de anamnese, editor visual de fórmulas/fichas técnicas, legenda do odontograma, contas a pagar, repasse, estoque, cadastro de equipe e testes E2E (Playwright) |
| **6 – IA** | Previsão de faltas e abandono, apoio à análise de raio-X |

**Próximo passo concreto:** validar o modelo de dados central antes das telas: Paciente, Atendimento, Evolução, EventoOdontograma, StatusLegenda, ItemPlanoTratamento e as entidades de precificação da seção 5.7.

---

## 9. Backlog / Stand-by

- **Escaneamento intraoral 3D do paciente**: em stand-by até a plataforma estar pronta. Os softwares dos próprios scanners oferecem hoje um suporte melhor a esses arquivos.
  - Até lá, os arquivos (STL/PLY/OBJ) podem ser guardados como **anexos** do paciente, sem visualizador.
  - Quando o tema for retomado, avaliar em fases: visualização ao lado do modelo genérico → marcação manual de pontos de referência dos dentes → segmentação automática por IA.
  - Observação: alguns scanners exportam em formato proprietário criptografado.
- **Gengiva no modelo 3D** (pedido após o teste da Fase 4, 2026-11-18): as raízes geradas
  por código ficaram feias quando expostas.
  - Gerar uma malha de gengiva por arcada (superior e inferior), acompanhando a curva e só
    os dentes presentes do paciente, como nó próprio (`gengiva_superior`/`gengiva_inferior`).
  - Raízes ficam **dentro** da gengiva. Gengiva translúcida ou removível pelo usuário, para
    ver as raízes quando quiser (ex.: explicar um canal ao paciente).
  - Junto: raízes mais realistas (mais grossas, ápice arredondado em vez de ponta).
  - Alternativa a avaliar: modelos prontos (Blender/artista ou com licença livre de uso
    comercial), mantendo os nomes de nós e a orientação já documentados.
- **WhatsApp (lembretes e alertas)**: em stand-by — a API oficial (WhatsApp Business) é
  paga e o projeto não tem integrações pagas por enquanto. Os alertas da Fase 5 ficam
  dentro do sistema; o consentimento `comunicacao` do paciente já existe para quando
  o envio for retomado (avaliar também e-mail, que é gratuito).
- **Raio-X, próximos passos**: visualizador DICOM no navegador (Cornerstone3D), Orthanc
  como PACS (DICOMweb), tomografia com várias fatias por estudo, JPEG/PNG de sensores
  intraorais e armazenamento S3 no lugar do disco local.
- **Modo offline** do PWA para o dia de atendimento.
- **Assinatura ICP-Brasil das evoluções**: em stand-by (o projeto ainda é um modelo, sem
  integrações pagas). Hoje a evolução tem assinatura eletrônica simples + hash do conteúdo,
  e a tabela `clinical_note_signatures` já tem campos para o certificado. Enquanto isso,
  quando precisar, o prontuário é **impresso e assinado à mão** (prever a impressão nas
  telas). Quando retomado: provedor de assinatura em nuvem (ex.: BirdID, VIDaaS) com e-CPF
  de cada dentista.

---

## 10. Decisões registradas

| Data | Decisão |
|---|---|
| 2026-11-16 | Arquitetura em monólito modular (FastAPI) + workers Celery. |
| 2026-11-16 | Odontograma com duas visões (2D para registro rápido e 3D genérico para visualização) sobre o mesmo modelo de dados. |
| 2026-11-16 | Escaneamento intraoral 3D movido para stand-by (pós-plataforma). |
| 2026-11-16 | Precificação como módulo-chave: tabelas versionadas, importação CSV/Excel, atribuição por dentista, fórmulas configuráveis sem código. |
| 2026-11-16 | Repasse de dentistas reaproveita o mecanismo de tabelas da precificação. |
| 2026-11-16 | Fundação: a aplicação conecta com role sem `BYPASSRLS` e sem ser dona das tabelas; migrações rodam com o role dono. |
| 2026-11-16 | Papel e vínculo do usuário são conferidos no banco a cada requisição (revogação imediata), não só no JWT. |
| 2026-11-16 | Referências entre tabelas da mesma clínica usam FK composta `(id, clinic_id)`: a checagem de FK do PostgreSQL ignora o RLS e, com FK simples, permitiria apontar para registro de outra clínica. |
| 2026-11-16 | Toda restrição de unicidade de tabela de clínica inclui `clinic_id`: a checagem de unicidade também ignora o RLS e, sem isso, uma clínica poderia sondar a existência de registros de outra pela mensagem de erro. |
| 2026-11-16 | Precificação: herança com ajuste percentual na versão (não na tabela), arredondamento em centavos (meio para cima) a cada nível; "dentista" de uma atribuição pode ser membro com papel dentista ou admin (dono-dentista). |
| 2026-11-16 | Precificação: herança resolvida na consulta (não materializada). A imutabilidade de versões publicadas fica no service; no banco, só `price_snapshots` é protegida, porque o snapshot copia valores e memória de cálculo. |
| 2026-11-16 | Importação de planilhas: `.csv` e `.xlsx` (sem `.xls`), processamento síncrono (até 2 MB / 5.000 linhas, sem fila). O arquivo não é guardado: as linhas lidas ficam no banco com nome e hash para auditoria, e são descartadas depois de aplicadas. |
| 2026-11-16 | Importação grava só no rascunho, nunca publica. Antes de gravar, confere uma impressão digital do rascunho/versão de referência; se mudou desde a validação, exige validar de novo. Job e tabela travados (`FOR UPDATE`) durante a aplicação. |
| 2026-11-16 | Corpo de requisição limitado a 3 MB na própria aplicação (o Starlette grava uploads em disco antes da rota); o proxy em produção também deve limitar. |
| 2026-11-16 | Painel do gestor: um só painel para clínica pequena e grande, escalando por camadas; dentista vê só os próprios números. Módulo somente leitura; views com `security_invoker = true` e sem materialized views, para não contornar o RLS. |
| 2026-11-17 | Precificação por custo: a tabela calculada gera itens comuns no rascunho (a resolução de preço não muda), com a fórmula versionada na versão e um hash dos insumos (fórmula, variáveis, fichas, custos) conferido na publicação. Fórmulas avaliadas por interpretador próprio sobre `ast` com lista branca, em `Decimal`. |
| 2026-11-17 | Tabela calculada cujo último recálculo deixou procedimentos de fora por erro só publica com `confirmar_erros` (409 lista os procedimentos, que na resolução cairiam para a próxima tabela). Os erros ficam na versão (`calc_errors`), copiados para o novo rascunho e limpos junto com o cálculo quando a fórmula muda. |
| 2026-11-17 | Fase 2, ordem: pacientes → agenda → anamnese → atendimento + evolução → odontograma. Atendimento é entidade própria (agendamento opcional, cobre encaixe e urgência). Recepção vê cadastro e agenda, não o conteúdo clínico; ASB lê o prontuário e marca odontograma, mas não escreve evolução; evolução e adendo só pelo dentista autor. Evolução retroativa até 7 dias, guardando também a data real do registro. Agenda v1: conflito por dentista e por cadeira, bloqueios de horário sim, expediente depois, sem encaixe por cima. Anamnese respondida é imutável (nova resposta vira a atual). Legenda padrão do odontograma criada para cada clínica. |
| 2026-11-17 | Gestor lê o conteúdo clínico (com auditoria de acesso). O prontuário é compartilhado entre os dentistas da clínica; o que é individual são os números de desempenho no painel. Cada pessoa tem login próprio (nada de conta compartilhada): o dono-dentista usa um único acesso com papel admin, que vale como dentista. |
| 2026-11-17 | Pacientes: nome e telefone obrigatórios; CPF opcional, validado e único por clínica quando informado; menor de 18 anos exige responsável e consentimento dado por ele. Sem exclusão (só desativar), pela guarda mínima de 20 anos do prontuário. Sem criptografia por coluna na v1 (impediria a busca por trecho do nome): disco/backup criptografados, RLS e auditoria de acesso. Leitura auditada (ficha, consentimentos e busca, esta sem guardar o termo); a auditoria guarda nomes de campos, não valores. Consentimentos LGPD append-only. |
| 2026-11-17 | Agenda: consultas e bloqueios na mesma tabela, para que as constraints de exclusão (`EXCLUDE USING gist`, com `btree_gist` e `clinic_id`) impeçam conflito entre eles por dentista e por cadeira; falta e cancelamento liberam o horário. A consulta prévia no service só dá a mensagem amigável; o banco é a garantia. Leitura da agenda não é auditada (sem conteúdo clínico); escritas e histórico de eventos (append-only, um evento por requisição) sim. |
| 2026-11-17 | Anamnese (módulo `prontuario`): modelos por clínica com versões rascunho → publicada → substituída (um rascunho e uma publicada por modelo); perguntas em JSONB tipadas (texto, sim/não, escolha única, múltipla, número, data), com obrigatória e alerta. Versão publicada congelada por gatilho no banco (não muda, não é apagada). Resposta append-only, ligada à versão publicada exibida (versão desatualizada → 409); a mais recente de cada modelo é a atual e os alertas dela vão para o cabeçalho do paciente. Recepção sem acesso; ASB, gestor, dentista e admin leem (auditado); dentista, ASB e admin preenchem; admin e gestor montam e publicam. |
| 2026-11-17 | Atendimento e evolução (módulo `prontuario`): atendimento aberto pelo dentista (ou admin) que atende; vindo da agenda, o agendamento vira atendido (só após o início; agendamento de outro dentista é aceito, para substituição); um atendimento por agendamento. Evolução e adendo append-only, só pelo autor; fechado o atendimento, só adendo. Data do ato clínico até 7 dias para trás, com a data real do registro guardada. Cada registro tem SHA-256 canônico do conteúdo e assinatura eletrônica simples em tabela própria, pronta para ICP-Brasil. Gatilhos no banco reforçam autoria, atendimento aberto, imutabilidade do atendimento fechado e coerência da assinatura com o conteúdo. |
| 2026-11-17 | Odontograma 2D (módulo `odontograma`): legenda por clínica (cor, tipo patologia/planejado/realizado, escopo dente inteiro ou por face), criada com a legenda padrão no primeiro uso e editável por admin e gestor; tipo, escopo e código não mudam depois de usados, e item não se apaga, só se desativa. Marcações são eventos append-only (marcar/remover) em lote atômico, por dente FDI (11–48, 51–85) e face (M, D, O/I, V, L/P; gravadas como M, D, O, V, L), com atendimento aberto opcional. O odontograma em qualquer data é reconstruído pelos eventos, ordenados por `clock_timestamp()` com as escritas serializadas por paciente. Marcam: dentista, admin e ASB; leem também o gestor (auditado); recepção sem acesso. |
| 2026-11-17 | Atendimento sem dono (dentista saiu ou de férias): o admin transfere o atendimento aberto para outro dentista, com motivo. Transferência append-only (`encounter_transfers`); o gatilho só deixa o dentista do atendimento mudar com ela registrada na mesma transação. Evoluções anteriores continuam do autor original. |
| 2026-11-17 | Plano de tratamento e orçamento (módulo `tratamento`): plano e orçamento são a mesma entidade (rascunho → emitido → aprovado/recusado → concluído; cancelado). Dentista e admin montam; dentista, admin, gestor e recepção emitem, dão desconto e registram a decisão. Desconto percentual sobre o total, até o limite da clínica (5% padrão) para dentista e recepção; acima, admin ou gestor. Validade padrão de 30 dias, configurável. Na emissão o preço de cada item é congelado via `price_snapshots` (tabela, versão e memória de cálculo); vencido, duplica e emite de novo. Aprovação parcial por item. Item realizado só pelo dentista do atendimento aberto, e atualiza o odontograma (tira o 'a fazer', marca o 'feito'). Gatilhos congelam preço, desconto e status finais. |
| 2026-11-17 | Financeiro (módulo `financeiro`): registro manual, sem gateway (o projeto é um modelo). O orçamento aprovado é parcelado à parte em entrada + parcelas mensais (centavos da divisão na 1ª parcela; vencimento no mesmo dia, ou no fim do mês); um parcelamento ativo por orçamento, refeito só sem recebimentos. Recebimentos append-only, parciais permitidos, taxa de cartão informada no registro; correção por estorno (lançamento negativo, uma vez por recebimento). Status da conta calculado dos recebimentos. Caixa: admin, gestor e recepção; estorno, cancelamento e contas a pagar: admin e gestor; dentista e ASB fora. Gatilhos mantêm o recebido entre zero e o valor, congelam conta com recebimento e conta a pagar paga ou cancelada. |
| 2026-11-17 | Estoque por lote: cada entrada cria um lote (código e validade opcionais, custo da compra); saldo = soma dos movimentos append-only (entrada, consumo, saída manual, ajuste de inventário), nunca negativo (gatilho). Custo do material = média ponderada dos lotes em estoque, recalculada a cada entrada (alimenta a precificação). ASB dá entrada sem informar custo; admin e gestor informam. Ao realizar item do plano, os materiais da ficha técnica saem pelo lote que vence primeiro (FEFO), sem usar lote vencido; falta de material não bloqueia o procedimento e vira aviso. Consumo fica ligado ao paciente e ao item (rastreabilidade de implantes). Alertas: abaixo do mínimo e lote vencido ou vencendo em 30 dias. |
| 2026-11-17 | Repasse (módulo `repasse`): sobre o recebido. Base de cada item realizado = valor líquido do item × fração já paga do plano até a data. Cálculo acumulado: cada fechamento leva só a diferença do já repassado (estorno depois do fechamento gera linha negativa). Regra por dentista, geral ou por procedimento, com vigência: percentual (descontos opcionais de taxa de cartão e materiais consumidos) ou valor fixo por procedimento (proporcional ao pago, sem descontos). Regras e fechamentos append-only; fechamento por dentista até uma data ≤ hoje. Admin e gestor fecham; o dentista vê só o próprio. Diferente do PLANO 5.6 original (mesmo mecanismo das tabelas de preço): regras próprias, mais simples, bastam por ora. |
| 2026-11-17 | Painel do gestor v1 (módulo `painel`): só leitura, sem tabelas, SQL agregado na sessão de tenant (sem views). Visão geral (admin e gestor): agenda de hoje, recebido/líquido/previsto do mês, contas a receber vencidas, contas a pagar vencidas e a vencer em 7 dias, orçamentos aguardando (e há mais de 7 dias), aprovados no mês, produção por dentista e alertas de estoque. "Meu desempenho" (dentista e admin): os próprios números e o último repasse. Datas no fuso da clínica. Sem auditoria de leitura: só agregados, nenhum dado individual de paciente. Fase 3 concluída no backend. |
| 2026-11-17 | Fase 4, arcada do paciente (módulo `odontograma`): dentição permanente, decídua ou mista, com 0 a 4 sisos ou lista explícita de dentes FDI; append-only, a mais recente vale e pode ser vista em qualquer data. Sem registro, sugerida pela idade (até 5 anos decídua, 6–11 mista típica, 12–17 permanente sem sisos, adulto ou sem data de nascimento 32 dentes). Decíduo e sucessor permanente não ocupam a mesma vaga. A arcada descreve a dentição; dente perdido continua sendo a marcação "ausente". Marcam: admin, dentista e ASB. |
| 2026-11-17 | Fase 4, biblioteca 3D: GLB **gerado por código** no backend (gravador glTF próprio, sem dependência e sem binário no repositório), determinístico, com ETag e cache. Cada dente é `dente_<fdi>` com um nó por face (`<fdi>_M/_D/_O/_V/_L`) e `<fdi>_raiz`; formas simplificadas por tipo (incisivo, canino, pré-molar, molar) e medidas médias. Arcada montada por composição (parábola por arcada, decíduos na vaga do sucessor, arcada decídua menor). Rotas `/odontograma/3d/*` exigem login mas não abrem sessão de clínica nem são auditadas (sem dado de paciente). Modelos do Blender podem substituir o gerador mantendo nomes e orientação. |
| 2026-11-17 | Fase 4, sincronização 2D/3D: uma só resposta (`/visualizacao`) serve as duas visões, com arcada, as cinco faces de cada dente (nó da malha, cor e marcações) e a posição na arcada. Cor: item da face, senão o do dente inteiro; prioridade patologia > planejado > realizado. Item da legenda ganhou efeito 3D (`colorir` ou `ocultar`, este só para dente inteiro; "ausente" oculta). Comparação antes/depois entre duas datas pelos eventos. Leitura auditada como o odontograma. |
| 2026-11-18 | Fase 5.1, alertas por regra (módulo `inteligencia`): calculados na hora a partir de agenda, plano de tratamento, atendimentos e financeiro, sem tabela de alertas. O catálogo de regras fica no código (profilaxia atrasada, canal sem retorno, orçamento aprovado sem agendamento, orçamento sem resposta, atendimento aberto, faltas repetidas, conta em atraso); a clínica liga/desliga e muda os parâmetros (`alert_rule_settings`). Cada regra tem os papéis que a veem (recepção não vê alerta clínico; dentista e ASB não veem financeiro). Dispensar "até tal data" é append-only (`alert_dismissals`); voltar a mostrar é um registro novo. Listagem auditada (traz nome e telefone); resumo só com contagens. Sem envio externo: WhatsApp em stand-by. |
| 2026-11-18 | Fase 5.2, painel completo: metas mensais opcionais (`panel_goals`, única escrita do módulo, unicidade com `NULLS NOT DISTINCT`) da clínica ou por dentista para recebido (só clínica), produção, procedimentos e valor aprovado; equipe com conversão (aprovados ÷ decididos), ticket médio, faltas e metas; tendências mês a mês com variação; visão geral e meu desempenho com comparativo, metas e contagem de alertas. Indicadores recalculados a cada consulta (sem cache). |
| 2026-11-18 | Fase 5.3, raio-X simples (módulo `imagens`): só DICOM, um arquivo por envio (até 30 MB, limite próprio só nessa rota), metadados lidos com pydicom sem os pixels, tipo sugerido pela modalidade (PX panorâmica, IO periapical, CT tomografia). Arquivo em disco local por clínica com chave gerada pelo servidor (`app.core.storage`, interface pronta para S3), download só pela API, auditado. Arquivo, paciente e metadados imutáveis (gatilho), sem exclusão: envio errado é invalidado com motivo. Sem Orthanc e sem visualizador por enquanto. |
| 2026-11-18 | Kit de teste local: `dev.ps1` (migra e sobe a API), `python -m app.cli demo` (dados de demonstração idempotentes, recusado em produção) e `testes.ps1` com banco `odonto_test` local. |
| 2026-11-18 | Frontend: React 19 + Vite + TypeScript, TanStack Query, React Router, Zustand só para a sessão. Componentes próprios com Tailwind 4 (alvos de toque ≥ 44px, claro/escuro por tokens) em vez de Radix/shadcn, para não depender de gerador. Cliente gerado do OpenAPI com openapi-typescript + openapi-fetch; `openapi.json` e `schema.d.ts` versionados e conferidos no CI. Sessão no `sessionStorage` (some ao fechar o navegador, tablet compartilhado) e PWA que guarda só o app, nunca dados da API. Em dev o Vite repassa `/api` para a API (sem CORS). 3D com React Three Fiber carregado sob demanda; o GLB é baixado com o token e pintado pelos nomes dos nós. TypeScript 5.9 até o ecossistema aceitar o 6/7. |
| 2026-11-18 | `GET /auth/equipe`: nome, papel e CRO dos membros ativos da clínica (sem e-mail), para o front escolher dentista. |
| 2026-11-18 | Financeiro do paciente para o dentista: **parametrizável por clínica**. O admin ou gestor liga a opção (`financial_settings.dentist_can_view`, desligada por padrão, auditada; tela Gestão → Configurações) e o dentista passa a **ler** o extrato de qualquer paciente da clínica (mesmo escopo do prontuário, que é compartilhado). Receber, parcelar, estornar e contas a pagar continuam só com o caixa; ASB continua sem acesso. |
| 2026-11-18 | `GET /auth/equipe` (nome, papel e CRO dos membros ativos, sem e-mail) fica visível a todos os papéis da clínica. |
| 2026-11-18 | Armazenamento de arquivos preparado para nuvem sem custo agora: dois backends com a mesma interface e as mesmas chaves (`<clinica>/<uuid>.<ext>`). Hoje `local` (disco); em produção `s3`, que serve a qualquer provedor compatível (AWS S3 em sa-east-1 pela LGPD, Cloudflare R2, Backblaze B2), com bucket privado, criptografia no servidor (SSE) e acesso só pela API. Migrar = copiar os arquivos mantendo as chaves e mudar `STORAGE_BACKEND`; `boto3` é dependência opcional (`.[s3]`). Isso fecha a escolha "storage S3 local" deixada em aberto em 2026-11-16: no desenvolvimento, disco local basta. |
| 2026-11-17 | Estoque mínimo (materiais com custo) criado antes da Fase 3 e consumido pela precificação só via `estoque.service` — primeira dependência entre módulos. Lotes, validade e baixa entram no mesmo módulo depois. |
| 2026-11-16 | Violação de constraint por concorrência (`IntegrityError`) responde 409 em toda a API, via handler global. |
| 2026-11-16 | Redis e object storage entram no compose só quando a Fase 1 precisar. Escolha do storage S3 local em aberto: a MinIO deixou de distribuir imagens da edição comunitária, então avaliar alternativas (ex.: Garage, SeaweedFS). |
| 2026-11-18 | Cor da legenda em dois níveis: a da clínica (admin/gestor) e uma pessoal por usuário (`tooth_status_user_colors`), resolvida no backend; o RLS isola por clínica e a separação por usuário é feita na aplicação. |
| 2026-11-18 | Anotações por dente em tabela própria e append-only (`tooth_notes`), separadas do histórico de marcações; corrige-se com uma anotação nova. |
| 2026-11-18 | Item da legenda tem região (coroa ou raiz; raiz só em item de dente inteiro). A visualização pinta em camadas: raiz com o item mais importante da raiz, coroa com o da coroa, e faces marcadas por cima. |
