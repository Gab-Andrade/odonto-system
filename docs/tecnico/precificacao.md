---
modulo: precificacao
atualizado_em: 12bcf0e
---
# Precificação

> Tabelas de preço de procedimentos por clínica, versionadas, com herança entre tabelas, atribuição por escopo (clínica, dentista, convênio), resolução de preço com memória de cálculo congelável em snapshot e importação/exportação de planilhas.

## Responsabilidades

Dentro do módulo:
- Cadastro de tabelas de preço, suas versões (rascunho e publicada) e itens.
- Herança: uma tabela filha herda de uma tabela-pai e aplica um ajuste percentual, podendo sobrescrever itens.
- Atribuição de tabelas a escopos com prioridade.
- Resolução do preço de um procedimento (`service.py:resolve`) e congelamento do resultado (`service.py:freeze`).
- Importação de planilha CSV/.xlsx para o rascunho de uma tabela, em três passos (analisar, validar, aplicar), com perfis de mapeamento salvos e exportação no mesmo formato (`importacao.py`, `service.py:create_import`/`validate_import`/`apply_import`/`export_version_xlsx`).

Fora do módulo:
- Orçamento: guarda a referência a um `PriceSnapshot`, não recalcula preço. O módulo de orçamento ainda não existe neste código.
- Cadastro de convênios: não existe. `insurer_id` e `scope_id` de convênio são UUIDs sem validação nem FK (`service.py:create_assignment`).
- Papéis e vínculo do dentista: vêm de `identidade.service.active_role`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `price_tables` | sim | Tabela de preço; pode ter `parent_table_id` |
| `price_table_versions` | sim | Versão (rascunho ou publicada) com vigência e ajuste % |
| `price_items` | sim | Preço de um procedimento numa versão (override, numa tabela filha); `custom_fields` guarda colunas extras da planilha |
| `price_assignments` | sim | Liga tabela a escopo com prioridade |
| `price_snapshots` | sim | Resolução congelada com `trace` (JSONB); append-only |
| `import_jobs` | sim | Uma importação: linhas lidas (`rows`), mapeamento, relatório e versão aplicada |
| `import_profiles` | sim | Mapeamento de colunas salvo para reaproveitar |

Relações e restrições (migrações `0002_precificacao_tabelas.py` e `0003_precificacao_importacao.py`):
- Todas as referências internas usam FK composta `(id, clinic_id)`, apontando para `UNIQUE (id, clinic_id)`. A checagem de FK do PostgreSQL não passa pelo RLS, então sem isso uma linha poderia apontar para outra clínica. Os testes `test_rls_and_composite_fk_block_cross_clinic_rows` cobrem isso.
- Índice único parcial `uq_price_table_versions_one_draft`: no máximo um rascunho por tabela.
- `published_has_valid_from`: versão publicada sempre tem `valid_from`. `applied_has_version`: importação `aplicada` sempre tem `applied_version_id`.
- `uq_price_assignments_table_scope` usa `NULLS NOT DISTINCT`, para que a atribuição `clinica` (com `scope_id` nulo) também seja única por tabela. O CHECK `scope_id_consistent` exige `scope_id` nulo só para `clinica`.
- `ondelete`: versões, itens e `import_jobs.table_id` em CASCADE. Pai, atribuições, snapshots e `import_jobs.applied_version_id` em RESTRICT. Não existe endpoint de exclusão de tabela, versão, item ou importação (só `DELETE` de atribuição e de perfil).
- `price_snapshots`: `REVOKE UPDATE, DELETE, TRUNCATE` para `odonto_app` na migração. É a única tabela do módulo imutável no banco.
- Os enums são `String` com CHECK criado na migração (`native_enum=False`, `create_constraint=False` no model).
- `import_jobs` não guarda o arquivo: só nome, tamanho, sha256 e as linhas lidas em JSONB.

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
| GET | `/tabelas/{id}/versoes/{vid}/exportar` | READ | Baixa a versão em .xlsx, no formato aceito pela importação |
| GET | `/atribuicoes` | READ | Lista atribuições por prioridade |
| POST | `/atribuicoes` | MANAGE | Cria atribuição |
| DELETE | `/atribuicoes/{id}` | MANAGE | Remove atribuição (204) |
| POST | `/resolver` | READ | Simula a resolução; não grava |
| POST | `/snapshots` | READ | Resolve e congela |
| GET | `/snapshots/{id}` | READ | Lê snapshot |
| GET | `/importacoes/modelo` | MANAGE | Planilha-modelo |
| GET, POST | `/importacoes` | MANAGE | Lista; envia arquivo (multipart: `arquivo`, `table_id`, `aba`) e lê |
| GET | `/importacoes/{id}` | MANAGE | Detalha (com `amostra` das 10 primeiras linhas) |
| POST | `/importacoes/{id}/validar` | MANAGE | Aplica mapeamento, valida e calcula diferenças |
| POST | `/importacoes/{id}/aplicar` | MANAGE | Grava as linhas no rascunho |
| GET, POST | `/perfis-importacao` | MANAGE | Lista e cria perfis de mapeamento |
| DELETE | `/perfis-importacao/{id}` | MANAGE | Remove perfil (204) |

