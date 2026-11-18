---
modulo: odontograma
atualizado_em: 53c3930
---
# Odontograma

> Legenda de marcações por clínica, histórico append-only de marcações e da arcada de cada paciente, e a visualização 2D/3D (biblioteca de dentes gerada por código) construída sobre eles.

## Responsabilidades

- Legenda da clínica (`tooth_statuses`): itens com cor, tipo (patologia, planejado, realizado), escopo (dente inteiro ou face) e efeito no 3D (colorir ou ocultar o dente).
- Marcar e remover itens em dentes/faces de um paciente, em lotes, opcionalmente vinculados a um atendimento aberto.
- Consultar o odontograma atual ou "como estava em" um momento, o histórico de eventos e a comparação entre dois momentos.
- Arcada do paciente (`dental_arch_configs`): quais dentes o modelo do paciente tem (decídua, mista, permanente, com 0 a 4 sisos). Sem registro, é sugerida pela idade.
- Visualização pronta para desenhar (`/visualizacao`), a mesma para 2D e 3D, e biblioteca 3D genérica (`.glb` gerado em memória).
- **Fora do módulo:** cadastro do paciente (`pacientes`), atendimento e evolução (`prontuario`; aqui só se referencia `encounters`), plano de tratamento e preço (`tratamento`). Item "planejado" é só marcação visual; não gera orçamento. O `tratamento` é quem **consome** este módulo (`odontograma.service.current_marks` e `record_events` ao realizar item do plano).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `tooth_statuses` | sim | Legenda da clínica |
| `odontogram_events` | sim | Eventos marcar/remover, append-only |
| `dental_arch_configs` | sim | Composição da arcada do paciente, append-only; a mais recente é a vigente |

- `odontogram_events` não tem estado: não existe "marcação atual" gravada. O estado é sempre derivado dos eventos (`regras.py:rebuild`).
- Append-only: a migração 0011 revoga UPDATE/DELETE/TRUNCATE do `odonto_app` em `odontogram_events`; a 0017 faz o mesmo em `dental_arch_configs`. Em `tooth_statuses` revoga só DELETE/TRUNCATE (itens são desativados, não apagados).
- FKs compostas com `clinic_id` garantem que paciente, item da legenda e atendimento sejam da mesma clínica; o atendimento ainda precisa ser do mesmo paciente (`fk_odontogram_events_encounter_same_patient`).
- CHECKs: dente FDI (11-48 com posição 1-8; 51-85 com posição 1-5), face em M/D/O/V/L, cor `#RRGGBB` maiúscula, código `[a-z0-9_]{1,40}`. Em `dental_arch_configs`, só numeração FDI e tamanho (1 a 52); repetição, vaga ocupada por dois dentes e coerência com a dentição ficam em `arcada.py:validate` (CHECK não tem subconsulta). Em `tooth_statuses` (0018): `display_3d` válido e `display_3d_whole_tooth` (`ocultar` só com escopo `dente`).
- Gatilhos (migração 0011, `check_violation`):
  - `odontogram_event_guard` (BEFORE INSERT): a presença de face tem de bater com o escopo do item; só `marcar` item ativo. Usa `FOR SHARE` no item para serializar com mudança concorrente de escopo.
  - `tooth_status_guard` (BEFORE UPDATE): `kind`, `scope`, `code` e `clinic_id` não mudam se já existe evento com o item. `display_3d` e `active` podem mudar mesmo com o item em uso.
- `created_at` de eventos e de arcadas usa `clock_timestamp()` (model e migração) e não `now()`. A ordem real define o estado (eventos) e qual arcada é a vigente; `now()` (início da transação) ficaria anterior à espera do lock e poderia inverter a ordem.

## API

