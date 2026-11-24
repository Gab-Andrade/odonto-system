---
modulo: prontuario
atualizado_em: 3afacea
---
# Prontuário

> Registro clínico do paciente: anamnese configurável (modelos versionados, respostas imutáveis, alertas) e atendimento com evolução clínica imutável, adendos e assinatura.

## Responsabilidades

O módulo tem duas partes independentes, no mesmo prefixo `/prontuario`:

- **Anamnese** (`service.py`, `router.py`, `anamnese.py`): modelos de formulário e suas versões (rascunho, publicada, substituída), respostas do paciente, cálculo de alertas.
- **Atendimento e evolução** (`atendimento_service.py`, `atendimento_router.py`, `evolucao.py`): abrir e fechar atendimento, registrar evolução, adendo e assinatura.
- Dentro, em ambas: auditoria de toda leitura e escrita de dado clínico.
- Fora: cadastro do paciente e consentimentos (`pacientes`); o módulo só usa `pacientes.service.get_patient` via `service.py:get_patient`, que converte o `NotFound` de pacientes no do próprio módulo. Agendamento fica em `agenda`; o prontuário só chama `agenda.service.get_entry` e `change_status` ao abrir atendimento a partir de um agendamento.
- Regras puras ficam em `anamnese.py` e `evolucao.py`, sem banco. Os services orquestram e os routers fazem commit e auditoria.
- `atendimento_service.py` reaproveita as exceções (`NotFound`, `RuleViolation`, `Forbidden`) e `get_patient` de `service.py`; `atendimento_router.py` reaproveita `READ` e `_http` de `router.py`. As duas partes compartilham essa infraestrutura de erros.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `anamnesis_templates` | sim | Modelo de formulário (nome único por clínica, flag `active`) |
| `anamnesis_template_versions` | sim | Versões do modelo; guarda as perguntas em JSONB |
| `anamnesis_responses` | sim | Resposta de um paciente a uma versão; guarda respostas e alertas congelados |
| `encounters` | sim | Atendimento: paciente, dentista, agendamento opcional, aberto/fechado |
| `clinical_notes` | sim | Evoluções e adendos, append-only |
| `clinical_note_signatures` | sim | Assinaturas das evoluções/adendos, append-only |
| `encounter_transfers` | sim | Transferências de atendimento aberto entre dentistas, append-only |

### Anamnese (migração `0009_prontuario_anamnese.py`)

- Máximo de **um rascunho e uma publicada por modelo**: dois índices únicos parciais em `template_id` (`uq_anamnesis_template_versions_one_draft` e `_one_published`).
- CHECK `(status = 'rascunho') = (published_at IS NULL)`.
- FKs compostas com `clinic_id` (`fk_..._same_clinic`, `fk_anamnesis_responses_version_same_template`) impedem referência entre clínicas e garantem que a versão da resposta pertence ao `template_id` informado.
- **Gatilho `anamnesis_version_guard`**: depois de sair de rascunho, a versão não muda `questions`, não volta a `rascunho` e não pode ser apagada; `number`, `template_id` e `clinic_id` nunca mudam. Só rascunho pode ser apagado. Vale também para o dono do schema.
- `anamnesis_responses` é **append-only**: a migração revoga UPDATE/DELETE/TRUNCATE do `odonto_app`. Não tem `updated_at`.
- Todas as FKs para versões e pacientes são `RESTRICT`.

### Atendimento e evolução (migração `0010_prontuario_atendimento.py`)

- O atendimento é entidade própria; `appointment_id` é opcional (cobre encaixe e urgência). Índice único parcial `uq_encounters_appointment`: **um atendimento por agendamento**.
- CHECK `(status = 'fechado') = (closed_at IS NOT NULL)` em `encounters`.
- FK composta `(encounter_id, patient_id, clinic_id)` em `clinical_notes`: o paciente da evolução é sempre o do atendimento. FK composta `(amends_id, encounter_id, clinic_id)`: o adendo fica no mesmo atendimento da evolução corrigida.
- CHECKs em `clinical_notes`: `(kind = 'adendo') = (amends_id IS NOT NULL)`, conteúdo não vazio após `btrim`, `content_hash` com 64 hex minúsculos.
- CHECK `icp_has_signature`: método diferente de `simples` exige `signature` e `certificate`.
- Três gatilhos `BEFORE`, todos com `ERRCODE = check_violation`:
  - `encounter_guard` (INSERT/UPDATE): nasce `aberto`; depois de `fechado` nada muda; paciente, clínica, `started_at` e `appointment_id` nunca mudam; `dentist_id` só muda com transferência (ver 0012); ao fechar, `closed_by` tem de ser o `dentist_id` do atendimento.
  - `clinical_note_guard` (INSERT): evolução só com atendimento `aberto` (lê com `FOR SHARE`, para esperar um fechamento concorrente) e `author_id` = dentista do atendimento; adendo só sobre nota do tipo `evolucao` e com o mesmo autor dela. **Não** exige atendimento aberto para o adendo.
  - `clinical_note_signature_guard` (INSERT): o `content_hash` da assinatura tem de ser igual ao da nota, e assinatura `simples` só pelo autor da nota.
