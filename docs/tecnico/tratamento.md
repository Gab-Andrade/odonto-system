---
modulo: tratamento
atualizado_em: f320bfa
---
# Tratamento (plano de tratamento e orçamento)

> Planejar procedimentos por dente/face, emitir o orçamento com preço congelado, registrar a decisão (parcial) do paciente e acompanhar a execução, atualizando o odontograma.

## Responsabilidades

Faz:
- Plano e orçamento são **a mesma entidade** (`treatment_plans`) em fases: `rascunho → emitido → aprovado/recusado → concluido`, com `cancelado` saindo de rascunho ou emitido (ou de aprovado, quando todos os itens aprovados são cancelados sem nenhum realizado) (`models.py` docstring, `service.py`).
- Itens por procedimento/dente/faces, com aprovação parcial e execução vinculada a um atendimento aberto.
- Configuração por clínica: validade padrão e desconto máximo para dentista/recepção.

Fica fora:
- Cálculo e versionamento de preços: `precificacao` (`pricing.resolve` e `pricing.freeze`). Este módulo só guarda o `price_snapshot_id` e uma cópia do valor.
- Legenda e histórico do odontograma: `odontograma` (`odonto_service.record_events`, `current_marks`).
- Atendimento/evolução: `prontuario`. Aqui só se lê o `Encounter` para validar e travar.
- Cobrança, parcelas e pagamento: não existem ainda.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `treatment_settings` | sim | uma linha por clínica (validade e desconto máximo); sem linha vale o padrão de `models.py` (30 dias, 5%) |
| `treatment_plans` | sim | cabeçalho do plano/orçamento, status, desconto, validade, quem emitiu/decidiu/cancelou |
| `treatment_plan_items` | sim | procedimento por dente/faces, status do item, preço congelado, atendimento onde foi realizado |

Restrições que não são óbvias pelo model (migração `0013_tratamento.py`):
- FKs compostas com `clinic_id` em tudo (paciente, snapshot, itens da legenda, atendimento). Item referencia `(plan_id, patient_id, clinic_id)`: o paciente do item é sempre o do plano, e o atendimento tem de ser do mesmo paciente.
- A migração cria `uq_price_snapshots_id_clinic` em `price_snapshots` (também declarado no model de `precificacao`) para servir de alvo da FK.
- CHECKs do plano: `draft_not_issued` (rascunho nunca tem `issued_at`) e `issued_when_not_draft` (fora rascunho/cancelado, `issued_at` é obrigatório). Cancelado pode ser um rascunho sem emissão.
- CHECKs do item: `price_with_snapshot` (`unit_price` e `price_snapshot_id` nascem juntos), `performed_has_encounter`, `tooth_fdi`, `faces_valid`.
- Gatilho `treatment_plan_guard` (UPDATE): paciente/clínica do plano não mudam; fora de rascunho, desconto e dentista não mudam e o status não volta a rascunho.
- Gatilho `treatment_plan_item_guard`: INSERT só com plano em rascunho; DELETE só com plano em rascunho; com snapshot, preço, procedimento, dente, faces e plano não mudam; `realizado`, `cancelado` e `recusado` são finais (status, atendimento, executor e data não mudam). Todos levantam `check_violation`.
- `odonto_app` tem DELETE e TRUNCATE revogados em `treatment_plans` e `treatment_settings`: plano nunca se apaga, só cancela. Itens podem ser apagados, mas só em rascunho (gatilho).

## API

