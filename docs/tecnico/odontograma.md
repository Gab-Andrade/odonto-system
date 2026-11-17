---
modulo: odontograma
atualizado_em: 02cafc0
---
# Odontograma

> Legenda de marcações por clínica e histórico append-only de marcações por paciente, de onde o odontograma de qualquer data é reconstruído.

## Responsabilidades

- Legenda da clínica (`tooth_statuses`): itens com cor, tipo (patologia, planejado, realizado) e escopo (dente inteiro ou face).
- Marcar e remover itens em dentes/faces de um paciente, em lotes, opcionalmente vinculados a um atendimento aberto.
- Consultar o odontograma atual ou "como estava em" um momento, e o histórico de eventos.
- **Fora do módulo:** cadastro do paciente (`pacientes`), atendimento e evolução (`prontuario`; aqui só se referencia `encounters`), plano de tratamento e preço dos procedimentos. Item "planejado" é só marcação visual; não gera orçamento.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `tooth_statuses` | sim | Legenda da clínica |
| `odontogram_events` | sim | Eventos marcar/remover, append-only |

- `odontogram_events` não tem estado: não existe "marcação atual" gravada. O estado é sempre derivado dos eventos (`regras.py:rebuild`).
- Append-only: a migração 0011 revoga UPDATE/DELETE/TRUNCATE do `odonto_app` em `odontogram_events`. Em `tooth_statuses` revoga só DELETE/TRUNCATE (itens são desativados, não apagados).
- FKs compostas com `clinic_id` garantem que paciente, item da legenda e atendimento sejam da mesma clínica; o atendimento ainda precisa ser do mesmo paciente (`fk_odontogram_events_encounter_same_patient`).
- CHECKs: dente FDI (11-48 com posição 1-8; 51-85 com posição 1-5), face em M/D/O/V/L, cor `#RRGGBB` maiúscula, código `[a-z0-9_]{1,40}`.
- Gatilhos (migração 0011, `check_violation`):
  - `odontogram_event_guard` (BEFORE INSERT): a presença de face tem de bater com o escopo do item; só `marcar` item ativo. Usa `FOR SHARE` no item para serializar com mudança concorrente de escopo.
  - `tooth_status_guard` (BEFORE UPDATE): `kind`, `scope`, `code` e `clinic_id` não mudam se já existe evento com o item.
- `created_at` dos eventos usa `clock_timestamp()` (model e migração) e não `now()`. Como as escritas são serializadas por paciente, `now()` (início da transação) ficaria anterior à espera do lock e poderia inverter a ordem real.

## API

| Método | Rota (prefixo `/odontograma`) | Papéis | O que faz |
|---|---|---|---|
| GET | `/legenda` | admin, gestor, dentista, asb | Lista a legenda (`incluir_inativos`); cria a legenda padrão na primeira leitura |
| POST | `/legenda` | admin, gestor | Cria item |
| PATCH | `/legenda/{id}` | admin, gestor | Edita nome, cor, ordem, ativo e, se nunca usado, tipo/escopo |
| GET | `/pacientes/{id}` | admin, gestor, dentista, asb | Odontograma atual ou em `?em=<datetime com fuso>` |
| POST | `/pacientes/{id}/eventos` | admin, dentista, asb | Grava lote de 1 a 200 eventos (201) |
| GET | `/pacientes/{id}/historico` | admin, gestor, dentista, asb | Eventos do mais novo ao mais antigo (`limit` até 500, `offset`) |

Recepção não acessa nada. Gestor lê e edita a legenda, mas não marca. `NotFound` vira 404; `RuleViolation` vira 409 (`router.py:_http`).

## Regras de negócio e invariantes