- Permissões: `encounters` perde só DELETE/TRUNCATE do `odonto_app` (UPDATE é necessário para fechar); `clinical_notes` e `clinical_note_signatures` perdem UPDATE/DELETE/TRUNCATE. Todas as FKs de dado clínico são `RESTRICT`: nada se apaga (a justificativa na migração é guarda mínima de 20 anos).

### Transferência de atendimento (migração `0012_prontuario_transferencia.py`)

- Tabela `encounter_transfers`: append-only (REVOKE de UPDATE/DELETE/TRUNCATE do `odonto_app`), RLS, FK composta `(encounter_id, clinic_id)`, CHECKs `from_dentist_id <> to_dentist_id` e motivo não vazio. `transferred_by` é `SET NULL`; as demais FKs para usuários são `RESTRICT`.
- A 0012 **substitui** `encounter_guard`: `dentist_id` só muda se existir em `encounter_transfers` uma linha com o mesmo atendimento, `from` = dentista antigo, `to` = novo e `created_at = now()`. Como `now()` é o início da transação, o registro tem de estar na **mesma transação** do UPDATE; uma transferência antiga não autoriza outra troca. Por isso `transfer_encounter` faz `flush` do INSERT antes de alterar `dentist_id`.
- O downgrade restaura o gatilho da 0010 (dentista imutável).

## API

Prefixo `/prontuario`. Papéis na anamnese: LER = admin, gestor, dentista, asb; PREENCHER = admin, dentista, asb; GERIR = admin, gestor. Atendimento: escrita (CLINICIAN) = admin, dentista; leitura = LER. **Recepção não acessa nada** (é conteúdo clínico). Gestor e ASB leem, mas não escrevem evolução.

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
| POST | `/atendimentos` | admin, dentista | Abre atendimento para quem está logado, opcionalmente a partir de um agendamento |
| GET | `/atendimentos/{id}` | LER | Atendimento com evoluções, adendos, assinaturas e transferências |
| POST | `/atendimentos/{id}/fechar` | admin, dentista | Fecha (só o dentista do atendimento) |
| POST | `/atendimentos/{id}/transferir` | admin | Passa atendimento aberto a outro dentista/admin, com motivo (devolve o detalhe) |
| POST | `/atendimentos/{id}/evolucoes` | admin, dentista | Registra evolução (só o dentista do atendimento, aberto) |
| POST | `/evolucoes/{id}/adendos` | admin, dentista | Adendo a uma evolução (só o autor dela) |
| GET | `/pacientes/{id}/atendimentos` | LER | Atendimentos do paciente com contagem de notas (`limit` até 500) |
| GET | `/pacientes/{id}/evolucoes` | LER | Linha do tempo de evoluções e adendos (`limit` até 500) |

Não existe rota de edição nem de exclusão de evolução, adendo ou assinatura.

Erros: `ProntuarioError` vira 404 (`NotFound`), **403** (`Forbidden`, só no atendimento) ou **409** (`RuleViolation`) em `router.py:_http`. Validação de schema é 422. Um `IntegrityError` que escape das checagens (corrida por nome duplicado, segundo rascunho, segundo atendimento do mesmo agendamento) é convertido em **409 genérico** pelo handler global em `app/main.py`, não em 500. Os gatilhos usam `check_violation` (SQLSTATE 23514, classe 23 = `IntegrityError` no SQLAlchemy), então também viram esse 409 genérico.

## Regras de negócio e invariantes

### Anamnese