Prefixo `/tratamento`. Papéis: `PLAN` = admin, dentista; `SELL` = admin, gestor, dentista, recepção; `MANAGE` = admin, gestor; `ALL` = toda a equipe.

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/configuracao` | ALL | lê validade e desconto máximo |
| PUT | `/configuracao` | MANAGE | grava (upsert) |
| POST | `/planos` | PLAN | cria rascunho, com itens opcionais |
| GET | `/pacientes/{id}/planos` | ALL | lista planos do paciente (auditado) |
| GET | `/planos/{id}` | ALL | plano completo com totais (auditado) |
| PATCH | `/planos/{id}` | PLAN | título, notas, dentista (só rascunho) |
| POST | `/planos/{id}/desconto` | SELL | define desconto (só rascunho) |
| POST | `/planos/{id}/itens` | PLAN | inclui item (só rascunho) |
| PUT | `/itens/{id}` | PLAN | substitui o item (só rascunho) |
| DELETE | `/itens/{id}` | PLAN | remove o item (só rascunho) |
| POST | `/planos/{id}/emitir` | SELL | congela preços e fixa validade |
| POST | `/planos/{id}/decisao` | SELL | itens listados aprovados, demais recusados |
| POST | `/planos/{id}/cancelar` | SELL | cancela rascunho ou emitido |
| POST | `/planos/{id}/duplicar` | PLAN | novo rascunho com os mesmos itens |
| POST | `/itens/{id}/realizar` | PLAN | realiza item aprovado em atendimento aberto |
| POST | `/itens/{id}/cancelar` | admin, gestor, dentista | cancela item aprovado e não realizado |

Códigos: `TreatmentError` vira 404 (`NotFound`), 403 (`Forbidden`) ou 409 (`RuleViolation`, qualquer regra de negócio) em `router.py:_http`. Violação de constraint/gatilho não tratada cai no handler global de `IntegrityError` em `app/main.py` e também vira **409** genérico, não 500.

## Regras de negócio e invariantes

- Só o rascunho é alterado (itens, desconto, dentista, título): `service.py:_ensure_draft`; no banco, gatilhos de item e plano. Para mudar um emitido, `duplicar`.
- Emitir exige ao menos um item, paciente ativo e dentista responsável ainda dentista/admin ativo; falta de preço em **qualquer** item aborta a emissão inteira com a lista dos códigos (`service.py:issue`). Como a sessão não é commitada, os snapshots já criados no laço são descartados.
- Preço congelado: `issue` chama `pricing.resolve` (tabela do dentista responsável, `insurer_id=None`) e `pricing.freeze`; copia `price`/`description` do snapshot para o item. Depois disso, gatilho impede alterar.
- Validade: `valid_until = hoje + validity_days` na emissão, com "hoje" no fuso `clinic_timezone` (`service.py:today`). Vencido é calculado na leitura (`regras.is_expired`), o status no banco continua `emitido`; decisão em orçamento vencido é recusada.
- Desconto: percentual sobre o subtotal aprovado. Dentista e recepção limitados a `max_discount_pct`; admin e gestor sem limite (`service.py:set_discount`, `regras.check_discount`). Só definido em rascunho, portanto o limite vale na hora de definir, não na emissão.
- Totais (`regras.totals`): `approved_subtotal` soma itens `aprovado` e `realizado`; desconto arredondado half-up em centavos. Itens recusados ou cancelados saem do total.
- Decisão: `decide` marca todos os itens (listados = aprovado, demais = recusado). Nenhum aprovado → plano `recusado`; senão `aprovado` (`regras.plan_after_decision`).
- Concluído: plano `aprovado` vira `concluido` quando não resta item `aprovado` e há ao menos um `realizado` (`regras.plan_is_done`, chamado em `perform_item` e `cancel_item`).
- Realizar item (`service.py:perform_item`): item `aprovado`; atendimento travado com `FOR UPDATE`, do mesmo paciente, `aberto`, e `encounter.dentist_id == user.user_id` (senão 403, mesmo admin). Se o item tem dente e itens de legenda, gera eventos: `remover` do "a fazer" (se marcado) e `marcar` do "feito" (se ainda não marcado e legenda ativa), por face quando o escopo é de face.
- Ligação com o odontograma (`_check_statuses`): exige dente; legenda de escopo face exige faces; `done_status_id` precisa ser do tipo `realizado`.
- `sort_order` é opcional: omitido na inclusão, vai depois do último em passos de 10 (começa em 0) (`_next_sort_order`). No `PUT` do item, `sort_order` nulo mantém a posição atual. Na duplicação, a ordem é copiada.
- Dente FDI e faces normalizadas (`regras.normalize_faces` → ordem M, D, O, V, L; faces exigem dente) são validados no schema e repetidos como CHECK no banco.
- O plano é travado (`FOR UPDATE`) em toda mutação, via `router.py:_load` / `_plan_and_item` (o item é relido com `db.refresh` depois do lock). Emissão, decisão e execução não correm em paralelo no mesmo plano.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`; não há consulta com `clinic_id` manual. Plano de outra clínica responde 404 (RLS). Com `FORCE`, o `odonto_app` nunca vê outra clínica.
- Chamadas cruzadas (`pacientes_service.get_patient`, `pricing`, `odonto_service`, `active_role`) usam a mesma sessão de tenant.
- Commit só no router; `service` apenas faz `flush`.
- Ações em `audit.record` (prefixo `tratamento.`): `configuracao_alterada`, `plano_criado` (inclui duplicação, com `duplicado_de`), `planos_listados`, `plano_lido`, `plano_alterado` (só se algo mudou), `desconto_definido`, `item_incluido`, `item_alterado`, `item_removido`, `orcamento_emitido`, `decisao_registrada`, `plano_cancelado`, `item_realizado` (com atendimento e nº de eventos no odontograma), `item_cancelado`. Leituras são auditadas por LGPD.

