---
modulo: financeiro
atualizado_em: 1d37523
---
# Financeiro

> Contas a receber (parcelamento do orçamento aprovado e contas avulsas), recebimentos append-only com estorno e contas a pagar da clínica, tudo com registro manual.

## Responsabilidades

- Gera as contas a receber (entrada + parcelas mensais) a partir do orçamento aprovado do módulo `tratamento`.
- Registra recebimentos (totais ou parciais), a taxa do meio de pagamento e o líquido. Correção é estorno, nunca edição.
- Calcula o status das contas (aberta, parcial, paga, vencida) a partir dos recebimentos. Só o cancelamento é gravado.
- Extrato do paciente e contas a pagar (fornecedor, vencimento, pagar, cancelar).
- Configuração da clínica (`financial_settings`): hoje só `dentist_can_view`, que libera o extrato ao dentista.

Fora do módulo:
- Cálculo do total aprovado e do desconto: `tratamento/regras.py:totals`, reutilizado aqui.
- Repasse ao dentista e painel: ainda não existem. A ASB não tem acesso ao financeiro. O dentista só lê o extrato, e só se a clínica liberar.
- Gateway de pagamento: não existe de propósito (o projeto é um modelo). O recebimento é lançado à mão, sem conciliação nem confirmação externa.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `receivables` | sim | uma conta a receber (`entrada`, `parcela` n/N ou `avulsa`) |
| `payments` | sim | um recebimento ou o estorno dele; append-only |
| `payables` | sim | uma conta a pagar da clínica |
| `financial_settings` | sim | configuração da clínica, uma linha por clínica (`uq_financial_settings_clinic`). Sem linha vale o padrão: dentista sem acesso |

Migrações: `alembic/versions/0014_financeiro.py` (contas e recebimentos) e `0022_financeiro_configuracao.py` (configuração, sem gatilhos nem REVOKE: é editável, diferente das tabelas de dinheiro). Pontos que não são óbvios pelo model:

- FKs compostas com `clinic_id` e `patient_id`. Conta, plano e paciente são sempre da mesma clínica, e o recebimento herda o paciente da conta. O model e a migração declaram as mesmas constraints.
- `payments.amount` é negativo no estorno. O CHECK `sign_by_kind` amarra o sinal a `reversal_of`, e `fee_sign` faz a taxa seguir o sinal.
- `uq_payments_one_reversal` (índice único parcial) permite no máximo um estorno por recebimento.
- CHECKs `installment_numbers` e `plan_unless_avulsa`: parcela exige numeração, e só a conta avulsa fica sem plano.
- Três gatilhos `BEFORE`, todos levantando `check_violation`:
  - `payment_guard` (INSERT em `payments`). Trava a conta com `FOR UPDATE`. Impede recebimento em conta cancelada, estorno que não anula exatamente o original, estorno de estorno e total recebido fora de `[0, amount]`.
  - `receivable_guard` (UPDATE em `receivables`). Paciente, plano, tipo e clínica não mudam. Conta cancelada não muda. Com recebimento, valor e vencimento não mudam. Só cancela com saldo recebido igual a zero.
  - `payable_guard`. Conta a pagar que não está `aberta` não muda mais.
- Permissões: a migração revoga do `odonto_app` UPDATE/DELETE/TRUNCATE em `payments` e DELETE/TRUNCATE em `receivables` e `payables`. Contas só se cancelam, recebimentos só se estornam.

## API