Códigos fora do padrão:
- Violação de regra de negócio (`RuleViolation`) responde 409 com `detail` em texto. `NotFound` responde 404 (`router.py:_http`). Erros de leitura da planilha (`SpreadsheetError`, `MappingError`) são convertidos em `RuleViolation`, logo também 409 (incluindo arquivo grande demais ou formato inválido).
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
- Arquivar tabela exige: nenhuma tabela filha **ativa** e nenhuma atribuição (`_ensure_can_archive`). Reativar exige pai ativo. Tabela arquivada não publica, não recebe atribuição nem importação.
- Atribuição a dentista exige vínculo ativo com papel `dentista` ou `admin` (`DENTIST_ROLES`, `ensure_dentist`). `freeze` repete essa checagem, pois o snapshot é imutável e não pode guardar dentista de outra clínica.
- Prioridade padrão: convênio 10, dentista 20, clínica 30. Menor vence, empate resolve por `created_at`.
- Preço congelado: o snapshot copia preço, descrição, categoria e o `trace`. Mudar ou arquivar tabelas depois não o afeta.

Resolução (`service.py:resolve`):
1. Candidatas: atribuições de clínica sempre, mais as de dentista e convênio se informados, de tabelas ativas, em ordem de prioridade.
2. Em cada candidata, usa a versão vigente na data (`effective_version`). Procura o item. Se não achar e houver pai ativo, resolve recursivamente no pai (mesma data) e aplica o ajuste da versão da filha.
3. A primeira candidata que resolve vence. Cada tentativa, inclusive as falhas com motivo, entra no `trace`.
4. Na herança, `version_id` e o passo do `trace` referem-se à versão da **filha**. Descrição e categoria vêm do item original do pai.

Importação (`service.py` seção "Importação de planilhas"; leitura e validação puras em `importacao.py`):
1. `create_import`: lê o arquivo (`parse_file`), sugere o mapeamento por sinônimos de cabeçalho (`suggest_mapping`) e grava o job `analisada`. Não toca na tabela.
2. `validate_import`: resolve o mapeamento (prioridade: `column_map` do corpo, depois perfil, depois sugestão), valida linha a linha, calcula as diferenças contra a **versão de referência** (`_reference_version`: o rascunho, se houver; senão a vigente hoje) e grava o relatório. Pode ser repetida até aplicar.
3. `apply_import`: exige `validada`, recusa se houver erros sem `ignorar_erros`, e **recusa se a tabela mudou desde a validação**. Isso é checado comparando id da versão de referência e `items_fingerprint` do conteúdo com os guardados em `report.versao_referencia`. Passando, regrava os itens do rascunho (cria um via `create_draft` se a referência era uma versão publicada) com `replace_items`, marca `aplicada` e zera `rows`. Nunca publica.
- Concorrência: `get_import(lock=True)` trava o job (`FOR UPDATE`, com `populate_existing`), e `apply_import` trava a linha da tabela. Duas aplicações na mesma tabela rodam em série e a segunda cai na checagem de impressão digital.
- Linhas com erro (campo obrigatório vazio, tamanho, preço inválido, código repetido na planilha) são descartadas só com `ignorar_erros`. Avisos (`is_ambiguous_price`, ex.: "1.500" lido como 1500) nunca bloqueiam.
- Preço aceita formato brasileiro e internacional (`parse_price`); rejeita negativo, mais de 2 casas e acima de `MAX_PRICE`.
- Limites: 2 MB, 5000 linhas, 100 colunas, 1000 caracteres por célula, proteção contra zip bomb em .xlsx (`_check_zip`). `.xls` é recusado com mensagem explicativa.
- Segurança da exportação: `build_xlsx` força toda célula de texto como string, para que valores começando com `=` não virem fórmula.

## Tenancy e auditoria

- Todos os endpoints usam `get_tenant_db`. O módulo nunca filtra `clinic_id` em consultas. `get_table`, `get_assignment`, `get_snapshot`, `get_import` e `get_profile` dependem do RLS para devolver 404 em dados de outra clínica.
- O router faz `audit.record` e depois `db.commit()`. O service só faz `flush`.
- Ações auditadas: `precificacao.tabela_criada`, `tabela_alterada`, `versao_criada`, `versao_alterada`, `itens_substituidos` (details só com a quantidade), `versao_publicada`, `atribuicao_criada`, `atribuicao_removida`, `snapshot_criado`, `importacao_criada` (arquivo, sha256, linhas), `importacao_validada`, `importacao_aplicada`, `perfil_criado`, `perfil_removido`. `/resolver`, o download do modelo e a exportação não auditam.
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
| Importação em 3 passos, aplicando só no rascunho | O usuário vê erros e diferenças antes de gravar, e a publicação continua explícita. |
| Linhas lidas ficam no banco (`rows` JSONB) em vez do arquivo | Validar de novo com outro mapeamento sem reenviar o arquivo; o arquivo não é armazenado. `rows` é zerado ao aplicar. |
| Impressão digital da versão de referência na validação | Evita aplicar um relatório de diferenças velho e apagar edições feitas no rascunho nesse meio-tempo. |
| Funções puras em `importacao.py` | Parsing e validação testáveis sem banco; o service só orquestra e grava. |

