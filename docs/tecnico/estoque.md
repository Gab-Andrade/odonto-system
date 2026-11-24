---
modulo: estoque
atualizado_em: 3afacea
---
# Estoque

> Cadastro de materiais, lotes com validade, movimentos append-only, estoque mínimo, custo médio ponderado e baixa automática (FEFO) quando um item do plano de tratamento é realizado.

## Responsabilidades

- Cadastro de materiais (custo unitário, unidade, estoque mínimo). Material nunca é excluído, só desativado (`active=false`), porque fichas técnicas apontam para ele.
- Entradas (cada uma cria um lote), saídas manuais, ajustes de inventário e consulta de saldos, alertas e movimentos.
- Rastreio por paciente: qual lote e validade foram usados em quem.
- Baixa automática pela ficha técnica: `lotes_service.py:consume_for_procedure`, chamada por `tratamento/service.py:perform_item`.
- **Fora do módulo:** a ficha técnica (`CostSheet`/`CostSheetItem`) e o uso do custo no cálculo de preço moram em [precificacao](precificacao.md). Plano, item e realização moram em [tratamento](tratamento.md). Paciente mora em pacientes.
- Interface para outros módulos: `service.py:material_costs` (custo atual, usado pela precificação) e `lotes_service.py:consume_for_procedure`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `materials` | sim | Cadastro; `unit_cost` é o custo médio ponderado vigente |
| `stock_lots` | sim | Uma entrada de compra (código, validade, custo da compra, fornecedor) |
| `stock_movements` | sim | Livro de movimentos append-only; o saldo do lote é a soma deles |

Pontos não óbvios (migração `0015_estoque_lotes.py`):

- **Não existe coluna de saldo.** Saldo do lote = `SUM(quantity)` dos movimentos (`lotes_service.py:_balances`); saldo do material = soma dos lotes.
- Quantidade é negativa nas saídas (`consumo`, `saida`); `ajuste` grava a diferença com sinal. CHECKs: `sign_by_kind`, `quantity_not_zero`, `consumption_has_patient` (consumo exige paciente e item do plano, e só consumo os tem) e `manual_has_reason` (saída e ajuste exigem motivo).
- Gatilho `stock_movement_guard` (BEFORE INSERT): trava a linha do lote (`FOR UPDATE`) e recusa o movimento se o saldo ficaria negativo, com `check_violation`. É a garantia real contra concorrência; a checagem do service só dá mensagem melhor.
- Gatilho `stock_lot_guard` (BEFORE UPDATE): lote não muda material, custo nem clínica.
- Append-only por grants: `REVOKE UPDATE, DELETE` em `stock_movements` e `REVOKE DELETE` em `stock_lots` para `odonto_app`. Não há gatilho, então o dono do schema (`odonto`) consegue alterar.
- FKs compostas com `clinic_id` (lote–material, movimento–lote/material, movimento–paciente, movimento–item do plano) impedem referência entre clínicas. A migração cria `uq_treatment_plan_items_id_clinic` em `treatment_plan_items` como alvo da FK.
- `stock_movements.created_at` usa `clock_timestamp()` para manter a ordem real de vários movimentos na mesma transação.
- Todas as FKs de movimentos são `RESTRICT`: paciente ou item do plano com consumo registrado não pode ser removido.

## API