Prefixo `/financeiro`. Caixa = admin, gestor, recepção. Gestão = admin, gestor.

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/receber` | caixa | Lista contas com filtros de paciente e vencimento; canceladas ficam fora por padrão; audita |
| POST | `/receber` | caixa | Cria conta avulsa |
| POST | `/planos/{plan_id}/parcelamento` | caixa | Gera entrada e parcelas do orçamento aprovado |
| POST | `/planos/{plan_id}/parcelamento/cancelar` | gestão | Cancela todas as contas abertas do plano (só se nenhuma tiver recebimento) |
| POST | `/receber/{id}/cancelar` | gestão | Cancela uma conta sem saldo recebido |
| POST | `/receber/{id}/pagamentos` | caixa | Registra recebimento |
| POST | `/pagamentos/{id}/estornar` | gestão | Cria o lançamento negativo que anula o recebimento |
| GET | `/pacientes/{id}/extrato` | caixa; dentista se liberado | Contas (inclusive canceladas), recebimentos e totais do paciente; audita |
| GET/POST | `/pagar` | gestão | Lista e cria contas a pagar |
| POST | `/pagar/{id}/pagar` | gestão | Marca como paga |
| POST | `/pagar/{id}/cancelar` | gestão | Cancela |
| GET | `/configuracao` | caixa, dentista | Lê a configuração (`dentist_can_view`) |
| PUT | `/configuracao` | gestão | Grava a configuração; audita |

Respostas fora do padrão:
- Extrato lido por dentista com a configuração desligada responde 403 em português (`router.py:statement`). O papel passa em `require_roles`, e a checagem da configuração é feita dentro da rota.
- `NotFound` do service vira 404 e `RuleViolation` vira 409 (`router.py:_http`), com mensagem em português.
- Qualquer `IntegrityError` que escape (corrida, gatilho, CHECK) é convertido em **409** genérico pelo handler global de `app/main.py`, não em 500. A mensagem do gatilho não chega ao cliente.
- Criar conta a pagar não captura `FinanceError`. O service não levanta nenhum nesse caminho.

## Regras de negócio e invariantes

- Só orçamento `aprovado` ou `concluido` é parcelado, e só um parcelamento ativo por plano (`service.py:installment_plan`). Para refazer, cancela-se o parcelamento antes.
- O valor parcelado é `approved_total` calculado na hora por `plan_rules.totals` (itens + desconto). O parcelamento não guarda vínculo com a versão do orçamento (ver Armadilhas).
- A soma de entrada e parcelas é exatamente o total. Os centavos que sobram da divisão vão na 1ª parcela (`regras.py:split`). Se o resto é zero, `installments` deve ser 0. Máximo de 48 parcelas.
- Vencimentos mensais usam `regras.add_months`, que recua para o fim do mês quando o dia não existe. Padrões: entrada hoje, 1ª parcela um mês depois da entrada. A 1ª parcela não vence antes da entrada.
- Recebimento: valor até o saldo da conta, data não futura, conta não cancelada. O service verifica antes, e o gatilho `payment_guard` garante sob concorrência.
- A taxa é calculada no servidor a partir de `fee_pct` (`regras.fee`), e o líquido é `amount - fee`. O cliente não envia valor de taxa.
- Estorno: usa a data de hoje, copia método e taxa com sinal invertido, e não pode ser estornado. O recebimento original permanece e o saldo da conta volta.
- Todas as escritas sobre uma conta pegam `SELECT ... FOR UPDATE` na conta (`service.get_receivable(lock=True)`). O estorno trava a conta do recebimento, não o recebimento. O parcelamento trava o plano (`plan_service.get_plan(lock=True)`) para duas requisições não gerarem contas duplicadas.
- Status é derivado (`regras.receivable_status`). "Vencida" compara o vencimento com o dia no fuso `clinic_timezone` (`service.today`), não com o UTC.
- Liberação do dentista: `service.dentist_can_view` lê a linha da clínica (isolada pelo RLS). `service.save_settings` faz upsert (`ON CONFLICT (clinic_id)`): a primeira gravação cria a linha e as seguintes atualizam. Liberar o extrato não libera o caixa: `/receber` e `/pagar` seguem 403 para o dentista.
- Dinheiro usa `Decimal` com 2 casas e `ROUND_HALF_UP` (`regras.money`).

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`. O RLS isola as três tabelas. Conta, recebimento ou plano de outra clínica responde 404, porque o RLS esconde a linha.
- O paciente é resolvido por `pacientes.service.get_patient`, e o plano por `tratamento.service.get_plan`. Os erros deles são traduzidos para `NotFound` do financeiro.
- O router chama `audit.record` com `action` em `financeiro.*` e faz o commit. Os `details` guardam ids, contagens e motivos, não valores de paciente além do necessário.