## Decisões

| Decisão | Motivo |
|---|---|
| Plano e orçamento são a mesma tabela | evita copiar itens e dá uma linha do tempo única; "emitir" só congela |
| Preço congelado em `price_snapshots` + cópia em `unit_price` | o orçamento não muda quando a tabela de preço é republicada; memória de cálculo fica auditável |
| Aprovação parcial por item | paciente costuma aprovar parte do orçamento; o total considera só aprovados e realizados |
| Imutabilidade por gatilho e CHECK, além do service | concorrência ou bug no service não corrompem preço emitido |
| Plano não se apaga, só cancela | histórico financeiro/clínico; DELETE revogado do `odonto_app` |
| Orçamento vencido não é reaberto: duplica-se | garante preço atualizado, já que preço congela na emissão |
| Realizar exige o dentista do atendimento | o procedimento é ato clínico atribuído a quem atende |
| Odontograma atualizado na mesma transação da realização | item realizado e marcação não divergem; falha no odontograma aborta tudo (`RuleViolation "Odontograma: ..."`) |

## Como estender

- **Novo campo no item:** model, migração (e, se for imutável após emitir, o gatilho `treatment_plan_item_guard`), `ItemIn`/`ItemOut`, e `ITEM_FIELDS` em `service.py` (vale para criar, atualizar e duplicar).
- **Novo status de plano/item:** enum em `models.py`, lista `PLAN_STATUSES`/`ITEM_STATUSES` e CHECK na migração, `regras.py` e os CHECKs `issued_when_not_draft`/gatilhos.
- **Nova tabela do módulo:** `TenantMixin`, `enable_tenant_rls` na migração, import em `app/models.py` e inclusão no `TRUNCATE` de `clean_db` (`tests/conftest.py`).
- **Cobrança:** deve consumir `unit_price` dos itens `realizado`/`aprovado` e `discount_pct`; reutilize `regras.totals` em vez de recalcular.

## Armadilhas

- `expired` é derivado na leitura; o `status` continua `emitido`. Filtros por status não enxergam vencimento.
- O limite de desconto é checado ao definir o desconto (só rascunho), usando o papel de quem define. Quem emite não é revalidado, mas o desconto não muda depois de emitido.
- `ItemOut.estimated_price`/`estimate_error` só aparecem em rascunho e disparam `pricing.resolve` por item a cada leitura do plano.
- `emitir` usa `insurer_id=None`: não há convênio no orçamento.
- `perform_item` rejeita admin que não seja o dentista do atendimento (403), mesmo admin.
- `perform_item` exige legenda ativa para `marcar`; legenda inativada é ignorada em silêncio (sem erro, sem evento), e `remover` de marca inexistente também é ignorado.
- `cancel_item` só cancela item `aprovado`; cancelar item de plano `emitido`/`rascunho` não é possível (remova o item no rascunho ou cancele o plano). Plano `aprovado` sem item cancelável restante fica assim até todos serem realizados/cancelados; se todos forem cancelados e nenhum realizado, o plano vira `cancelado` (`regras.plan_after_items`, com motivo automático).
- Violação de gatilho/CHECK que escapa do service vira 409 genérico ("Conflito com dados existentes"), sem a mensagem do gatilho.
- `duplicate` não reaproveita preço: itens voltam sem snapshot e são reprecificados na nova emissão.
- `PlanSummary` na listagem não traz totais nem itens.
