---
modulo: prontuario
atualizado_em: 4346a5f
---
# Prontuário

> Anamnese configurável por clínica: modelos de formulário versionados, respostas imutáveis por paciente e alertas clínicos (ex.: alergia) para o cabeçalho do paciente.

## Responsabilidades

Hoje o módulo só tem a **anamnese**. Evolução clínica e atendimento virão depois neste mesmo módulo.

- Dentro: modelos de anamnese e suas versões (rascunho, publicada, substituída), respostas do paciente, cálculo de alertas, auditoria de toda leitura e escrita de dado clínico.
- Fora: cadastro do paciente e consentimentos (`pacientes`); o módulo só usa `pacientes.service.get_patient` (`prontuario/service.py:get_patient`, que converte o `NotFound` de pacientes no do próprio módulo). Agendamento fica em `agenda`.
- Regras puras (validação de perguntas, respostas e alertas) ficam em `prontuario/anamnese.py`, sem acesso a banco. O `service.py` orquestra e o router faz commit e auditoria.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `anamnesis_templates` | sim | Modelo de formulário (nome único por clínica, flag `active`) |
| `anamnesis_template_versions` | sim | Versões do modelo; guarda as perguntas em JSONB |
| `anamnesis_responses` | sim | Resposta de um paciente a uma versão; guarda respostas e alertas congelados |

Restrições que não são óbvias pelo model (todas na migração `0009_prontuario_anamnese.py`):

- Máximo de **um rascunho e uma publicada por modelo**: dois índices únicos parciais em `template_id` (`uq_anamnesis_template_versions_one_draft` e `_one_published`).
- CHECK `(status = 'rascunho') = (published_at IS NULL)`: publicada e substituída sempre têm `published_at`.
- FKs compostas com `clinic_id` (`fk_..._same_clinic`, `fk_anamnesis_responses_version_same_template`) impedem referência entre clínicas e garantem que a versão da resposta pertence ao `template_id` informado.
- **Gatilho `anamnesis_version_guard`** (BEFORE UPDATE/DELETE em versões): depois de sair de rascunho, a versão não muda `questions`, não volta a `rascunho` e não pode ser apagada; `number`, `template_id` e `clinic_id` nunca mudam. Só rascunho pode ser apagado. Vale também para o dono do schema.
- `anamnesis_responses` é **append-only**: a migração revoga UPDATE/DELETE/TRUNCATE do `odonto_app`. Não tem `updated_at`.
- Todas as FKs para versões e pacientes são `RESTRICT`: nada que tem resposta pode ser apagado.

## API

Prefixo `/prontuario`. Papéis: LER = admin, gestor, dentista, asb; PREENCHER = admin, dentista, asb; GERIR = admin, gestor. **Recepção não acessa nada** (é conteúdo clínico).

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/anamnese/modelos` | LER | Lista modelos com resumo da publicada e do rascunho (`incluir_inativos`) |
| POST | `/anamnese/modelos` | GERIR | Cria modelo + rascunho nº 1 |
| GET | `/anamnese/modelos/{id}` | LER | Detalhe com histórico de versões |
| PATCH | `/anamnese/modelos/{id}` | GERIR | Altera nome, descrição, `active` |
| POST | `/anamnese/modelos/{id}/rascunho` | GERIR | Novo rascunho, copiando a publicada |
| GET | `/anamnese/versoes/{id}` | LER | Versão com perguntas |
| PUT | `/anamnese/versoes/{id}` | GERIR | Substitui as perguntas do rascunho |
| DELETE | `/anamnese/versoes/{id}` | GERIR | Descarta rascunho (204) |
| POST | `/anamnese/versoes/{id}/publicar` | GERIR | Publica o rascunho |
| POST | `/pacientes/{id}/anamneses` | PREENCHER | Registra uma resposta |
| GET | `/pacientes/{id}/anamneses` | LER | Histórico do paciente |
| GET | `/pacientes/{id}/alertas` | LER | Alertas das respostas atuais |
| GET | `/anamneses/{id}` | LER | Resposta com as perguntas da versão usada |

Erros: `ProntuarioError` vira 404 (`NotFound`) ou **409** (`RuleViolation`) em `router.py:_http`. Validação de pergunta malformada é 422 (pydantic). Um `IntegrityError` que escape das checagens (corrida por nome duplicado, segundo rascunho, gatilho da versão) é convertido em **409 genérico** pelo handler global em `app/main.py`, não em 500.

## Regras de negócio e invariantes

- Só o rascunho é editável ou descartável (`service.py:_ensure_draft`); o gatilho repete isso no banco.
- Publicar exige ao menos uma pergunta (`service.py:publish`). A publicada anterior vira `substituida` com um `flush` **antes** de promover a nova, porque o índice único parcial não tolera duas publicadas e o flush não garante a ordem dos UPDATEs.
- Número da versão = `max(number) + 1` do modelo (`service.py:create_draft`), contando as substituídas.
- Responder só é possível se: paciente ativo, modelo ativo, existe publicada e `version_id` enviado é a publicada atual (senão 409 pedindo recarregar) (`service.py:record_response`).
- Validação das respostas (`anamnese.py:validate_answers`): id desconhecido é erro; vazio (`None`, texto em branco, lista vazia) conta como não respondido e é descartado; obrigatória sem resposta é erro; múltipla é reordenada na ordem do formulário e sem repetição; número rejeita `bool`, NaN/infinito e `abs > 1e9`; data só `AAAA-MM-DD` real.
- Alertas (`anamnese.py:compute_alerts`) só vêm de perguntas com `alert`. Em múltipla com `alert_options`, o alerta guarda apenas as opções que disparam. Regras por tipo estão no docstring do arquivo.
- Os alertas são **gravados na resposta** com o texto da pergunta no momento do preenchimento (snapshot), então editar o modelo depois não muda alertas antigos.
- "Resposta atual" = a mais recente por modelo (`created_at desc, id desc`) via `DISTINCT ON (template_id)` (`service.py:_current_ids`). Alertas do paciente consideram só as respostas atuais.
- Coerência de pergunta (`anamnese.py:check_question` e `check_questions`): escolhas têm 2 a 50 opções sem repetição (ignorando caixa); `options` só em escolha; `alert_options` exige `alert` e estar contido em `options`; ids únicos; máximo 150 perguntas. O pydantic chama essas funções em `schemas.py` (`Question._coherent`, `_checked`).

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`. Modelo, versão ou resposta de outra clínica aparece como 404 pelo RLS (sem filtro manual de `clinic_id`).
- Toda leitura de dado de paciente é auditada, inclusive GET. Os `details` nunca carregam respostas, só ids e contagens.

