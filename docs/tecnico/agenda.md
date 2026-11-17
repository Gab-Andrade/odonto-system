---
modulo: agenda
atualizado_em: 47b3794
---
# Agenda

> Cadeiras, agendamentos de consulta e bloqueios de horário, sem conflito de dentista ou cadeira, com histórico de eventos append-only.

## Responsabilidades

- Cadastro de cadeiras, marcação e remarcação de consultas, bloqueios (almoço, férias, manutenção), máquina de status e histórico por agendamento.
- Fora do módulo: dados do paciente e consentimentos (`pacientes`; a agenda só valida que o paciente existe e está ativo, via `pacientes.service.get_patient`), papéis e vínculos (`identidade`; `active_role` valida o dentista), conteúdo clínico (não existe ainda; a agenda guarda só `procedure` e `notes` livres).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `chairs` | sim | Cadeiras da clínica; nome único por clínica |
| `appointments` | sim | Consultas **e** bloqueios (`kind`) |
| `appointment_events` | sim | Histórico de criação, reagendamento, alteração e status |

- Consulta e bloqueio dividem a tabela de propósito: as mesmas constraints de exclusão barram conflito entre eles.
- Constraints de exclusão GiST (`excl_appointments_dentist_overlap` e `excl_appointments_chair_overlap`, migração `0008_agenda.py`) usam `clinic_id`, o id e `tstzrange(starts_at, ends_at, '[)')`, com `WHERE status IN (agendado, confirmado, atendido)`. Elas não aparecem no model. `clinic_id` entra porque a checagem de exclusão ignora o RLS. Terminar às 10h e começar às 10h não conflita. `NULL` em dentista ou cadeira não conflita com nada.
- A lista de status que ocupam horário existe em dois lugares que precisam andar juntos: `models.py:OCCUPYING` e o WHERE das constraints na migração.
- CHECKs: `consulta_has_patient_and_dentist` e `bloqueio_has_target` (bloqueio sem paciente, com dentista e/ou cadeira), além de `period_valid`.
- FKs compostas `(patient_id, clinic_id)` e `(chair_id, clinic_id)` impedem referência cruzada entre clínicas. `dentist_id` aponta para `users` (global), então a pertença à clínica é validada só no service.
- `appointment_events` é append-only: a migração revoga UPDATE/DELETE/TRUNCATE do `odonto_app`. A migração também cria a extensão `btree_gist`, que o downgrade não remove.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/agenda/cadeiras` | toda a equipe | Lista (`incluir_inativas`) |
| POST | `/agenda/cadeiras` | admin, gestor | Cria cadeira |
| PATCH | `/agenda/cadeiras/{id}` | admin, gestor | Renomeia, ativa ou desativa |
| GET | `/agenda/agendamentos` | toda a equipe | Lista por período, dentista, cadeira ou paciente |
| POST | `/agenda/agendamentos` | toda a equipe | Cria consulta |
| POST | `/agenda/bloqueios` | toda a equipe | Cria bloqueio |
| GET | `/agenda/agendamentos/{id}` | toda a equipe | Detalhe com `historico` |
| PATCH | `/agenda/agendamentos/{id}` | toda a equipe | Remarca ou altera textos (serve para consulta e bloqueio) |
| POST | `/agenda/agendamentos/{id}/status` | toda a equipe | Muda status |

- Toda violação de regra (inclusive conflito de horário) devolve **409** com `detail` em texto. Não encontrado devolve 404. A conversão está em `router.py:_http`. Erros de validação de schema seguem o padrão 422.
- Bloqueios são listados, lidos, alterados e cancelados pelas rotas de `/agendamentos`.

## Regras de negócio e invariantes

- **Conflito de horário:** a garantia é a constraint do banco. `service.py:_ensure_free` consulta antes só para montar a mensagem com o horário conflitante. Se duas requisições passarem juntas, `service.py:_flush` faz o flush num savepoint e traduz a violação pelo nome da constraint (`EXCLUSION_CONSTRAINTS`).
- **`_ensure_free` roda em `no_autoflush`:** sem isso, as mudanças pendentes da própria entrada iriam ao banco antes da consulta, e a constraint dispararia sem a mensagem amigável.
- **Dentista:** precisa ter papel ativo `dentista` ou `admin` na clínica (`service.py:_ensure_dentist`, via `active_role`). O admin conta como dono-dentista.
- **Paciente:** ativo e da clínica, validado só na criação. Desativar o paciente depois não afeta os agendamentos existentes.
- **Cadeira:** precisa estar ativa ao ser usada. Desativar é recusado se há compromisso ocupante que ainda não terminou (`update_chair`).
- **Duração:** consulta até 12h, bloqueio até 31 dias. Datas precisam ter fuso (`regras.py:check_period`). Listagem aceita no máximo 62 dias (`MAX_LIST_RANGE`).
- **Status** (`regras.py:TRANSITIONS`): `agendado` vai para confirmado, atendido, falta ou cancelado. `confirmado` vai para atendido, falta ou cancelado. Os demais são finais. `atendido` e `falta` só depois do horário de início. Bloqueio só pode ser cancelado (`service.py:change_status`). Falta e cancelamento liberam o horário. Atendido continua ocupando.
- **Remarcação** (`starts_at`, `ends_at`, `dentist_id`, `chair_id`) só vale em agendado ou confirmado (`regras.is_editable`). Remarcar um confirmado o volta para agendado, porque a confirmação era do horário antigo. Consulta nunca fica sem dentista. Bloqueio precisa manter dentista ou cadeira.
- **Histórico:** `update_entry` grava no máximo **um** evento por requisição. Eventos da mesma transação teriam o mesmo `created_at` (`now()` do Postgres), e a ordem ficaria indefinida. Por isso, uma remarcação com mudança de texto vira um evento `reagendado` com `details.campos`.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`. O módulo não usa `get_db`. As consultas não filtram `clinic_id`.
- `service` nunca faz commit: quem commita é o router, depois de `audit.record`.
- Ações auditadas: `agenda.cadeira_criada`, `agenda.cadeira_alterada`, `agenda.agendamento_criado`, `agenda.bloqueio_criado`, `agenda.agendamento_alterado` ou `agenda.bloqueio_alterado` (só se algo mudou), `agenda.status_alterado`.
- Leituras (listas e detalhe) **não** são auditadas: a agenda não traz conteúdo clínico.
- Existem duas trilhas: `audit_logs` (quem fez, global) e `appointment_events` (histórico de negócio do agendamento, exposto no detalhe).

