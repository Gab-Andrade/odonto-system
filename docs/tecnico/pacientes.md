---
modulo: pacientes
atualizado_em: a86b581
---
# Pacientes

> Cadastro de pacientes da clínica (busca por nome, CPF ou telefone) e registro de consentimentos LGPD como eventos append-only.

## Responsabilidades

- Cadastro e alteração de dados pessoais, responsável legal de menores, desativação e busca.
- Consentimentos por finalidade (`tratamento_dados`, `comunicacao`, `uso_imagem`), com histórico e estado atual.
- **Fora do módulo:** conteúdo clínico (anamnese, evolução, odontograma), agenda e financeiro. Ficarão em módulos próprios do prontuário, com regras de papel próprias. Aqui todos os papéis da clínica acessam só o cadastro.
- Não há exclusão de paciente, só `active=false`. O prontuário tem guarda mínima de 20 anos (`models.py`, docstring).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `patients` | sim | Ficha cadastral do paciente |
| `patient_consents` | sim | Eventos de consentimento (aceite ou revogação), append-only |

- `patients` tem `UNIQUE (id, clinic_id)` para servir de alvo da FK composta de `patient_consents` (`fk_patient_consents_patient_same_clinic`). Assim o banco impede consentimento ligado a paciente de outra clínica, além do RLS.
- CPF é opcional, mas único por clínica via índice parcial `uq_patients_clinic_cpf (clinic_id, cpf) WHERE cpf IS NOT NULL`. O índice inclui `clinic_id` porque a checagem de unicidade ignora o RLS: sem isso, o CPF de uma clínica bloquearia outra.
- CHECKs de formato (`cpf_digits`, `guardian_cpf_digits`, `phone_digits`) existem só na migração `0007_pacientes.py`. Os enums (`sex`, `purpose`, `given_by`) têm CHECK criado na migração (`create_constraint=False` no model).
- `search_name` é derivado (nome + nome social, minúsculo e sem acento) e tem índice GIN `gin_trgm_ops`. A migração cria a extensão `pg_trgm` e **não** a remove no downgrade.
- `patient_consents` é append-only para `odonto_app` (REVOKE UPDATE/DELETE/TRUNCATE na migração). Revogar é inserir novo evento com `granted=false`. Não tem `updated_at`.
- `created_by` e `recorded_by` usam `ON DELETE SET NULL` para `users`.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/pacientes` | admin, gestor, dentista, asb, recepcao | Busca paginada (`busca`, `incluir_inativos`, `limit`, `offset`); devolve resumo com CPF mascarado |
| POST | `/pacientes` | idem | Cadastra |
| GET | `/pacientes/{id}` | idem | Ficha completa (CPF inteiro) |
| PATCH | `/pacientes/{id}` | idem | Altera só campos enviados; `active=false` desativa |
| GET | `/pacientes/{id}/consentimentos` | idem | Estado atual por finalidade (`atuais`) e `historico` |
| POST | `/pacientes/{id}/consentimentos` | idem | Registra aceite ou revogação |

Erros de regra (`RuleViolation`) viram **409** com `detail` em texto. Paciente inexistente ou de outra clínica vira **404** (`router.py:_http`). Validação de formato (CPF, telefone, CEP, e-mail) vira 422 pelo Pydantic.

## Regras de negócio e invariantes

- CPF e telefone são guardados só com dígitos. O CPF é validado pelos dígitos verificadores (`dados.py:normalize_cpf`, aplicado em `schemas.py`). Telefone aceita 8 a 15 dígitos.
- CPF único por clínica: checagem prévia em `service.py:_ensure_cpf_free` (gera 409 amigável), com o índice parcial como garantia final.
- Menor de 18 anos exige `guardian_name`; CPF do responsável não pode ser igual ao do paciente (`service.py:_check`, rodado depois de aplicar as mudanças, tanto no create quanto no update). A idade usa a data no fuso `clinic_timezone` (`service.py:today`).
- `full_name`, `phone` e `active` não aceitam `null` no PATCH, mesmo que o schema permita (`service.py:update_patient`, 409). Para os demais campos opcionais, `null` limpa o valor.
- `search_name` é recalculado em todo create e update (`service.py`). Qualquer escrita fora do service deixa a busca desatualizada.
- Consentimento: dado pelo responsável exige `guardian_name` cadastrado, e paciente menor só aceita `given_by=responsavel` (`service.py:record_consent`).
- Estado atual do consentimento é o evento mais recente por finalidade (`service.py:current_consents`, depende de `list_consents` ordenar do mais novo ao mais antigo).
- Busca (`service.py:search_patients`): termo sem nenhuma letra e com pelo menos 4 dígitos vira busca por CPF exato ou telefone contendo os dígitos (`phone`/`phone_alt`). Caso contrário, cada palavra do termo vira um `LIKE %palavra%` em `search_name` (AND). Limite efetivo máximo de 100 (`MAX_SEARCH_RESULTS`). Ordena por `search_name, id`.
- A listagem mascara o CPF (`dados.py:mask_cpf`); só a ficha devolve o CPF inteiro.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`; nenhuma consulta filtra `clinic_id`. `get_patient` usa `db.get`, e o RLS faz paciente de outra clínica cair em 404.
- O service faz `flush` e o router faz `commit`. A auditoria é gravada na mesma transação.
- **Leitura também é auditada** (LGPD). Os `details` levam só nomes de campo ou contagens, nunca valores. O termo de busca não é guardado, porque pode ser CPF ou telefone.

