---
modulo: precificacao
atualizado_em: 6b1d10b
---
# Precificação

> Tabelas de preço de procedimentos por clínica, versionadas, com herança entre tabelas, atribuição por escopo (clínica, dentista, convênio) e resolução de preço com memória de cálculo congelável em snapshot.

## Responsabilidades

Dentro do módulo:
- Cadastro de tabelas de preço, suas versões (rascunho e publicada) e itens.
- Herança: uma tabela filha herda de uma tabela-pai e aplica um ajuste percentual, podendo sobrescrever itens.
- Atribuição de tabelas a escopos com prioridade.
- Resolução do preço de um procedimento (`service.py:resolve`) e congelamento do resultado (`service.py:freeze`).

Fora do módulo:
- Orçamento: guarda a referência a um `PriceSnapshot`, não recalcula preço. O módulo de orçamento ainda não existe neste código.
- Cadastro de convênios: não existe. `insurer_id` e `scope_id` de convênio são UUIDs sem validação nem FK (`service.py:create_assignment`).
- Importação de itens (planilha): prevista. Ela deve reutilizar `service.py:replace_items`.
- Papéis e vínculo do dentista: vêm de `identidade.service.active_role`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `price_tables` | sim | Tabela de preço; pode ter `parent_table_id` |
| `price_table_versions` | sim | Versão (rascunho ou publicada) com vigência e ajuste % |
| `price_items` | sim | Preço de um procedimento numa versão (override, numa tabela filha) |
| `price_assignments` | sim | Liga tabela a escopo com prioridade |
| `price_snapshots` | sim | Resolução congelada com `trace` (JSONB); append-only |

Relações e restrições (migração `0002_precificacao_tabelas.py`):
- Todas as referências internas usam FK composta `(id, clinic_id)`, apontando para `UNIQUE (id, clinic_id)`. A checagem de FK do PostgreSQL não passa pelo RLS, então sem isso uma linha poderia apontar para outra clínica. Os testes `test_rls_and_composite_fk_block_cross_clinic_rows` cobrem isso.
- Índice único parcial `uq_price_table_versions_one_draft`: no máximo um rascunho por tabela.
- `published_has_valid_from`: versão publicada sempre tem `valid_from`.
- `uq_price_assignments_table_scope` usa `NULLS NOT DISTINCT`, para que a atribuição `clinica` (com `scope_id` nulo) também seja única por tabela. O CHECK `scope_id_consistent` exige `scope_id` nulo só para `clinica`.
- `ondelete`: versões e itens em CASCADE. Pai, atribuições e snapshots em RESTRICT. Não existe endpoint de exclusão de tabela, versão ou item (só `DELETE` de atribuição).
- `price_snapshots`: `REVOKE UPDATE, DELETE, TRUNCATE` para `odonto_app` na migração. É a única tabela do módulo imutável no banco.
- Os enums são `String` com CHECK criado na migração (`native_enum=False`, `create_constraint=False` no model).

## API