- Lote é atômico e validado contra o estado atual: sem repetir (dente, face, item) no lote, não marcar o já marcado, não remover o inexistente (`regras.py:check_batch`).
- Dente/face/item formam a chave da marcação; itens diferentes coexistem no mesmo dente/face (`regras.py:rebuild`).
- Escopo do item x face é validado no serviço (mensagem amigável) e de novo por gatilho (`service.py:record_events`).
- Item desativado não pode ser marcado, mas pode ser removido e continua aparecendo em marcações antigas (a rota do odontograma usa `list_statuses` com inativos).
- Paciente inativo não recebe marcações (`service.py:record_events`).
- Atendimento informado deve existir, ser do paciente e estar ABERTO.
- Escritas do mesmo paciente são serializadas por `SELECT ... FOR UPDATE` na linha do paciente antes de ler o estado e inserir (`service.py:record_events`). Sem isso, dois lotes concorrentes passariam em `check_batch` contra o mesmo estado.
- Faces: gravadas só como M, D, O, V, L. Na entrada `I` vira `O` e `P` vira `L`; na saída o rótulo clínico é recalculado por dente (`O`→`I` em anteriores, posição ≤ 3; `L`→`P` na arcada superior, quadrantes 1, 2, 5, 6) (`regras.py:normalize_face`, `face_label`).
- `em` usa `created_at <= em`; sem `em`, usa o momento atual do servidor.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`. A legenda é por clínica, então é filtrada só pelo RLS.
- Pacientes são obtidos via `pacientes.service.get_patient` (herdando seu RLS e erro 404).
- Ações auditadas:
  - `odontograma.legenda_criada`, `odontograma.legenda_alterada` (`details.campos`; só se algo mudou)
  - `odontograma.lido` (odontograma; `details.em` se informado)
  - `odontograma.marcado` (`details.eventos`, `details.atendimento`)
  - `odontograma.historico_lido`
- A leitura da legenda não é auditada (não tem dado de paciente).

## Decisões

| Decisão | Motivo |
|---|---|
| Event sourcing simples em vez de tabela de estado | Histórico clínico imutável e odontograma retroativo sem trabalho extra |
| Legenda padrão criada na primeira leitura/uso, com `ON CONFLICT DO NOTHING` | Não exige seed por clínica; seguro sob concorrência |
| "Sem itens" significa "nunca inicializada" | Itens nunca são apagados, só desativados |
| Tipo/escopo imutáveis após uso, por serviço e por gatilho | Mudar escopo reinterpretaria eventos antigos |
| Face O e L guardam também incisal e palatina | Evita duplicar faces; o rótulo depende do dente |
| Lock na linha do paciente | Serializar validação e inserção do lote |

## Como estender

- Novo item padrão: editar `regras.py:DEFAULT_LEGEND`. Só afeta clínicas ainda sem legenda; as existentes precisam criar via API.
- Nova face ou tipo: atualizar enum no model, schema, CHECK numa nova migração (inclusive nos gatilhos, se afetar a regra) e `regras.py`.
- Novo model: importar em `app/models.py`, RLS na migração e `TRUNCATE` em `tests/conftest.py`.
- Vincular a plano de tratamento: referenciar `odontogram_events` ou o item da legenda no módulo novo, sem mudar o histórico.

## Armadilhas

- O GET da legenda escreve (cria a legenda padrão) e faz commit, apesar de ser leitura. Papéis de leitura (inclusive ASB) disparam essa escrita. O mesmo vale para `create_status` e `record_events`, que também chamam `ensure_default_legend`.
- `ensure_default_legend` só checa se existe algum item. Se a clínica criar um item antes de qualquer leitura, `create_status` ainda inicializa o padrão antes (por isso é chamado lá).
- `IntegrityError` não tratado (incluindo `check_violation` dos gatilhos e corrida no código da legenda) vira 409 pelo handler global de `app/main.py`, não 500. A checagem de código duplicado em `create_status` é só mensagem amigável.
- `PATCH` com campo `null` explícito retorna 409 ("não pode ficar vazio"); campo omitido é ignorado. `code` não é editável.
- Remover uma marcação grava novo evento `remover`; não há como corrigir ou apagar um evento errado.
- `GET /pacientes/{id}` não pagina e devolve só dentes com marcação; dente sem marcação não aparece.
- Eventos de um mesmo lote têm `created_at` distintos (`clock_timestamp()`), mas o desempate de ordenação é por `id` (UUID aleatório); não confie na ordem dentro de um lote além do timestamp.
- O parâmetro `em` exige data com fuso (`AwareDatetime`).
