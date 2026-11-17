# Odonto System — Plano de Arquitetura e Produto

> Documento vivo. Registra a visão do produto, a arquitetura, a stack escolhida e o roadmap.
> Última atualização: 2026-11-16

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
| Arquivos | **S3-compatível** (AWS S3 / MinIO) | Upload direto via URL pré-assinada. |
| Auth | **Keycloak** (OIDC) ou fastapi-users + JWT | Controle de acesso por papéis (RBAC): dentista, ASB, recepção, gestor, admin. |
| Testes | pytest, factory-boy, Playwright (E2E) | |

Django + DRF foi considerado. FastAPI venceu porque o núcleo do sistema é uma API servindo um frontend rico, e porque a tipagem de ponta a ponta reduz bugs em dado clínico.

### Frontend

- **React + TypeScript + Vite**, entregue como **PWA**: instala no tablet e permite modo offline parcial no futuro.
- **TanStack Query** para dados do servidor e **Zustand** para estado local.
- **Tailwind + Radix/shadcn/ui**, com alvos de toque de no mínimo 44px e layout pensado para tablet na horizontal.
- **React Hook Form + Zod** para formulários.
- **AG Grid Community** ou **TanStack Table** para grades editáveis (tabelas de preço, estoque).

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
| **4 – Odontograma 3D** | Biblioteca GLB (FDI, decídua/permanente/mista, 0–4 sisos), sincronizada com o 2D |
| **5 – Inteligência** | Raio-X/DICOM no prontuário, alertas por regra + WhatsApp, painel do gestor com equipe completa, metas, alertas e tendências |
| **6 – IA** | Previsão de faltas e abandono, apoio à análise de raio-X |

**Próximo passo concreto:** validar o modelo de dados central antes das telas: Paciente, Atendimento, Evolução, EventoOdontograma, StatusLegenda, ItemPlanoTratamento e as entidades de precificação da seção 5.7.

---

## 9. Backlog / Stand-by

- **Escaneamento intraoral 3D do paciente**: em stand-by até a plataforma estar pronta. Os softwares dos próprios scanners oferecem hoje um suporte melhor a esses arquivos.
  - Até lá, os arquivos (STL/PLY/OBJ) podem ser guardados como **anexos** do paciente, sem visualizador.
  - Quando o tema for retomado, avaliar em fases: visualização ao lado do modelo genérico → marcação manual de pontos de referência dos dentes → segmentação automática por IA.
  - Observação: alguns scanners exportam em formato proprietário criptografado.
- **Modo offline** do PWA para o dia de atendimento.

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
| 2026-11-17 | Estoque mínimo (materiais com custo) criado antes da Fase 3 e consumido pela precificação só via `estoque.service` — primeira dependência entre módulos. Lotes, validade e baixa entram no mesmo módulo depois. |
| 2026-11-16 | Violação de constraint por concorrência (`IntegrityError`) responde 409 em toda a API, via handler global. |
| 2026-11-16 | Redis e object storage entram no compose só quando a Fase 1 precisar. Escolha do storage S3 local em aberto: a MinIO deixou de distribuir imagens da edição comunitária, então avaliar alternativas (ex.: Garage, SeaweedFS). |