Prefixo `/odontograma`.

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/legenda` | admin, gestor, dentista, asb | Lista a legenda (`incluir_inativos`); cria a legenda padrão na primeira leitura |
| POST | `/legenda` | admin, gestor | Cria item |
| PATCH | `/legenda/{id}` | admin, gestor; dentista só o campo `color` | Edita nome, cor, ordem, efeito 3D, ativo e, se nunca usado, tipo/escopo |
| GET | `/pacientes/{id}` | admin, gestor, dentista, asb | Odontograma atual ou em `?em=<datetime com fuso>`; só dentes com marcação |
| POST | `/pacientes/{id}/eventos` | admin, dentista, asb | Grava lote de 1 a 200 eventos (201) |
| GET | `/pacientes/{id}/historico` | admin, gestor, dentista, asb | Eventos do mais novo ao mais antigo (`limit` até 500, `offset`) |
| GET | `/pacientes/{id}/arcada` | admin, gestor, dentista, asb | Arcada vigente (registrada ou sugerida pela idade), opcional `?em=` |
| POST | `/pacientes/{id}/arcada` | admin, dentista, asb | Registra nova arcada (201) |
| GET | `/pacientes/{id}/visualizacao` | admin, gestor, dentista, asb | Arcada + marcações resolvidas (cor por face, dente oculto, posição 3D) |
| GET | `/pacientes/{id}/comparacao?de=&ate=` | admin, gestor, dentista, asb | Marcações que entraram e saíram entre dois momentos |
| GET | `/3d/biblioteca` | admin, gestor, dentista, asb | Manifesto da biblioteca 3D |
| GET | `/3d/dentes/{fdi}.glb` | idem | Dente isolado |
| GET | `/3d/arcada.glb?dentes=11,12,...` | idem | Arcada montada; sem `dentes`, permanente com 32 dentes |

Recepção não acessa nada. Gestor lê e edita a legenda, mas não marca. O dentista só recolore itens: o `PATCH` aceita o papel (`router.py:RECOLOR`), mas qualquer campo além de `color` no corpo dá 403 (`router.py:update_status`). `NotFound` vira 404; `RuleViolation` vira 409 (`router.py:_http`). `comparacao` com `de > ate` devolve 422. Os `.glb` respondem 304 com `If-None-Match` e 404 para dente fora do FDI; `dentes` inválido dá 422 (`biblioteca_router.py:parse_teeth`).

## Regras de negócio e invariantes

- Lote é atômico e validado contra o estado atual: sem repetir (dente, face, item) no lote, não marcar o já marcado, não remover o inexistente (`regras.py:check_batch`).
- Dente/face/item formam a chave da marcação; itens diferentes coexistem no mesmo dente/face (`regras.py:rebuild`).
- Escopo do item x face é validado no serviço (mensagem amigável) e de novo por gatilho (`service.py:record_events`).
- Item desativado não pode ser marcado, mas pode ser removido e continua aparecendo em marcações antigas (as rotas usam `list_statuses` com inativos).
- Paciente inativo não recebe marcações nem arcada (`service.py:record_events`, `record_arch`).
- Atendimento informado deve existir, ser do paciente e estar ABERTO.
- Escritas do mesmo paciente são serializadas por `SELECT ... FOR UPDATE` na linha do paciente antes de ler o estado e inserir (`service.py:record_events`). Sem isso, dois lotes concorrentes passariam em `check_batch` contra o mesmo estado.
- Faces: gravadas só como M, D, O, V, L. Na entrada `I` vira `O` e `P` vira `L`; na saída o rótulo clínico é recalculado por dente (`O`→`I` em anteriores, posição ≤ 3; `L`→`P` na arcada superior, quadrantes 1, 2, 5, 6) (`regras.py:normalize_face`, `face_label`).
- `em` usa `created_at <= em`; sem `em`, usa o momento atual do servidor. Vale para eventos e para a arcada (`service.py:effective_arch`).
- Arcada: cada vaga (quadrante permanente 1-4 + posição) tem um dente só; o decíduo 5x-8x ocupa a vaga do sucessor permanente. Posições 6-8 só existem na permanente; sisos só na permanente (`arcada.py:validate`, `slot`). `POST /arcada` aceita `teeth` explícito **ou** preset (`third_molars`; omitido na permanente = 4 sisos), nunca os dois.
- Arcada sugerida por idade quando não há registro: < 6 decídua, 6-11 mista típica, 12-17 permanente sem sisos, adulto ou sem nascimento permanente com 32 (`arcada.py:default_for`). A data de referência usa `clinic_timezone`.
- Arcada e marcações são independentes: marcar não consulta a arcada, e mudar a arcada não apaga marcações. Dente marcado fora da arcada aparece em `/visualizacao` com `in_arch=false` (`visualizacao.py:build`).
- Cor de uma face: item mais importante da face; sem ele, o mais importante do dente inteiro; sem nenhum, `null`. Importância: patologia > planejado > realizado, desempate por `sort_order` e `code` (`visualizacao.py:priority`). Dente é `hidden` se tem marcação de dente inteiro com `display_3d = ocultar`.
- `display_3d = ocultar` só em item de dente inteiro: validado em `service.py:_check_display` e pelo CHECK.
- Tipo/escopo mudam só enquanto o item não tem evento (`service.py:update_status`, gatilho).

## Tenancy e auditoria

- Rotas de paciente e de legenda usam `get_tenant_db`. A legenda é por clínica, então é filtrada só pelo RLS. Pacientes vêm de `pacientes.service.get_patient` (herda RLS e 404).
- Rotas `/odontograma/3d/*` usam só `require_roles(*READ)` (sessão global, sem tenant): o conteúdo é genérico, sem dado de clínica ou paciente. Não são auditadas.
- Ações auditadas:
  - `odontograma.legenda_criada`, `odontograma.legenda_alterada` (`details.campos`; só se algo mudou)
  - `odontograma.lido` (odontograma; `details.em` se informado; `/visualizacao` grava a mesma ação com `details.visualizacao = true`)
  - `odontograma.marcado` (`details.eventos`, `details.atendimento`)
  - `odontograma.historico_lido`
  - `odontograma.arcada_lida`, `odontograma.arcada_registrada` (`details.denticao`, `details.dentes`)
  - `odontograma.comparado` (`details.de`, `details.ate`)
- A leitura da legenda não é auditada (sem dado de paciente).

## Decisões

| Decisão | Motivo |
|---|---|
| Event sourcing simples em vez de tabela de estado | Histórico clínico imutável e odontograma retroativo sem trabalho extra |
| Arcada também append-only, vigente = mais recente | Mudança de dentição é fato clínico datado; permite `?em=` retroativo |
| Arcada padrão calculada, não gravada | Evita gravar algo que o dentista não afirmou; só vira registro quando ele confirma |
| Legenda padrão criada na primeira leitura/uso, com `ON CONFLICT DO NOTHING` | Não exige seed por clínica; seguro sob concorrência |
| "Sem itens" significa "nunca inicializada" | Itens nunca são apagados, só desativados |
| Tipo/escopo imutáveis após uso, por serviço e por gatilho | Mudar escopo reinterpretaria eventos antigos |
| Face O e L guardam também incisal e palatina | Evita duplicar faces; o rótulo depende do dente |
| Lock na linha do paciente | Serializar validação e inserção do lote |
| `/visualizacao` única para 2D e 3D, com decisão de cor no backend | As duas visões não divergem; o frontend só pinta |
| Modelos 3D gerados por código (`malha3d.py`, `glb.py`), sem binários no repositório e sem dependências | Determinístico (mesmos bytes, logo ETag estável); trocar por modelos do Blender exige manter nomes de nós e orientação |
| Nós nomeados `dente_<fdi>`, `<fdi>_<face>`, `<fdi>_raiz` | Contrato entre `/visualizacao` (`node`) e o `.glb`; o toque numa malha devolve dente e face |

## Como estender

- Novo item padrão: editar `regras.py:DEFAULT_LEGEND` (e `HIDDEN_IN_3D` se deve ocultar). Só afeta clínicas ainda sem legenda; as existentes precisam criar via API.
- Nova face ou tipo: atualizar enum no model, schema, CHECK numa nova migração (inclusive nos gatilhos, se afetar a regra) e `regras.py`. Nova face também exige nós e materiais em `malha3d.py`.
- Trocar a geometria dos dentes: mude `malha3d.py` e incremente `VERSION` (o frontend usa `library_version`). Para modelos externos, preserve nomes de nós, orientação (convenções em `malha3d.CONVENTIONS`) e `extras`.
- Nova regra de composição da arcada: `arcada.py:validate`/`preset`; só a numeração/tamanho está no CHECK.
- Novo model: importar em `app/models.py`, RLS na migração e `TRUNCATE` em `tests/conftest.py`.
- Vincular a plano de tratamento: já feito em `tratamento` (referencia o item da legenda e chama `record_events`); novos consumidores devem usar `service.py`, não escrever eventos direto.

## Armadilhas

- O GET da legenda escreve (cria a legenda padrão) e faz commit, apesar de ser leitura. Papéis de leitura (inclusive ASB) disparam essa escrita. O mesmo vale para `create_status` e `record_events`, que também chamam `ensure_default_legend`. `/visualizacao`, `/comparacao` e `GET /odontograma/pacientes/{id}` **não** inicializam a legenda (sem eventos não precisam dela).
- `ensure_default_legend` só checa se existe algum item.
- `IntegrityError` não tratado (incluindo `check_violation` dos gatilhos e corrida no código da legenda) vira 409 pelo handler global de `app/main.py`, não 500. A checagem de código duplicado em `create_status` é só mensagem amigável.
- O 403 do dentista por campo proibido é checado **antes** de `get_status`: id inexistente com campo proibido dá 403, não 404. A auditoria (`legenda_alterada`) é a mesma dos outros papéis.
- `PATCH` com campo `null` explícito retorna 409 ("não pode ficar vazio"); campo omitido é ignorado. `code` não é editável.
- Remover uma marcação grava novo evento `remover`; não há como corrigir ou apagar um evento errado.
- `GET /pacientes/{id}` não pagina e devolve só dentes com marcação; já `/visualizacao` devolve todos os dentes da arcada mais os marcados fora dela.
- Eventos de um mesmo lote têm `created_at` distintos (`clock_timestamp()`), mas o desempate de ordenação é por `id` (UUID aleatório); não confie na ordem dentro de um lote além do timestamp.
- `em`, `de` e `ate` exigem data com fuso (`AwareDatetime`).
- A migração 0018 desliga e religa `FORCE ROW LEVEL SECURITY` em `tooth_statuses` para atualizar "ausente" de todas as clínicas; ela também muda um item próprio da clínica que tenha o mesmo código, tipo e escopo. Se a migração falhar no meio, confira que o FORCE voltou (roda na transação, então o rollback restaura).
- `record_arch` não trava a linha do paciente (diferente de `record_events`): duas arcadas simultâneas são aceitas e vale a de `created_at` maior.
- `arch_model_url` em `/visualizacao` é um caminho relativo sem prefixo de versão; o `.glb` exige login (Bearer), então o frontend não pode usar uma tag de carregamento direto sem o header.
- Cache dos `.glb`: `private, no-cache` com ETag por hash do conteúdo: o navegador guarda o arquivo, mas revalida a cada uso (304 quando não mudou), então uma geometria nova chega na hora. Os caches em memória (`lru_cache` em `malha3d.py`) são por processo.
- `parse_teeth` deduz a dentição dos dentes do query string e aplica `arcada.validate`; `dentes` vazio (`?dentes=`) cai em lista vazia e dá 422 ("ao menos um dente"), enquanto parâmetro ausente dá o padrão permanente.
- A marcação "ausente" da legenda e a arcada são conceitos diferentes (dente perdido x dente que não existe na dentição); não use um para o outro.