| `action` | Quando |
|---|---|
| `pacientes.busca` | Cada busca (`resultados`, `com_termo`) |
| `pacientes.cadastrado` | POST |
| `pacientes.ficha_lida` | GET da ficha |
| `pacientes.ficha_alterada` | PATCH com ao menos um campo realmente alterado (`campos`) |
| `pacientes.consentimentos_lidos` | GET de consentimentos |
| `pacientes.consentimento_registrado` | POST de consentimento (`finalidade`, `aceito`) |

## Decisões

| Decisão | Motivo |
|---|---|
| Desativar em vez de excluir | Guarda mínima de 20 anos do prontuário (Lei 13.787/2018) |
| Consentimento como eventos append-only | Funciona como prova; revogação não apaga o aceite anterior |
| Auditar leituras e buscas | Dado pessoal e de saúde (LGPD); registra quem consultou |
| `search_name` desnormalizado + trigrama | Busca sem acento por trecho do nome, com índice |
| FK composta `(patient_id, clinic_id)` | Garante no banco que consentimento e paciente são da mesma clínica |
| Cadastro aberto a todos os papéis | Recepção e ASB operam o cadastro; o dado clínico terá regras próprias em outros módulos |

## Como estender

- **Novo campo no cadastro:** adicione ao model, a `PatientFields` e `PatientOut` (e a `PatientSummary`, se aparecer na listagem), e crie migração (`nova-migracao`). Se o campo for dado de texto buscável, inclua-o em `dados.py:search_name`. Se for obrigatório, acrescente-o a `REQUIRED_FIELDS` em `service.py`.
- **Nova finalidade de consentimento:** inclua em `ConsentPurpose` e altere o CHECK `purpose_valid` em nova migração. `current_consents` passa a incluí-la sozinho, via `dict.fromkeys`.
- **Novo módulo clínico que referencia paciente:** use FK composta `(patient_id, clinic_id)` para `patients`, como em `patient_consents`.
- **Restringir papéis:** altere a tupla `CADASTRO` em `router.py`.

## Armadilhas

- `schemas.py:_birth_not_future` compara com `date.today()` (fuso do servidor), enquanto as regras de menoridade usam o fuso da clínica (`service.today`). Perto da meia-noite pode haver divergência de um dia.
- `list_consents` ordena por `created_at desc`, e `created_at` vem de `now()` do banco, que é o início da transação. Eventos da mesma finalidade gravados na mesma transação empatam e o desempate por `id` (UUID) é arbitrário. Hoje cada POST é uma transação, então não ocorre.
- Mudar o consentimento de um menor que vira adulto, ou remover o responsável depois do consentimento, não revalida eventos antigos. A regra só vale no momento do registro.
- PATCH com `cpf: null` limpa o CPF, mas `phone: null` e `full_name: null` dão 409 (não 422).
- `pacientes.ficha_alterada` só é gravada se algum valor mudou. Um PATCH sem mudança real não gera auditoria.
- `limit` acima de 100 é rejeitado com 422 pela query; `min(limit, MAX_SEARCH_RESULTS)` no service é só defesa extra.
- O downgrade da `0007` mantém a extensão `pg_trgm`.