Dois routers com o mesmo prefixo `/estoque`: `router.py` (materiais) e `lotes_router.py` (lotes e movimentos). Ambos registrados em `main.py`.

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/estoque/materiais` | admin, gestor, dentista, asb | Lista; custo só para admin e gestor |
| POST | `/estoque/materiais` | admin, gestor | Cria material |
| GET | `/estoque/materiais/{id}` | admin, gestor, dentista, asb | Detalhe (custo só para admin e gestor) |
| PATCH | `/estoque/materiais/{id}` | admin, gestor | Altera ou desativa |
| POST | `/estoque/entradas` | admin, gestor, asb | Cria lote + movimento de entrada e recalcula o custo médio |
| POST | `/estoque/saidas` | admin, gestor, asb | Saída manual de um lote (perda, vencido, uso avulso) |
| POST | `/estoque/ajustes` | admin, gestor | Ajusta o lote para a quantidade contada; sem diferença responde 200 com `null` e não grava |
| GET | `/estoque/saldos` | admin, gestor, dentista, asb | Saldo por material com lotes (só saldo > 0); `somente_alertas` filtra abaixo do mínimo ou com lote vencido/vencendo |
| GET | `/estoque/movimentos` | admin, gestor | Movimentos filtrados por material/lote (limite 500) |
| GET | `/estoque/pacientes/{id}/rastreio` | admin, gestor, dentista, asb | Materiais e lotes usados no paciente |

Respostas fora do padrão: toda `StockError` que não seja `NotFound` vira 409 (`RuleViolation`). Qualquer `IntegrityError` não tratado (inclusive `check_violation` dos gatilhos) também vira 409 pelo handler global de `main.py`, não 500.

## Frontend e demo

Tela em `frontend/src/pages/estoque/Estoque.tsx`, rota `/estoque` (`App.tsx`, carregada com `lazy`), item de menu visível aos papéis `CLINICOS` (admin, gestor, dentista, asb) em `layout/AppLayout.tsx`.

- **Quem vê o quê:** a tela escolhe pelo papel da sessão, espelhando as regras da API.
  - Dentista: só a aba "Saldos e lotes", em leitura (sem botões de ação, sem custo).
  - ASB: a mesma aba, com "+ Entrada" e "Saída" por lote. Não vê a coluna de custo, o formulário de entrada não pede custo (envia `unit_cost: null`) e não há "Inventário".
  - Admin e gestor (`GESTAO`): três abas (Saldos e lotes, Materiais, Movimentos), coluna de custo, custo obrigatório na entrada e "Inventário" (ajuste).
- **Rotas consumidas:** `GET /estoque/saldos` (filtro `somente_alertas`), `GET /estoque/materiais` (`incluir_inativos`), `POST /estoque/materiais`, `PATCH /estoque/materiais/{id}`, `POST /estoque/entradas`, `/saidas`, `/ajustes` e `GET /estoque/movimentos` (limite 200, filtro por material). O rastreio por paciente não é usado nesta tela.
- Após qualquer mutação invalida a query `["estoque"]`; salvar material invalida também `["precificacao"]`, porque o custo alimenta a ficha técnica.
- Na tela de saída de lote vencido, o motivo vem pré-preenchido com "Lote vencido". O campo Motivo é obrigatório em saída e inventário (espelha o CHECK `manual_has_reason`).
- Desativar/reativar material usa o PATCH apenas com `active`.
- **Demo** (`backend/app/demo.py`: `MATERIALS` e `_stock`): cria 4 materiais com lotes usando `estoque.create_material` e `estoque_lotes.register_entry(..., can_set_cost=True)`. Cobre os alertas: resina abaixo do mínimo e vencendo (lote com 20 dias), anestésico com um lote já vencido (-10 dias), lima sem validade. É idempotente por checagem: se já existe qualquer material, não faz nada.

## Regras de negócio e invariantes

- **Saldo nunca negativo:** gatilho `stock_movement_guard`. O service pré-checa em `lotes_service.py:register_exit` (mensagem "Quantidade acima do saldo do lote."); em corrida, quem perde recebe 409 genérico do handler.
- **Custo médio ponderado:** a cada entrada, `lotes_service.py:register_entry` recalcula `Material.unit_cost` com `regras.py:weighted_cost` sobre todos os lotes com saldo > 0 (inclui vencidos com saldo). Só entrada recalcula; saídas, consumos e ajustes não mexem no custo do material.
- **PATCH manual de `unit_cost` é sobrescrito** na próxima entrada, porque o custo é recomputado dos lotes e não do valor anterior. O PATCH continua válido até lá (e é o único jeito de definir custo de material sem lotes).
- **Quem informa custo na entrada:** admin e gestor devem informar `unit_cost` (obrigatório); ASB não pode informar (409 se enviar). O lote da ASB entra com o custo atual do material (`material.unit_cost`). Ver Armadilhas sobre o efeito disso na média.
- **Entrada:** material desativado é recusado; `received_on` futura é recusada (data de referência: `lotes_service.py:today`, fuso `clinic_timezone`).
- **FEFO:** `regras.py:allocate` ignora lotes sem saldo e vencidos (`expires_on < hoje`), ordena por validade (sem validade por último, empate pelo recebimento mais antigo) e divide a necessidade entre lotes.
- **Baixa automática não bloqueia o procedimento:** `consume_for_procedure` baixa o que houver, devolve as faltas como `Shortage` e `tratamento/service.py:perform_item` as converte em `warnings` na resposta (`Estoque insuficiente de X: faltou N.`). Sem ficha técnica para o `procedure_code`, não baixa nada, sem aviso.
- **Concorrência na baixa:** `lot_balances(lock=True)` trava os lotes do material (`FOR UPDATE`) antes de alocar; `get_lot` também trava o lote nas saídas e ajustes; `register_entry` trava a linha do material antes de recalcular a média.
- **Ajuste:** grava `contado - saldo atual` (positivo ou negativo); o gatilho barra se o resultado fosse negativo, o que não ocorre com contagem >= 0.
- **Custo visível só a admin e gestor** em materiais e lotes (`router.py:_out`, `lotes_router.py:_lot_out`). Dentista e ASB recebem `unit_cost` nulo/ausente.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`; nenhuma consulta filtra `clinic_id`, o RLS faz isso. Nas duas tabelas novas, `enable_tenant_rls` está na migração 0015.
- O módulo importa `pacientes.service.get_patient` no rastreio e `precificacao.models` (import local em `consume_for_procedure`, para evitar ciclo, já que a precificação depende do estoque).
- Ações de `audit.record`:

| Ação | Quando |
|---|---|
| `estoque.material_criado` / `estoque.material_alterado` | POST/PATCH de material |
| `estoque.entrada` | Entrada (lote) |
| `estoque.saida` | Saída manual |
| `estoque.ajuste` | Ajuste com diferença (sem diferença, nada é auditado) |
| `estoque.movimentos_lidos` | GET `/movimentos` (consumos expõem paciente) |
| `estoque.rastreio_lido` | GET do rastreio por paciente (LGPD) |

- O consumo automático não gera `audit.record` próprio: fica registrado no movimento e na auditoria `item_realizado` do tratamento (campo `faltas_estoque`).
- Leituras de materiais e de `/saldos` não são auditadas.

## Decisões

| Decisão | Motivo |
|---|---|
| Saldo derivado dos movimentos, sem coluna de saldo | Evita divergência; o livro append-only é a fonte da verdade e permite rastreio |
| Gatilho para saldo não negativo em vez de só checar no service | Movimentos simultâneos no mesmo lote não passam juntos |
| Custo médio ponderado em `materials.unit_cost` | A precificação já lê esse campo (`material_costs`); nada muda do lado dela |
| Falta de estoque vira aviso, não erro | O atendimento clínico não pode ser travado por contagem de estoque desatualizada |
| FEFO ignorando vencidos | Material vencido não deve ser usado em paciente; sai por saída manual com motivo |
| Consumo exige paciente e item do plano (CHECK) | Rastreabilidade de implantes e materiais |
| ASB dá entrada sem custo | ASB não vê custos; o lote usa o custo atual do material |

## Como estender

- **Novo tipo de movimento:** incluir em `MovementKind`, no CHECK `kind_valid` e em `sign_by_kind`/regras de motivo por nova migração (CHECKs são criados à mão, `create_constraint=False`).
- **Novo campo do lote:** adicionar ao model e à migração; lembrar que `stock_lot_guard` só protege material, custo e clínica.
- **Nova rota que lê paciente em movimentos:** audite a leitura, como `movimentos_lidos` e `rastreio_lido`.
- **Regra de alocação diferente (ex.: outro critério além de FEFO):** alterar `regras.py:allocate`/`fefo_order`, que são puras e têm testes em `tests/test_estoque_lotes_unit.py`.
- **Nova tabela do módulo:** `TenantMixin` + `enable_tenant_rls` na migração, import em `app/models.py` e inclusão no `TRUNCATE` de `clean_db`.

## Armadilhas

- **`unit_cost` editado por PATCH é perdido** na próxima entrada (a média é recomputada dos lotes). Documentado como comportamento, mas a resposta do PATCH não avisa.
- **Entrada da ASB não recalcula a média:** o lote entra ao custo atual do material e `register_entry` só recalcula `materials.unit_cost` quando o custo foi informado (admin/gestor). A próxima entrada com custo recalcula a média incluindo esse lote.
- **Lotes vencidos com saldo entram** no saldo do material, no alerta de mínimo e na média de custo, mas nunca são consumidos pelo FEFO. É preciso dar saída manual para tirá-los.
- **Entrada aceita `expires_on` no passado** (não há validação); o lote já nasce vencido.
- **`lot_code` não é único**: o mesmo código pode ser cadastrado várias vezes.
- **Material desativado ainda é baixado** pela ficha técnica: `consume_for_procedure` não filtra por `active`. A entrada é que recusa material inativo.
- **Erro de saldo em corrida** chega como 409 genérico (IntegrityError via handler global), sem a mensagem amigável do service.
- **Dois routers sob `/estoque`:** rotas novas devem ir ao arquivo certo (materiais em `router.py`, o resto em `lotes_router.py`) e cada um define seus próprios conjuntos de papéis (`READ`, `MANAGE`, `MOVE`), duplicados entre os arquivos.
- **Ajuste sem diferença** responde 200 com corpo `null`, sem auditoria.
- **Tela: `FormMaterial` envia `unit_cost` no PATCH** de edição (corpo completo), então salvar outros campos regrava o custo exibido, que pode ser a média atual; a edição de custo segue sujeita à regra de sobrescrita na próxima entrada.
- **Tela: movimentos mostram "—" no nome/unidade** de materiais que não vieram da lista (a aba usa `useMateriais(true)`, que inclui inativos, então só falha se a lista não carregou).
- `odonto_app` nunca teve `TRUNCATE`, então o revoke da migração não o cobre; a limpeza dos testes usa o role dono.