## Decisões

| Decisão | Motivo |
|---|---|
| Consulta e bloqueio na mesma tabela | As mesmas constraints de exclusão cobrem os dois tipos de conflito |
| Conflito garantido por constraint de exclusão, com consulta prévia só para a mensagem | A consulta sozinha tem corrida; a constraint não tem |
| `appointment_events` append-only, separada da auditoria | O histórico de status alimenta faltas e indicadores |
| Falta e cancelamento liberam o horário; atendido não | O horário atendido foi de fato usado |
| Tratar admin como dentista | Dono-dentista agenda para si mesmo |

## Como estender

- **Novo status:** altere `AppointmentStatus`, `TRANSITIONS` e `STATUS_LABEL` em `regras.py`, o CHECK `status_valid` (em `appointments` e `appointment_events`) numa migração nova, e decida se ele ocupa horário. Se ocupar, mude `OCCUPYING` e recrie as duas constraints de exclusão.
- **Novo campo de remarcação:** inclua em `SCHEDULE_FIELDS` (`service.py`) e trate em `update_entry`.
- **Nova tabela da agenda:** `TenantMixin`, `enable_tenant_rls` na migração, import em `app/models.py` e entrada no TRUNCATE de `clean_db`. O TRUNCATE do conftest já inclui as três tabelas deste módulo.

## Armadilhas

- `PATCH /agendamentos/{id}` com `null` explícito limpa o campo (por exemplo `chair_id`, `notes`). Para `starts_at` e `ends_at`, `null` é recusado. Campos de texto podem ser alterados em qualquer status, inclusive cancelado.
- Na remarcação, o dentista só é revalidado se foi alterado. Se perdeu o papel de dentista depois, a consulta antiga continua remarcável sem trocar de dentista.
- `change_status` sobrescreve `status_reason` a cada mudança (inclusive com `None`). O motivo anterior só sobrevive no histórico, e só se tiver sido informado.
- `list_entries` corta em 2000 linhas sem avisar. Sem período, só é aceito com `paciente_id`, e aí não há limite de datas.
- Se `starts_at` ou `ends_at` for omitido num PATCH, o outro é comparado com o valor atual. A validação de período usa o par resultante.
- A mensagem de conflito expõe o horário do compromisso conflitante, e isso vale também para a cadeira ou dentista de outro paciente. É uma escolha, não um bug, mas não mostra o nome do paciente.
- Uma `IntegrityError` que não seja de exclusão é relançada por `_flush` e vira 409 genérico pelo handler global de `app/main.py` (sem a mensagem específica).
- Os testes estão em `tests/test_agenda_unit.py` (regras puras) e `tests/test_agenda_integration.py` (exigem banco).