## Como estender

- **Novo tipo de escopo:** adicionar em `ScopeType`, ajustar o CHECK `scope_type_valid` e `scope_id_consistent` em nova migração, incluir a condição em `resolve`, a prioridade em `DEFAULT_PRIORITY` e a validação em `create_assignment`.
- **Validar convênio:** quando o módulo existir, validar em `create_assignment` (há comentário no ponto) e em `freeze` para `insurer_id`.
- **Novo campo importável de item:** incluir em `FIELDS`/`FIELD_LABELS`/`SYNONYMS` (e `FIELD_MAX_LEN`) em `importacao.py`, tratar em `validate_rows`, `compute_diff` e `items_fingerprint`, e em `_item_dicts`/`export_version_xlsx` no service. Se virar coluna, nova migração e ajuste de `ItemIn`/`ItemOut`.
- **Novo formato de arquivo:** adicionar um ramo em `parse_file` que devolva linhas `(número, células)` no mesmo formato e respeite `_RowCollector`.
- **Nova tabela:** `TenantMixin` no model, `enable_tenant_rls()` na migração, FK composta para tabelas do módulo e inclusão na lista de `TRUNCATE` do `clean_db`.
- **Novo endpoint que altere versão ou item:** chamar `_ensure_draft`, auditar e fazer o commit no router.

## Armadilhas

- Imutabilidade de versão publicada e de itens não tem proteção no banco, só no service.
- Unicidade de nome (tabela e perfil): o service compara em minúsculas, mas as constraints `uq_price_tables_clinic_name` e `uq_import_profiles_clinic_name` diferenciam maiúsculas. Duas requisições concorrentes ou escrita fora do service podem criar nomes que só diferem na caixa.
- Concorrência em `create_draft`, atribuição duplicada e criação de tabela/perfil: dependem do índice/constraint do banco. Não há tratamento de `IntegrityError` no router, então a corrida resultaria em erro 500 em vez de 409.
- `PUT /itens` (`replace_items`) não trava a tabela nem compara impressão digital, ao contrário de `apply_import`. Uma edição manual concorrente durante a aplicação pode não ser detectada se ocorrer depois da checagem; na prática o `apply_import` só protege contra edições entre validar e aplicar.
- Importar em tabela **filha** substitui todos os overrides: itens que não estão na planilha somem do rascunho e voltam a ser herdados. Aparece como "removidos" no relatório.
- Se a referência era uma versão publicada, `apply_import` chama `create_draft` (que copia todos os itens) e logo em seguida `replace_items` apaga essa cópia. É trabalho descartado, mas correto.
- Se alguém abrir um rascunho (ou o rascunho for criado) entre validar e aplicar, a versão de referência muda de id e a aplicação exige nova validação, mesmo sem alteração de preços.
- Jobs `analisada`/`validada` mantêm até 5000 linhas em JSONB e nunca são limpos (não há endpoint de exclusão nem expiração). Em job `aplicada`, `rows` é vazio, então `amostra` volta vazia e o job não pode ser revalidado (`validate_import` recusa).
- `create_import` lê o arquivo inteiro em memória (até 2 MB + 1 byte) antes de validar o tamanho em `parse_file`.
- `create_profile` valida os campos do mapeamento, mas não os nomes de colunas; só `validate_import` confere se as colunas existem na planilha. `extra_columns` do perfil não é validado na criação.
- `/resolver` e `/snapshots` não validam `dentist_id` ou `insurer_id` na resolução. Só `freeze` valida o dentista, e o convênio nunca é validado. Um `dentist_id` inválido no `/resolver` apenas não casa com nenhuma atribuição.
- Reajuste na tabela-pai muda o preço resolvido das filhas imediatamente (a filha resolve o pai na data consultada). Só snapshots antigos preservam o valor.
- Ao arquivar um pai, só filhas ativas bloqueiam. Uma filha arquivada continua apontando para ele, e reativá-la exige o pai ativo.
- `ensure_dentist` aceita `admin`, por isso `scope_id` de dentista pode ser um admin.
- Várias respostas 404 compartilham status (ver API). Há uma diferença de corpo. Erros de planilha respondem 409, não 400/413/422.
- `PATCH` de tabela com `status` nulo é ignorado em silêncio.