| Ação (`audit.record`) | Quando |
|---|---|
| `prontuario.modelo_criado` | POST modelo |
| `prontuario.modelo_alterado` | PATCH, só se algum campo mudou (`details.campos`) |
| `prontuario.rascunho_criado` / `rascunho_alterado` / `rascunho_descartado` | ciclo do rascunho |
| `prontuario.versao_publicada` | publicar (`details.substituiu` = número anterior) |
| `prontuario.anamnese_registrada` | POST resposta (`details.alertas` = quantidade) |
| `prontuario.anamneses_listadas` | listagem do paciente |
| `prontuario.alertas_lidos` | alertas do paciente |
| `prontuario.anamnese_lida` | detalhe da resposta |

Ler modelos e versões (sem dado de paciente) não é auditado.

## Decisões

| Decisão | Motivo |
|---|---|
| Perguntas em JSONB dentro da versão, sem tabela de perguntas | Versão publicada é um documento imutável; as respostas dependem exatamente dele |
| Imutabilidade garantida por gatilho + REVOKE, além do service | Registro clínico não pode ser alterado por bug de aplicação |
| Resposta nova em vez de edição | Preserva histórico; a mais recente é a atual |
| `version_id` obrigatório no POST de resposta | Evita gravar contra uma versão diferente da que o usuário viu |
| Alertas calculados e gravados na escrita | Cabeçalho do paciente sem reinterpretar o formulário, e fiel ao que foi perguntado na época |
| Recepção sem acesso | Anamnese é dado de saúde |

## Como estender

- **Novo tipo de pergunta**: adicionar em `anamnese.py:QuestionType`, tratar em `_normalize`, `check_question` e `compute_alerts`; os testes unitários estão em `tests/test_prontuario_unit.py`. Versões antigas não mudam, pois o tipo só vale para novos rascunhos.
- **Evolução clínica / atendimento**: novos models no mesmo módulo, com `TenantMixin`, migração com `enable_tenant_rls`, import em `app/models.py` e tabela no `TRUNCATE` de `clean_db`. Se for registro clínico, repetir o padrão append-only (REVOKE na migração).
- **Nova tabela com FK para paciente**: usar FK composta `(patient_id, clinic_id)` como em `anamnesis_responses`.

## Armadilhas

- Um erro do gatilho (`check_violation`) ou de unicidade vira 409 com mensagem genérica ("Conflito com dados existentes"), sem explicar a causa.
- `update_template` aceita `description: null` para limpar, mas `name` e `active` nulos dão 409; string vazia dá 422.
- Modelo desativado ainda pode ter rascunho criado, editado e publicado; só o **preenchimento** é bloqueado (`record_response`).
- Paciente inativo bloqueia preencher, mas não ler o histórico.
- `PUT` de rascunho substitui a lista inteira de perguntas; não há edição parcial.
- O `id` da pergunta deve ser mantido entre versões para a mesma pergunta; o sistema não correlaciona respostas entre versões, só guarda cada resposta com as perguntas da sua versão.
- A publicação não revalida as perguntas já salvas; a validação acontece só no schema da requisição.
- "Atual" depende de `created_at` (hora do início da transação no servidor); empate exato é desfeito pelo `id` (UUID aleatório).
- Cada resposta lida é auditada, então telas que listam muitos pacientes não devem chamar `/alertas` em lote sem considerar o volume do log.