| action | quando |
|---|---|
| `contas_listadas` | GET `/receber` (leitura de dado de paciente) |
| `extrato_lido` | GET extrato |
| `conta_criada` | conta avulsa |
| `parcelamento_criado` / `parcelamento_cancelado` | parcelamento do plano |
| `conta_cancelada` | cancelamento de uma conta |
| `recebimento_registrado` / `recebimento_estornado` | recebimentos |
| `configuracao_alterada` | PUT `/configuracao`; `details` com o novo valor e se mudou |
| `conta_pagar_criada` / `conta_pagar_paga` / `conta_pagar_cancelada` | contas a pagar |

Listar contas a pagar não é auditado.

## Decisões

| Decisão | Motivo |
|---|---|
| Recebimento append-only com estorno negativo | Dinheiro não se apaga nem se edita. O histórico fica completo e o saldo é a soma dos lançamentos. |
| Status derivado dos recebimentos, só o cancelamento é gravado | Evita status divergente do saldo. |
| Invariantes de valor em gatilho do banco, além do service | Duas requisições simultâneas passam juntas pelas checagens do service. O gatilho trava a conta e fecha a corrida. |
| Sem gateway de pagamento | O projeto é um modelo, e o registro é manual. `fee_pct` é informado pelo operador. |
| Parcelamento calculado no ato, sem vínculo de versão do orçamento | As contas passam a ser o compromisso financeiro, independente de edições posteriores do plano. |
| Recepção opera o caixa, mas não cancela nem estorna | Desfazer lançamento exige gestão. |
| Dentista lê o extrato por opção da clínica, desligado por padrão | Nem toda clínica quer o dentista vendo valores do paciente. Só leitura: o caixa continua com recepção e gestão. |

## Como estender

- **Novo meio de pagamento:** adicione ao `PaymentMethod` em `models.py` e ao CHECK `method_valid` e `paid_method_valid` em uma migração nova. Não edite a 0014.
- **Nova tabela do módulo:** `TenantMixin`, `enable_tenant_rls` na migração, import em `app/models.py` e inclusão no `TRUNCATE` de `clean_db` (`tests/conftest.py`). Se for financeira, revogue UPDATE/DELETE como na 0014.
- **Nova regra de valor:** ponha a conta pura em `regras.py` (testes sem banco em `test_financeiro_unit.py`). Se protege dinheiro, replique no gatilho.
- **Novo relatório:** use `service.rows_for`, que calcula pago e status em lote (uma query de soma), em vez de calcular por conta.

## Armadilhas

- O dentista liberado lê o extrato de **qualquer** paciente da clínica, não só dos que atende: `statement` não restringe por vínculo. A configuração é tudo ou nada.
- `PUT /configuracao` com o mesmo valor não dá erro e ainda grava auditoria (`mudou=false`) e atualiza `updated_at`/`updated_by`. `GET /configuracao` é aberto ao dentista, mas não à ASB.
- As contas **não acompanham** o plano depois do parcelamento. Cancelar item aprovado em `tratamento.service.cancel_item` não altera nem cancela as parcelas. Nenhum código do módulo `tratamento` conhece o financeiro. A coerência é manual: cancelar o parcelamento e refazê-lo.
- Cancelar o parcelamento de um plano com qualquer recebimento é bloqueado (inclusive de uma só parcela). É preciso estornar antes. Um recebimento estornado deixa saldo zero e libera o cancelamento, mas o original permanece no extrato.
- `Payment.paid` do extrato soma todos os lançamentos, estornos inclusive, e `total` ignora contas canceladas. O `balance` do extrato é `total - paid`.
- Erro de gatilho chega ao cliente como 409 genérico ("Conflito com dados existentes"), sem o motivo. As mensagens claras vêm só das checagens do service, e o 409 genérico é o sinal de corrida ou de regra do banco.
- `list_receivables` limita a 500 por chamada e ordena por vencimento. Só o extrato lista sem limite.
- O estorno sempre usa a data de hoje, não a do recebimento original. Isso afeta qualquer relatório por `paid_on`.
- `GET /pagar` não é auditado, e criar conta a pagar não trata `FinanceError`.
- O `odonto_app` nunca teve TRUNCATE (`roles.sql` só concede SELECT/INSERT/UPDATE/DELETE). O REVOKE de TRUNCATE na migração é defesa redundante. Os testes limpam as tabelas pelo role `odonto`.