Prefixo `/precificacao`. `MANAGE` = admin, gestor. `READ` = admin, gestor, dentista, recepcao (ASB não acessa nada do módulo).

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/tabelas`, `/tabelas/{id}` | READ | Lista e detalha tabelas |
| POST | `/tabelas` | MANAGE | Cria tabela e já abre a versão 1 em rascunho |
| PATCH | `/tabelas/{id}` | MANAGE | Renomeia, altera descrição, arquiva ou reativa |
| GET | `/tabelas/{id}/versoes` | READ | Lista versões, da mais nova para a mais antiga |
| POST | `/tabelas/{id}/versoes` | MANAGE | Abre rascunho copiando a última versão publicada |
| PATCH | `/tabelas/{id}/versoes/{vid}` | MANAGE | Altera o ajuste % do rascunho |
| GET | `/tabelas/{id}/versoes/{vid}/itens` | READ | Lista itens |
| PUT | `/tabelas/{id}/versoes/{vid}/itens` | MANAGE | Substitui todos os itens do rascunho |
| POST | `/tabelas/{id}/versoes/{vid}/publicar` | MANAGE | Publica o rascunho com `valid_from` |
| GET | `/atribuicoes` | READ | Lista atribuições por prioridade |
| POST | `/atribuicoes` | MANAGE | Cria atribuição |
| DELETE | `/atribuicoes/{id}` | MANAGE | Remove atribuição (204) |
| POST | `/resolver` | READ | Simula a resolução; não grava |
| POST | `/snapshots` | READ | Resolve e congela |
| GET | `/snapshots/{id}` | READ | Lê snapshot |

Códigos fora do padrão:
- Violação de regra de negócio (`RuleViolation`) responde 409 com `detail` em texto. `NotFound` responde 404 (`router.py:_http`).
- `/resolver` e `/snapshots` respondem 404 com **corpo próprio** `{"detail", "trace"}` quando nenhuma tabela resolve (`router.py:_not_found`). O mesmo status 404 também é usado para tabela, versão ou snapshot inexistente, sem `trace`. Para diferenciar, o cliente precisa olhar a presença de `trace`.
- Tabela de outra clínica aparece como 404, pois o RLS a esconde.

## Regras de negócio e invariantes

- Versão publicada e seus itens são imutáveis, garantido **só no service** (`service.py:_ensure_draft`, usado por `update_draft`, `replace_items` e `publish`). Nada no banco impede um UPDATE direto. Qualquer escrita nova em versão ou item precisa chamar `_ensure_draft`.
- Mudança de preço exige nova versão: `create_draft` copia itens e ajuste da última publicada (`_last_published`).
- `valid_from` não pode estar no passado nem antes da `valid_from` da última publicada (`service.py:check_valid_from`). Igualdade é permitida, e o desempate na vigência é o maior número de versão (`effective_version`).
- "Hoje" é calculado no fuso `clinic_timezone` (`service.py:today`), não em UTC.
- Tabela sem pai não publica versão sem itens. Tabela filha pode publicar vazia (herda tudo) (`service.py:publish`).
- Ajuste percentual só existe em tabela com pai, na criação e no `update_draft`. `parent_table_id` é fixado na criação e não há como alterá-lo. Por isso não há ciclo de herança possível, e `MAX_INHERITANCE_DEPTH = 10` é só salvaguarda.
- Ajuste: `preço * (100 + pct) / 100`, arredondado a centavos com `ROUND_HALF_UP`. Resultado acima de `MAX_PRICE` vira "não encontrado" naquela tabela, não erro (`_resolve_in_table`).
- Arquivar tabela exige: nenhuma tabela filha **ativa** e nenhuma atribuição (`_ensure_can_archive`). Reativar exige pai ativo. Tabela arquivada não publica nem recebe atribuição.
- Atribuição a dentista exige vínculo ativo com papel `dentista` ou `admin` (`DENTIST_ROLES`, `ensure_dentist`). `freeze` repete essa checagem, pois o snapshot é imutável e não pode guardar dentista de outra clínica.
- Prioridade padrão: convênio 10, dentista 20, clínica 30. Menor vence, empate resolve por `created_at`.
- Preço congelado: o snapshot copia preço, descrição, categoria e o `trace`. Mudar ou arquivar tabelas depois não o afeta.

Resolução (`service.py:resolve`):
1. Candidatas: atribuições de clínica sempre, mais as de dentista e convênio se informados, de tabelas ativas, em ordem de prioridade.
2. Em cada candidata, usa a versão vigente na data (`effective_version`). Procura o item. Se não achar e houver pai ativo, resolve recursivamente no pai (mesma data) e aplica o ajuste da versão da filha.
3. A primeira candidata que resolve vence. Cada tentativa, inclusive as falhas com motivo, entra no `trace`.
4. Na herança, `version_id` e o passo do `trace` referem-se à versão da **filha**. Descrição e categoria vêm do item original do pai.

## Tenancy e auditoria

- Todos os endpoints usam `get_tenant_db`. O módulo nunca filtra `clinic_id` em consultas. `get_table`, `get_assignment` e `get_snapshot` dependem do RLS para devolver 404 em dados de outra clínica.
- O router faz `audit.record` e depois `db.commit()`. O service só faz `flush`.
- Ações auditadas: `precificacao.tabela_criada`, `tabela_alterada`, `versao_criada`, `versao_alterada`, `itens_substituidos` (details só com a quantidade), `versao_publicada`, `atribuicao_criada`, `atribuicao_removida`, `snapshot_criado`. `/resolver` não audita (não grava).
- Em `tabela_alterada` e `versao_alterada`, `details` guarda os valores como `str`.

## Decisões

| Decisão | Motivo |
|---|---|
| Versionamento com rascunho e publicação | Mudar preço não pode reescrever o histórico. A vigência por data permite agendar reajuste. |
| Ajuste % na versão, não na tabela | Alterar o ajuste também gera histórico. |
| Herança resolvida em tempo de consulta (não materializada) | Reajuste na tabela-pai propaga para as filhas sem republicar, e filhas guardam só overrides. |
| Snapshot com cópia dos valores e `trace` | O orçamento fica estável sem depender da imutabilidade das versões, o que justifica deixá-la só no service. |
| FK composta `(id, clinic_id)` | A FK do PostgreSQL ignora o RLS, então esta é a barreira contra referência entre clínicas. |
| `scope_id` sem FK | O alvo depende do tipo de escopo (usuário ou convênio). |
| Falha de resolução devolve o `trace` | Permite explicar a quem monta o orçamento por que não achou preço. |
| `PUT` de itens substitui tudo | É o mesmo fluxo que a futura importação usará. |

## Como estender

- **Novo tipo de escopo:** adicionar em `ScopeType`, ajustar o CHECK `scope_type_valid` e `scope_id_consistent` em nova migração, incluir a condição em `resolve`, a prioridade em `DEFAULT_PRIORITY` e a validação em `create_assignment`.
- **Validar convênio:** quando o módulo existir, validar em `create_assignment` (há comentário no ponto) e em `freeze` para `insurer_id`.
- **Importação de itens:** gerar a lista de dicts e chamar `replace_items` no rascunho. Limite atual de 5000 itens por requisição (`ItemsReplace`).
- **Nova tabela:** `TenantMixin` no model, `enable_tenant_rls()` na migração, FK composta para tabelas do módulo e inclusão na lista de `TRUNCATE` do `clean_db`.
- **Novo endpoint que altere versão ou item:** chamar `_ensure_draft`, auditar e fazer o commit no router.

## Armadilhas

- Imutabilidade de versão publicada e de itens não tem proteção no banco, só no service.
- Unicidade de nome: o service compara em minúsculas (`_ensure_unique_name`), mas a constraint do banco `uq_price_tables_clinic_name` diferencia maiúsculas. Duas requisições concorrentes ou escrita fora do service podem criar nomes que só diferem na caixa.
- Concorrência em `create_draft` e em atribuição duplicada: dependem do índice/constraint do banco. Não há tratamento de `IntegrityError` no router, então a corrida resultaria em erro 500 em vez de 409.
- `/resolver` e `/snapshots` não validam `dentist_id` ou `insurer_id` na resolução. Só `freeze` valida o dentista, e o convênio nunca é validado. Um `dentist_id` inválido no `/resolver` apenas não casa com nenhuma atribuição.
- Reajuste na tabela-pai muda o preço resolvido das filhas imediatamente (a filha resolve o pai na data consultada). Só snapshots antigos preservam o valor.
- Ao arquivar um pai, só filhas ativas bloqueiam. Uma filha arquivada continua apontando para ele, e reativá-la exige o pai ativo.
- `ensure_dentist` aceita `admin`, por isso `scope_id` de dentista pode ser um admin.
- Várias respostas 404 compartilham status (ver API). Há uma diferença de corpo.
- `PATCH` de tabela com `status` nulo é ignorado em silêncio.