- Só o rascunho é editável ou descartável (`service.py:_ensure_draft`); o gatilho repete isso no banco.
- Publicar exige ao menos uma pergunta (`service.py:publish`). A publicada anterior vira `substituida` com um `flush` **antes** de promover a nova, porque o índice único parcial não tolera duas publicadas e o flush não garante a ordem dos UPDATEs.
- Número da versão = `max(number) + 1` do modelo (`service.py:create_draft`), contando as substituídas.
- Responder só é possível se: paciente ativo, modelo ativo, existe publicada e `version_id` enviado é a publicada atual (senão 409 pedindo recarregar) (`service.py:record_response`).
- Validação das respostas (`anamnese.py:validate_answers`): id desconhecido é erro; vazio (`None`, texto em branco, lista vazia) conta como não respondido e é descartado; obrigatória sem resposta é erro; múltipla é reordenada na ordem do formulário e sem repetição; número rejeita `bool`, NaN/infinito e `abs > 1e9`; data só `AAAA-MM-DD` real.
- Alertas (`anamnese.py:compute_alerts`) só vêm de perguntas com `alert`. Em múltipla com `alert_options`, o alerta guarda apenas as opções que disparam.
- Os alertas são **gravados na resposta** com o texto da pergunta no momento do preenchimento (snapshot).
- "Resposta atual" = a mais recente por modelo (`created_at desc, id desc`) via `DISTINCT ON (template_id)` (`service.py:_current_ids`). Alertas do paciente consideram só as respostas atuais.
- Coerência de pergunta (`anamnese.py:check_question`, `check_questions`): escolhas têm 2 a 50 opções sem repetição (ignorando caixa); `options` só em escolha; `alert_options` exige `alert` e estar contido em `options`; ids únicos; máximo 150 perguntas. O pydantic chama essas funções em `schemas.py` (`Question._coherent`, `_checked`).

### Atendimento e evolução

- **Autoria**: o dentista do atendimento é sempre quem o abriu (`dentist_id = user.user_id`, `atendimento_service.py:open_encounter`); não há parâmetro para abrir em nome de outro. Só ele registra evolução e fecha (`_ensure_own_open`, 403 caso contrário). O gatilho repete a regra no banco.
- **Abrir a partir de agendamento de outro dentista é permitido de propósito** (substituição de profissional). `open_encounter` não compara `appointment.dentist_id` com o usuário; o atendimento fica com quem abriu e o agendamento não é reatribuído.
- Abrir exige paciente ativo. `started_at` opcional (padrão: agora) segue a mesma janela de `performed_at`.
- Com agendamento: precisa ser `consulta` (não bloqueio) e do mesmo paciente; não pode já ter atendimento; se não estiver `atendido`, é movido para `atendido` por `agenda.service.change_status`, que valida a transição (cancelado e falta são finais; `atendido` só depois do horário de início). Se a agenda recusar, vira 409 com a mensagem dela e nada é gravado (rollback). Agendamento já `atendido` é vinculado sem nova transição.
- Janela do ato clínico (`evolucao.py:check_performed_at`): exige fuso, no máximo 5 min no futuro (`CLOCK_TOLERANCE`) e no máximo 7 dias no passado. Vale para `started_at` e `performed_at` informados. `created_at` é a data real do registro.
- **Transferência** (`atendimento_service.py:transfer_encounter`, só admin): exige atendimento `aberto`, destino diferente do atual e com papel ativo `dentista` ou `admin` na clínica (`active_role`; vale o dono-dentista). Evoluções já registradas continuam com o autor original; o novo dentista passa a registrar e fechar. Pode haver várias transferências em sequência; `list_transfers` ordena por `created_at, id`.
- Fechar não exige evolução (`close_encounter`). Atendimento fechado só aceita adendo.
- **Adendo** (`add_addendum`): só sobre `evolucao` (não sobre adendo), só pelo autor dela, a qualquer tempo, com `performed_at = agora`. Não há como editar a evolução original.
- **Hash e assinatura**: `_new_note` calcula `content_hash` (SHA-256 de JSON canônico com id da nota, atendimento, paciente, autor, tipo, `amends_id`, `performed_at` em UTC e conteúdo; `evolucao.py:content_hash`) e cria na mesma transação a assinatura `simples` do autor com esse hash. Toda nota nasce assinada. O hash é recalculável das colunas gravadas.
- Conteúdo: não vazio após strip e até 20.000 caracteres (`evolucao.MAX_CONTENT`, aplicado em `schemas.NoteContent`).
- Linha do tempo do paciente ordena por `performed_at desc, created_at desc, id`; a do atendimento, por `created_at, id`.

### Frontend: editor de modelos de anamnese

Tela Configurações (`/configuracoes`, só admin/gestor, o mesmo GERIR do backend) com `frontend/src/pages/config/ModelosAnamnese.tsx`. Não há rota nova; a tela só consome as rotas de `/anamnese/modelos` e `/anamnese/versoes`.

