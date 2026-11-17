---
modulo: painel
atualizado_em: c4e9fa2
---
# Painel

> Indicadores agregados e só leitura para o gestor (visão da clínica) e para o dentista (visão própria), calculados em SQL sobre os dados de outros módulos.

## Responsabilidades

- Agrega agenda do dia, receita do mês, contas vencidas, contas a pagar, orçamentos, produção por dentista e alertas de estoque.
- Não tem tabelas, models nem migração. Não escreve nada.
- Não expõe dado individual de paciente. Para ver um paciente, usa-se o prontuário (auditado).
- Regras de cada número continuam nos módulos de origem. O painel reaproveita `financeiro.regras` (`money`, `add_months`), `estoque.lotes_service.stock` e `estoque.regras.expiry_status`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| (nenhuma própria) | n/a | Lê `appointments`, `payments`, `receivables`, `payables`, `treatment_plans`, `treatment_plan_items`, `encounters`, `commission_settlements`, materiais/lotes (via estoque) e, de `users` + `clinic_memberships` (globais), só nomes de dentistas |

Cada campo de saída documenta a origem em `schemas.py` (descrições dos `Field`).

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/painel/visao-geral?mes=AAAA-MM` | admin, gestor | Clínica inteira: agenda de hoje, receita do mês, vencidos, contas a pagar, orçamentos, estoque e produção por dentista (ordenada por valor desc) |
| GET | `/painel/meu-desempenho?mes=AAAA-MM` | admin, dentista | Números do próprio usuário: agenda de hoje, atendimentos, produção, orçamentos em que é responsável e último repasse |

`mes` é opcional (padrão: mês atual no fuso da clínica). Formato inválido dá 422 (`router.py:_month`, além do `pattern` da query; ex.: `2025-13` cai no `ValueError`).

## Regras de negócio e invariantes

- Datas "de hoje" e limites de dia/mês usam `clinic_timezone` (`service.py:tz`, `day_bounds`, `_instant`) e são convertidos para UTC ao comparar com colunas `timestamptz`. Colunas `date` (`paid_on`, `due_date`) comparam direto com o mês.
- Agenda conta só `EntryKind.CONSULTA` com início no dia; bloqueios ficam fora (`service.py:agenda_day`).
- Receita: `received` soma `Payment.amount` por `paid_on` no mês. Estornos são linhas negativas, então já descontam. `expected` soma parcelas com vencimento no mês, não canceladas (`service.py:revenue`).
- Vencidos: saldo = valor da parcela menos soma dos pagamentos (incluindo estornos negativos); só parcelas não canceladas, vencidas antes de hoje e com saldo > 0 (`service.py:overdue_receivables`).
- Contas a pagar: só status `ABERTA`; "em breve" = hoje até hoje+7 dias, inclusive (`PAYABLES_SOON_DAYS`).
- Orçamentos: `awaiting` é o estoque atual de planos `EMITIDO`, sem filtro de mês; `awaiting_stale` = emitidos há mais de 7 dias (`STALE_QUOTE_DAYS`). `approved_in_month` e o valor usam `decided_at` no mês e plano `APROVADO` ou `CONCLUIDO`; o valor soma `unit_price` dos itens `APROVADO`/`REALIZADO` **sem desconto** (`service.py:quotes`).
- Produção: itens `REALIZADO` com `performed_at` no mês, agrupados por `performed_by`, valor = `unit_price * (1 - discount_pct/100)`, ou seja, **com** desconto do plano (`service.py:production`). Isso difere da regra de orçamentos acima, de propósito (cada campo declara a sua).
- Visão do dentista filtra sempre pelo `user.user_id` do token, nunca por parâmetro (`router.py:my_performance`). Orçamentos usam `TreatmentPlan.dentist_id`; produção usa `performed_by`; atendimentos usam `Encounter.dentist_id`.
- Estoque: considera só materiais ativos (padrão de `stock()`); lote só conta com saldo > 0; "vence em breve" segue `NEAR_EXPIRY_DAYS` de `estoque/regras.py` (a descrição do schema diz 30 dias).
- Nome do dentista: busca em `users` com join em `clinic_memberships` filtrando pela clínica do token, para não vazar nome de usuário sem vínculo (`router.py:_names`). Quem não tem vínculo fica com `dentist_name = None`.

## Tenancy e auditoria

- Usa só `get_tenant_db`. Os indicadores dependem do RLS para isolar clínicas, sem filtro manual de `clinic_id`. A exceção é `_names`, que filtra `clinic_id` explicitamente porque `users` e vínculos são globais.
- Não chama `audit.record`: só agregados, sem dado individual de paciente. Se um indicador passar a expor linhas por paciente, essa decisão precisa ser revista.

## Decisões

| Decisão | Motivo |
|---|---|
| Sem tabelas nem cache; tudo calculado na hora | Dados sempre consistentes com os módulos de origem; v1 sem custo de manter agregados |
| Acesso próprio do dentista em rota separada, sem parâmetro de dentista | Impede que um dentista consulte números de outro |
| `admin` também acessa `meu-desempenho` | Caso do dono que atende; ele vê os próprios números como dentista |
| Sem auditoria de leitura | Dados agregados, sem identificar paciente |
| Reuso de regras de financeiro/estoque em vez de reimplementar | Mantém definição de dinheiro, validade e mínimo igual aos módulos de origem |

## Como estender

1. Novo indicador: função agregada em `service.py` (dataclass de retorno), campo em `schemas.py` com `Field(description=...)` dizendo a origem, e inclusão em `OverviewOut` e/ou `MyPerformanceOut`.
2. Montagem no `router.py` via `XOut(**service.f(...).__dict__)`: os nomes de campos da dataclass e do schema precisam coincidir.
3. Cobrir em `tests/test_painel_unit.py` (limites de data) e `tests/test_painel_integration.py` (valores e isolamento).
4. Se o indicador listar pessoas/pacientes, adicione auditoria e reveja os papéis.

## Armadilhas

- `stock_alerts` carrega todos os materiais ativos com seus lotes e conta em Python; custo cresce com o catálogo.
- `received` usa `paid_on` do pagamento; um estorno entra no mês da data do estorno, não no do pagamento original.
- Fuso é único por instalação (`settings.clinic_timezone`), não por clínica.
- `meu-desempenho` para um dentista sem produção devolve zeros (não 404), e `production.dentist_name` vem nulo nessa rota.
- `last_settlement` usa o maior `period_end` do dentista, sem considerar o mês pedido em `mes`.
- `approved_value_in_month` (sem desconto) e `production.value` (com desconto) não são comparáveis diretamente.
- O módulo não escreve, então o handler global de `IntegrityError` (409) não se aplica aqui.
