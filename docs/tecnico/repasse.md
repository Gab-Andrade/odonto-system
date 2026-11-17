---
modulo: repasse
atualizado_em: 89d842f
---
# Repasse

> Calcula a comissão de cada dentista sobre o que o paciente efetivamente pagou, com regras versionadas e fechamentos acumulados append-only.

## Responsabilidades

- Regras de comissão por dentista (geral ou por procedimento), prévia do cálculo e fechamento por dentista até uma data.
- **Fora do módulo:** realização dos itens e `performed_by` (tratamento), recebimentos, estornos e taxa de cartão (financeiro), custo dos lotes e consumo (estoque). O repasse só **lê** essas tabelas; nada é gravado nelas.
- Não há pagamento do repasse ao dentista (conta a pagar); o fechamento só registra o valor devido.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `commission_rules` | sim | Regra de um dentista: percentual ou fixo, com vigência (`valid_from`) |
| `commission_settlements` | sim | Cabeçalho do fechamento (dentista + `period_end`) |
| `commission_lines` | sim | Uma linha por item do plano em cada fechamento, com a regra usada |

- As três são append-only: a migração `0016_repasse.py` revoga UPDATE/DELETE do `odonto_app`. Mudar uma regra é inserir outra com vigência nova.
- Unicidade (`clinic_id`, `dentist_id`, `period_end`) no fechamento. As FKs das linhas são compostas com `clinic_id`, então linha, fechamento, item e regra nunca cruzam clínicas.
- CHECKs em `commission_rules`: `kind` válido e `value` entre 0 e 100 quando percentual.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/repasse/regras` | admin, gestor, dentista | Lista regras; dentista só as próprias |
| POST | `/repasse/regras` | admin, gestor | Cria regra (`repasse.regra_criada`) |
| GET | `/repasse/previa?ate=` | admin, gestor, dentista | Calcula sem gravar; dentista vê só o próprio |
| POST | `/repasse/fechamentos` | admin, gestor | Fecha até uma data (`repasse.fechamento`) |
| GET | `/repasse/fechamentos` | admin, gestor, dentista | Lista; dentista só os próprios |
| GET | `/repasse/fechamentos/{id}` | admin, gestor, dentista | Detalhe com linhas; 403 se for de outro dentista |

Respostas fora do padrão: violações de regra de negócio (`RuleViolation`) viram **409** (`router.py:_http`); fechamento inexistente é 404; `/previa` sem dentista (gestor/admin) é 422.

## Regras de negócio e invariantes

- **Repasse sobre o recebido, acumulado.** Base do item = líquido do item (preço × (1 − desconto do plano)) × fração paga do plano até a data − base já repassada em fechamentos anteriores (`regras.py:compute_line`, `service.py:compute`). Pagamentos novos entram no fechamento seguinte; estorno posterior gera base negativa (linha negativa), sem reabrir fechamento.
- **Fração paga** = soma de `Payment.amount` (estornos são negativos) com `paid_on <= period_end` dos recebíveis do plano ÷ total aprovado do plano, limitada a [0, 1] (`regras.py:paid_ratio`).
- **Seleção de regra:** a do procedimento (casamento exato de `procedure_code`) tem prioridade sobre a geral; entre as candidatas vale a de `valid_from` mais recente ≤ data de realização do item, não a data do fechamento (`regras.py:pick_rule`).
- **Percentual:** comissão = (base − taxa − materiais) × %. Taxa = base × (taxas ÷ recebido do plano), se `deduct_card_fee`. Materiais = custo de consumo do item (`-quantity × StockLot.unit_cost`) × (base ÷ valor do item), se `deduct_materials`.
- **Fixo:** valor × (base ÷ líquido do item), isto é, proporcional ao pago, ignorando as flags de desconto.
- **Um fechamento só avança:** `period_end` precisa ser maior que o do último fechamento do dentista (`service.py:compute`) e não pode ser futuro (`service.py:close`). Datas são avaliadas no fuso da clínica (`clinic_timezone`).
- **Serialização:** `close` toma `pg_advisory_xact_lock` por dentista, pois o cálculo depende do fechamento anterior.
- Só entram itens `REALIZADO` com `performed_by` = dentista. Linhas com base 0 não são gravadas.
- Itens sem regra aplicável **não entram** e seus códigos vão para `missing_rule`. Como a base é acumulada contra `CommissionLine`, ao criar a regra depois (com vigência anterior à realização) o item é pego no próximo fechamento.
- O dentista da regra/fechamento deve ter papel dentista ou admin ativo na clínica (`service.py:ensure_dentist`).

## Tenancy e auditoria

- Tudo usa `get_tenant_db`; as consultas não filtram `clinic_id`.
- `audit.record`: `repasse.regra_criada` e `repasse.fechamento` (detalhes com dentista, data, total e nº de itens). Leituras e prévia não são auditadas.
- Commit no router; o service só faz flush.

## Decisões

| Decisão | Motivo |
|---|---|
| Repasse sobre o recebido, não sobre o realizado | A clínica só repassa o que entrou no caixa |
| Cálculo acumulado por diferença (sem guardar saldo) | Recebimentos tardios e estornos se corrigem sozinhos no próximo fechamento |
| Regras e fechamentos append-only | Histórico auditável do que foi acordado e pago |
| Vigência avaliada na data de realização | Alterar a regra não reescreve procedimentos já feitos |
| Lógica pura em `regras.py` | Testável sem banco (`test_repasse_unit.py`) |

## Como estender

- **Novo tipo de regra:** incluir em `RuleKind`, no CHECK `kind_valid` (nova migração), em `regras.py:compute_line` e em `service.py:compute` (montagem de `regras.Rule`).
- **Nova dedução:** coluna booleana na regra (migração), campo em `RuleIn`, `regras.Rule` e `compute_line`, e coluna em `commission_lines` para guardar o valor.
- **Pagar o repasse:** criar conta a pagar no financeiro a partir do fechamento; hoje não existe vínculo.

## Armadilhas

- `procedure_code` da regra não é validado contra catálogo: erro de digitação gera regra que nunca casa (o item cai em `missing_rule`).
- `IntegrityError` não tratado (por exemplo, corrida no `uq_commission_settlements_dentist_end`) vira 409 pelo handler global, não 500.
- `odonto_app` nunca teve TRUNCATE; a limpeza dos testes é feita como `odonto`.
- Percentual > 100 passa pelo schema e só é barrado no service (409) ou no CHECK; `RuleIn` valida apenas `ge=0`.
- Fechar sem nenhuma linha ainda grava fechamento (total 0) e trava a data: não é possível fechar de novo até uma data anterior ou igual.
- Taxa de cartão é proporcional ao plano inteiro (taxas ÷ recebido do plano), não ao meio de pagamento do item.
- A prévia de dentista não chama `ensure_dentist` (só gestor/admin chamam); como o escopo é o próprio usuário, não há efeito prático.
- Recebíveis avulsos sem `plan_id` não contam para nenhum repasse.
