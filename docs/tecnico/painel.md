---
modulo: painel
atualizado_em: 1ee64af
---
# Painel

> Indicadores agregados para o gestor (clínica inteira, equipe, tendências) e para o dentista (visão própria), calculados em SQL sobre dados de outros módulos, mais metas mensais, que são a única escrita do módulo.

## Responsabilidades

- Agrega agenda do dia, receita do mês, vencidos, contas a pagar, orçamentos, produção por dentista e alertas de estoque (`service.py`, v1).
- Indicadores por mês com comparação contra o mês anterior, série de tendências, comparativo da equipe e metas (`gestao.py`, Fase 5.2).
- Guarda metas mensais (`panel_goals`). Todo o resto é leitura calculada na hora.
- Mostra alertas de inteligência só como contagem por regra (`inteligencia.service.summary`). O detalhe com pacientes mora em `/inteligencia`, que é auditado.
- Não expõe dado individual de paciente. Para ver um paciente, usa-se o prontuário.
- As regras de cada número continuam nos módulos de origem. O painel reaproveita `financeiro.regras` (`money`, `add_months`), `estoque.lotes_service.stock` e `estoque.regras.expiry_status`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `panel_goals` | sim | Meta de um indicador num mês, da clínica (`dentist_id` nulo) ou de um dentista |
| (leitura) | sim | `appointments`, `payments`, `receivables`, `payables`, `treatment_plans`, `treatment_plan_items`, `encounters`, `commission_settlements`, `patients`, materiais e lotes (via estoque) |
| (leitura) | não (global) | `users` e `clinic_memberships`, só para nomes e para listar dentistas |