- Fluxo: lista de modelos, novo modelo (POST com `questions: []`), detalhe. O detalhe edita o rascunho se existir; sem rascunho, mostra a publicada em prévia somente leitura e oferece "Criar rascunho" (POST `/rascunho`).
- Botões do editor (`Editor`): Salvar rascunho = PUT; Publicar = POST `/publicar`; Descartar = DELETE; Desativar/Reativar o modelo = PATCH `active`. Publicar chama o PUT antes se houver alteração local, em duas requisições separadas.
- A prévia ("Ver como fica", `Previa`) reutiliza `CampoPergunta` e o tipo `Pergunta`, exportados por `frontend/src/pages/prontuario/Anamnese.tsx`. Mudar esse componente muda a prévia e o preenchimento ao mesmo tempo.
- `paraApi` converte o estado de edição para o formato da API: mantém o `id` de perguntas existentes e gera `id` por slug do texto (até 34 caracteres, sufixo `_2`, `_3` em colisão) só para perguntas novas. Opções vêm de texto, uma por linha, sem repetição; `alert_options` é filtrado para opções ainda existentes.

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`. Registro de outra clínica aparece como 404 pelo RLS (sem filtro manual de `clinic_id`); isso inclui atendimento, evolução e o agendamento informado ao abrir.
- Toda leitura de dado de paciente é auditada, inclusive GET. Os `details` nunca carregam respostas de anamnese nem texto clínico, só ids e contagens.

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
| `prontuario.atendimento_aberto` | POST atendimento (`details.agendamento` se houver) |
| `prontuario.atendimento_lido` | GET atendimento |
| `prontuario.atendimento_fechado` | fechar |
| `prontuario.atendimento_transferido` | transferir (`details`: paciente, `de`, `para`; o motivo não vai para o log) |
| `prontuario.evolucao_registrada` | POST evolução (`details.data_informada`: se o cliente mandou `performed_at`) |
| `prontuario.adendo_registrado` | POST adendo (`details.evolucao`) |
| `prontuario.atendimentos_listados` | listagem do paciente |
| `prontuario.evolucoes_lidas` | linha do tempo do paciente |

Ler modelos e versões de anamnese (sem dado de paciente) não é auditado. A mudança de status do agendamento ao abrir atendimento gera evento próprio da agenda (`agenda.service._event`), não uma ação de auditoria separada.

## Decisões

| Decisão | Motivo |
|---|---|
| Perguntas em JSONB dentro da versão, sem tabela de perguntas | Versão publicada é um documento imutável; as respostas dependem exatamente dele |
| Imutabilidade por gatilho + REVOKE, além do service | Registro clínico não pode ser alterado por bug de aplicação, nem por quem tem o role do schema (no caso dos gatilhos) |
| Resposta nova em vez de edição | Preserva histórico; a mais recente é a atual |
| `version_id` obrigatório no POST de resposta | Evita gravar contra uma versão diferente da que o usuário viu |
| Alertas calculados e gravados na escrita | Cabeçalho do paciente sem reinterpretar o formulário, e fiel ao que foi perguntado na época |
| Recepção sem acesso | Anamnese e evolução são dado de saúde |
| Atendimento como entidade própria, agendamento opcional | Encaixe e urgência não têm agendamento; a agenda não é o prontuário |
| Correção só por adendo, sem editar nem apagar evolução | Guarda legal do prontuário; o histórico mostra o que foi dito e o que foi corrigido |
| Evolução com `performed_at` (até 7 dias) separado de `created_at` | Permite registrar depois sem falsificar a data real do registro |
| Hash do conteúdo + assinatura simples automática, com campos prontos para ICP-Brasil | Prova de integridade desde já; certificado digital entra depois sem migração de tabela |
| Regras de autoria duplicadas no gatilho | O banco é a última barreira se um caminho novo esquecer o service |
| Atendimento aberto a partir do agendamento de outro dentista é permitido | Substituição de profissional; quem atende é quem responde pelo registro |
| Troca de dentista só por transferência registrada, validada no gatilho | Resolve atendimento órfão (dentista desativado) sem abrir mão da regra de autoria; a troca deixa rastro imutável e o banco recusa mudança sem ele |

## Como estender

- **Novo tipo de pergunta**: adicionar em `anamnese.py:QuestionType`, tratar em `_normalize`, `check_question` e `compute_alerts`; testes em `tests/test_prontuario_unit.py`. Versões antigas não mudam.
- **Assinatura ICP-Brasil**: inserir `ClinicalNoteSignature` com `method = icp_brasil`, `signature` e `certificate` (o CHECK os exige) e o mesmo `content_hash` da nota (o gatilho confere). O gatilho só restringe o signatário no método `simples`. Hoje nenhuma rota cria assinatura além da automática em `_new_note`.
- **Novo tipo de registro clínico**: model com `TenantMixin`, FK composta com `clinic_id` e com paciente, migração com `enable_tenant_rls`, REVOKE de UPDATE/DELETE/TRUNCATE e, se tiver regra de autoria, gatilho `check_violation`. Importar em `app/models.py` e incluir no `TRUNCATE` de `clean_db`.
- **Nova regra de janela de data**: alterar `evolucao.py:MAX_BACKDATE`/`CLOCK_TOLERANCE`; os testes unitários estão em `tests/test_atendimento_unit.py`.
- **Nova tabela com FK para paciente**: FK composta `(patient_id, clinic_id)`, como em `anamnesis_responses` e `encounters`.

## Armadilhas

- Erros de gatilho (`check_violation`) e de unicidade viram 409 com mensagem genérica ("Conflito com dados existentes"), sem explicar a causa. O service checa as mesmas regras antes, então o 409 genérico só aparece em corrida ou em caminho que fure o service.
- `update_template` aceita `description: null` para limpar, mas `name` e `active` nulos dão 409; string vazia dá 422.
- Modelo desativado ainda pode ter rascunho criado, editado e publicado; só o **preenchimento** é bloqueado.
- Paciente inativo bloqueia preencher anamnese e abrir atendimento, mas não ler histórico. Evolução e adendo em atendimento já aberto não revalidam paciente ativo.
- `PUT` de rascunho substitui a lista inteira de perguntas.
- O `id` da pergunta deve ser mantido entre versões para a mesma pergunta; o sistema não correlaciona respostas entre versões.
- A publicação não revalida as perguntas já salvas; a validação acontece só no schema.
- "Atual" depende de `created_at` (hora do início da transação); empate exato é desfeito pelo `id` (UUID aleatório).
- Cada leitura é auditada; telas que listam muitos pacientes não devem chamar `/alertas`, `/atendimentos` ou `/evolucoes` em lote sem considerar o volume do log.
- Um atendimento aberto e esquecido não tem prazo: só o dentista atual fecha (nem outro admin), e o gatilho exige `closed_by` = dentista. Se ele for desativado, o admin resolve transferindo o atendimento (`/transferir`); não há fechamento por terceiros.
- Após transferir, o dentista anterior perde a escrita no atendimento, mas o adendo a uma evolução dele continua só por ele (regra do autor); se ele estiver desativado, essa evolução não poderá mais receber adendo.
- `transfer_encounter` não trava a linha do atendimento: um fechamento concorrente faz o UPDATE falhar no gatilho e o `IntegrityError` vira o 409 genérico, não a mensagem "Atendimento fechado não é transferido".
- O papel (dentista/admin) é conferido no router por `require_roles`; o service só confere identidade (`user_id`). Chamar o service de outro lugar sem essa dependência não verifica papel.
- `add_addendum` usa a data atual como `performed_at` e não passa pela janela de 7 dias; o adendo pode vir meses depois da evolução.
- A assinatura `simples` é só "usuário autenticado": o hash garante integridade do que está no banco, não identidade forte nem carimbo de tempo confiável.
- A paginação de `list_encounters` ordena por `started_at desc`, e a de `patient_notes` por `performed_at desc`; com `offset` alto e inserções concorrentes, itens podem repetir ou pular entre páginas.
- Editor de modelos (frontend): "Descartar" só aparece quando já existe versão publicada (`temPublicada`); um modelo novo, com só o rascunho nº 1, não pode ser descartado pela tela (a API permitiria). O slug do `id` de pergunta nova nasce do texto no momento do primeiro salvamento e depois não muda, mesmo que o texto seja editado.
- Editor de modelos (frontend): a validação local só exige texto e pelo menos 2 opções nas perguntas de lista; os limites de 50 opções e 150 perguntas só são checados pelo backend (422 exibido como aviso). Se o PUT do "Publicar" passa e o POST falha, o rascunho fica salvo sem publicar.
- A janela de 7 dias vale também para `started_at`: não é possível abrir, por esta API, um atendimento mais antigo que isso, mesmo a partir de um agendamento antigo ainda não marcado como atendido.