Restrições de `panel_goals` (migração `0020_painel_metas.py`, espelhadas em `models.py:PanelGoal`):
- Unicidade `(clinic_id, month, metric, dentist_id)` com `NULLS NOT DISTINCT`. Sem isso, duas metas da clínica (dentista nulo) para o mesmo mês e métrica seriam permitidas.
- CHECKs: `month` é dia 1, `target > 0`, e `recebido` exige `dentist_id` nulo.
- FK `dentist_id` com `RESTRICT` (não dá para apagar o usuário com meta). `updated_by` com `SET NULL`.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/painel/visao-geral?mes=` | admin, gestor | Clínica inteira: agenda de hoje, receita, vencidos, a pagar, orçamentos, estoque, produção por dentista (valor desc), comparação com o mês anterior, metas da clínica e contagem de alertas |
| GET | `/painel/meu-desempenho?mes=` | admin, dentista | Números do próprio usuário: agenda de hoje, atendimentos, produção, orçamentos, último repasse, comparação, metas e alertas |
| GET | `/painel/equipe?mes=` | admin, gestor | Indicadores e metas de cada dentista no mês |
| GET | `/painel/tendencias?ate=&meses=&dentista_id=` | admin, gestor | Série mensal com variação % contra o mês anterior; sem `dentista_id`, é a clínica |
| GET | `/painel/minha-tendencia?ate=&meses=` | admin, dentista | Mesma série, sempre do usuário do token |
| GET | `/painel/metas?mes=` | admin, gestor | Metas do mês (clínica e dentistas) com realizado e % |
| PUT | `/painel/metas` | admin, gestor | Cria (201) ou substitui (200) a meta de mês + métrica + dentista |
| DELETE | `/painel/metas/{id}` | admin, gestor | Remove a meta (204; 404 se não existe na clínica) |

`mes` e `ate` são opcionais (padrão: mês atual no fuso configurado). Formato ou ano fora de 2000 a 2100 dá 422 (`router.py:_month`). `meses` vai de 1 a 24. Violação de regra de meta dá 422 com `detail` em texto (`GoalError`). Métrica inválida dá 422 (`router.py:_metric`).

## Regras de negócio e invariantes

- Datas "de hoje" e limites de dia/mês usam `settings.clinic_timezone` e viram UTC para comparar com `timestamptz` (`service.py:tz`, `day_bounds`, `_instant`). Colunas `date` (`paid_on`, `due_date`) comparam direto.
- Agenda conta só `EntryKind.CONSULTA`; bloqueios ficam fora (`service.py:agenda_day`). No indicador mensal, `consultas` exclui canceladas e `taxa_faltas_pct` = faltas ÷ (atendidas + faltas) (`gestao.py:month_metrics`).
- Receita: `received` soma `Payment.amount` por `paid_on`. Estornos são linhas negativas, então já descontam. `expected` soma parcelas com vencimento no mês e não canceladas (`service.py:revenue`).
- Vencidos: saldo = valor da parcela menos pagamentos (com estornos); só não canceladas, vencidas antes de hoje e saldo > 0 (`service.py:overdue_receivables`).
- Contas a pagar: só `ABERTA`; "em breve" vai de hoje a hoje+7, inclusive (`PAYABLES_SOON_DAYS`).
- Orçamentos: `awaiting` é o estoque atual de `EMITIDO`, sem filtro de mês; `awaiting_stale` = emitidos há mais de 7 dias. O valor aprovado soma `unit_price` dos itens `APROVADO`/`REALIZADO` de planos `APROVADO`/`CONCLUIDO` decididos no mês, **sem desconto** (`service.py:quotes`, `gestao.py:month_metrics`).
- Produção: itens `REALIZADO` com `performed_at` no mês, agrupados por `performed_by`, valor = `unit_price * (1 - discount_pct/100)`, ou seja, **com** desconto (`service.py:production`). Difere de propósito do valor aprovado.
- Conversão = aprovados ÷ decididos no mês (decididos = `APROVADO`, `CONCLUIDO`, `RECUSADO` com `decided_at` no mês). Ticket médio = valor aprovado ÷ orçamentos aprovados (`gestao.py`).
- `recebido` e `novos_pacientes` só existem na visão da clínica: com `dentist_id` ficam `None`, porque recebimento não é atribuído a dentista (`gestao.py:month_metrics`). A variação deles também é `None`.
- `variation` devolve `None` quando falta base ou o mês anterior é zero, nunca divide por zero (`gestao.py:variation`).
- Meta (`gestao.py:set_goal`): alvo > 0; `procedimentos` exige inteiro; `recebido` não aceita dentista; ano 2000 a 2100; o `dentist_id` precisa ser dentista ou admin ativo na clínica (`is_dentist` relê o papel via `active_role`). O mês é normalizado para dia 1. Upsert com `SELECT ... FOR UPDATE` e depois `flush`.
- Progresso de meta = realizado ÷ alvo, em % com uma casa (`gestao.py:progress`). O realizado vem de `MonthMetrics.value(metric)`.
- Visão do dentista filtra sempre por `user.user_id` do token, nunca por parâmetro (`router.py:my_performance`, `my_trend`). Orçamentos usam `TreatmentPlan.dentist_id`; produção usa `performed_by`; atendimentos usam `Encounter.dentist_id`.
- Estoque considera materiais ativos (padrão de `stock()`); lote só conta com saldo > 0; "vence em breve" segue `NEAR_EXPIRY_DAYS` de `estoque/regras.py`.
- Nome de dentista: junta `users` com `clinic_memberships` filtrando pela clínica do token (`router.py:_names`, `gestao.py:dentists`), para não vazar nome de usuário sem vínculo.
- Equipe: lista dentistas e admins com vínculo e usuário ativos; quem saiu mas produziu no mês é acrescentado com o nome ou "(sem vínculo)" e papel `DENTISTA` (`gestao.py:team`).

## Tenancy e auditoria

- Só `get_tenant_db`. O isolamento vem do RLS, sem filtro manual de `clinic_id`. Exceções: consultas a `users` e `clinic_memberships` (globais), que filtram `clinic_id` explicitamente, e o `clinic_id` gravado em `set_goal`.
- Leituras não são auditadas (só agregados).
- `PUT /painel/metas` chama `audit.record` com `painel.meta_definida` (detalhes: mês, métrica, `nova`). `DELETE` usa `painel.meta_removida`. O commit é feito no router.

## Decisões

| Decisão | Motivo |
|---|---|
| Sem cache nem agregados materializados; tudo calculado na hora | Consistência com os módulos de origem; evita manter tabelas derivadas |
| Metas em tabela própria, opcionais | O painel funciona sem nenhuma meta |
| Rota separada para o dentista, sem parâmetro de dentista | Impede um dentista de consultar números de outro |
| `admin` também acessa as rotas do dentista | Dono que atende vê os próprios números |
| `recebido` só da clínica | Pagamento não tem dentista |
| Regras de financeiro e estoque reaproveitadas | Mantém a definição de dinheiro, validade e mínimo igual à dos módulos de origem |
| Alertas como contagem apenas | Detalhe com paciente exige leitura auditada em `/inteligencia` |

## Como estender

1. Novo indicador mensal: campo em `gestao.py:MonthMetrics` e cálculo em `month_metrics`; inclua em `COMPARED` se deve ter variação; adicione o campo em `schemas.py:MonthMetricsOut` (a montagem usa `__dict__`, então os nomes precisam coincidir).
2. Nova métrica de meta: valor em `models.py:GoalMetric`, ramo em `MonthMetrics.value`, lista `METRICS` em nova migração que altere o CHECK `metric_valid`, e a mensagem de `router.py:_metric`.
3. Novo indicador da visão geral: função agregada em `service.py` (dataclass), schema com `Field(description=...)` dizendo a origem, e inclusão em `OverviewOut` ou `MyPerformanceOut` e no `router.py`.
4. Se algo listar pessoas ou pacientes, adicione auditoria e reveja os papéis.
5. Testes: `test_painel_unit.py` e `test_painel_gestao_unit.py` (regras puras e limites de data); `test_painel_integration.py` e `test_painel_gestao_integration.py` (valores, papéis e isolamento).

## Armadilhas

- Custo de consultas: cada `month_metrics` faz várias queries. A visão geral calcula o mês e o anterior, e as metas recalculam por dentista; `equipe` roda um por dentista e `tendencias` roda `meses + 1` (até 25). `stock_alerts` carrega todos os materiais ativos com lotes e conta em Python.
- Metas de dentista não aparecem na `visao-geral` (só as da clínica); estão em `/painel/metas`, `/painel/equipe` e `meu-desempenho`.
- `received` usa `paid_on`: o estorno entra no mês da data do estorno.
- Fuso único por instalação, não por clínica.
- `meu-desempenho` sem produção devolve zeros (não 404), e `production.dentist_name` vem nulo nessa rota.
- `last_settlement` usa o maior `period_end` do dentista, ignorando `mes`.
- `approved_value_in_month`/`aprovado` (sem desconto) e produção (com desconto) não são comparáveis.
- `PUT /painel/metas` tenta evitar corrida com `FOR UPDATE`, mas se duas criações simultâneas passarem sem linha prévia, a unicidade falha e cai no handler global de `IntegrityError` (409), não no 422.
- Desativar um dentista não apaga as metas dele (FK `RESTRICT` só impede apagar o usuário), e `PUT` para ele passa a dar 422.
- Em `team`, o papel de quem saiu é fixado como `DENTISTA` mesmo que tenha sido admin.
