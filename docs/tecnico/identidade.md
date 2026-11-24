---
modulo: identidade
atualizado_em: f99e454
---
# Identidade

> Quem é o usuário, em qual clínica ele está atuando e com qual papel, e como a equipe da clínica é cadastrada, convidada e mantida.

## Responsabilidades

- Cadastro de clínicas, usuários e vínculos usuário↔clínica com papel.
- Login por e-mail e senha, com emissão de JWT de acesso.
- Cadastro da equipe **só pelo admin da clínica** (`/equipe/*`): membro novo com senha provisória, convite com código para e-mail que já tem cadastro, mudança de papel, ativação/desativação, redefinição de senha e pedidos para rebaixar/desativar outro admin.
- Primeiro acesso (`/auth/primeiro-acesso`), troca da própria senha (`/auth/senha`) e aceite de convite (`/auth/vinculos/aceitar`).
- Dependências FastAPI usadas por **todos** os outros módulos: `get_current_user`, `require_roles`, `get_tenant_db` (`deps.py`).
- Comando administrativo `python -m app.cli criar-clinica` (`app/cli.py`).

Fora daqui: hash e JWT ficam em `app/core/security.py`, a sessão de tenant em `app/core/db.py`, e o registro de auditoria em `app/core/audit.py`.

Organização: `router.py` (rotas `/auth`, que rodam em sessão global antes de haver clínica), `equipe_router.py` (`/equipe`, só admin, sessão de tenant), `service.py` (login, papel, equipe de leitura) e `equipe_service.py` (regras do cadastro de equipe; não faz commit).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `clinics` | não (global) | clínica; `slug` único; `active` desliga a clínica inteira |
| `users` | não (global) | pessoa; um usuário pode atuar em várias clínicas |
| `clinic_memberships` | não (global) | vínculo usuário↔clínica com `role`; `active` revoga só aquele vínculo |
| `membership_invites` | não (global) | convite pendente de um e-mail já cadastrado, com hash do código de uso único e validade |
| `admin_change_requests` | sim | pedido para rebaixar ou desativar outro admin; só vale quando o admin alvo aceita |

- `clinics`, `users`, `clinic_memberships` e `membership_invites` são globais de propósito: login e aceite de convite precisam lê-las antes de saber a clínica. O isolamento fica na camada de serviço, e **toda** consulta nelas em `equipe_service.py` filtra `clinic_id` ou o próprio usuário explicitamente.
- `users.email` tem CHECK `email = lower(email)`. Normalize com `service.normalize_email` antes de gravar ou consultar.
- `users.must_change_password` marca senha aleatória (cadastro ou redefinição). `users.password_changed_at` invalida tokens emitidos antes dela.
- `clinic_memberships` e `membership_invites`: unicidade `(user_id, clinic_id)`. `role` é `String(20)` com CHECK na migração, e o model usa `Enum(native_enum=False, create_constraint=False)`.
- `membership_invites`: o convite é **apagado** ao ser aceito (vira `ClinicMembership`) ou cancelado; não há status. Vencido continua na tabela até renovar ou cancelar.
- `admin_change_requests` (migração `0026`): CHECKs garantem `rebaixar` ⇔ `new_role` preenchido (e nunca admin), `requested_by <> target_user_id`, `aprovada` só com `decided_by = target_user_id` e `decided_at` nulo ⇔ `pendente`. Índice único parcial `(clinic_id, target_user_id) WHERE status='pendente'`: no máximo um pedido pendente por alvo. FKs de usuário são `RESTRICT`.
- `ondelete`: vínculos e convites caem em cascata com usuário ou clínica. Tabelas de tenant usam `RESTRICT` para `clinics`, então na prática clínica não se apaga, se desativa.

## API

Detalhes de corpo e resposta no OpenAPI (`/docs`).

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| POST | `/auth/login` | público | autentica e devolve `access_token` + clínica + papel |
| POST | `/auth/primeiro-acesso` | público | troca a senha provisória pela da pessoa e já entra (mesma resposta do login) |
| POST | `/auth/vinculos/aceitar` | público | aceita convite com e-mail, senha atual e código; responde 204 |
| GET | `/auth/me` | qualquer autenticado | dados do usuário e da clínica do token |
| GET | `/auth/equipe` | qualquer autenticado | membros ativos da clínica do token (nome, papel, CRO, sem e-mail), para escolher dentista na agenda, no plano etc. |
| POST | `/auth/senha` | qualquer autenticado | troca a própria senha e devolve token novo |
| GET | `/equipe/membros` | admin | equipe com e-mail e situação (`incluir_inativos`) |
| POST | `/equipe/membros` | admin | e-mail novo: cria usuário com senha provisória; e-mail já cadastrado: cria convite com código |
| PATCH | `/equipe/membros/{user_id}` | admin | papel, ativo e (nome, CRO quando permitido) |
| POST | `/equipe/membros/{user_id}/redefinir-senha` | admin | nova senha provisória |
| GET | `/equipe/convites` | admin | convites pendentes (inclui vencidos) |
| POST | `/equipe/convites/{invite_id}/novo-codigo` | admin | código novo e +7 dias |
| DELETE | `/equipe/convites/{invite_id}` | admin | cancela o convite |
| GET | `/equipe/solicitacoes` | admin | pedidos (só pendentes por padrão; sem filtro, os 100 mais recentes) |
| POST | `/equipe/solicitacoes` | admin | pede rebaixar/desativar outro admin |
| POST | `/equipe/solicitacoes/{id}/aceitar` | admin | só o admin alvo; aplica a mudança |
| POST | `/equipe/solicitacoes/{id}/recusar` | admin | só o admin alvo |
| POST | `/equipe/solicitacoes/{id}/cancelar` | admin | só quem pediu |

Códigos fora do padrão:

- `POST /auth/login` e `/auth/primeiro-acesso` respondem **409** com `ClinicSelectionResponse` quando há mais de um vínculo ativo e não veio `clinic_id`. No primeiro acesso a senha **já foi trocada**; o cliente segue com login usando a senha nova e a clínica escolhida.
- `POST /auth/login` e `/auth/vinculos/aceitar` respondem **403** ("Defina uma senha sua...") quando a senha é provisória.
- Credencial errada, usuário inativo, sem vínculo ativo ou `clinic_id` inválido: tudo vira o mesmo **401** genérico. `/auth/primeiro-acesso` com senha correta mas **sem** `must_change_password` também dá 401 (`equipe_service.first_access`).
- Erros de regra em `/equipe/*` e `/auth/primeiro-acesso`/`/auth/senha` são **409** com `detail` em texto; `NotFound` é 404 e `Forbidden` é 403 (`equipe_router.py:_http`). Senha atual errada em `/auth/senha` é 403.
- Código de convite inválido ou vencido: **400** (`InvalidCode`).
- Respostas que trazem senha ou código (`POST /equipe/membros`, `redefinir-senha`, `novo-codigo`, `/auth/senha`) enviam `Cache-Control: no-store`. A senha/código aparece só nessa resposta.
- `GET /auth/equipe` (`service.py:team`) filtra `clinic_id` explicitamente (tabelas globais) e só traz vínculo ativo **e** usuário ativo. Qualquer papel lê. Teste: `test_auth_integration.py:test_team_lists_only_active_members_of_own_clinic`.

## Regras de negócio e invariantes

- O papel **não** vem do token. `deps.py:get_current_user` chama `service.session_role` a cada request. Usuário, vínculo ou clínica inativos geram 401 na hora.
- `session_role` também derruba o token quando `must_change_password` está ligado ou quando `iat_ms` do token é anterior a `password_changed_at` (comparação em milissegundos; `core/security.py:create_access_token` emite `iat_ms` porque `iat` só tem resolução de segundos). Token antigo sem `iat_ms` cai no `iat * 1000`.
- O JWT exige `exp`, `iat`, `sub`, `cid` e `typ == "access"` (`core/security.py:decode_access_token`).
- Senha provisória só serve para definir a própria: login e aceite de convite recusam (403) e o token existente deixa de valer (`service.authenticate`, `session_role`). Gerada por `equipe_service.generate_password` (12 caracteres, ~59 bits); código de convite por `generate_code` (10 caracteres, ~49 bits, guardado só como hash argon2).
- Toda definição de senha passa por `equipe_service._set_password`, que atualiza `password_changed_at` e derruba as sessões abertas.
- A clínica nunca fica sem admin ativo. `_lock_active_admins` trava os vínculos de admin (ordem por id) **antes** de travar o membro alvo em `update_member`, `reset_password`, `create_request` e `accept_request`; `_check_admin_remains` conta depois da trava. Mantenha essa ordem em qualquer função nova que mexa em admin, para evitar corrida e deadlock.
- O admin se rebaixa/desativa direto (se sobrar outro). Rebaixar ou desativar **outro** admin só por pedido aceito pelo próprio alvo, dentro de 7 dias (`REQUEST_TTL`). O aceite revalida que quem pediu ainda é admin ativo e que o alvo ainda é admin e não é o último.
- Pedido expirado é fechado preguiçosamente (`_expire_stale`, chamado em listagem e criação). Por isso `GET /equipe/solicitacoes` faz commit.
- Dados da pessoa (nome, CRO, senha) pertencem ao usuário, não à clínica. `update_member` e `reset_password` recusam quando `other_clinics` (vínculo ou convite não vencido em outra clínica). Nome e CRO de outro admin só ele mesmo altera. Senha de outro admin nunca é redefinida por aqui.
- `get_member(lock=True)` trava também a linha de `users` e só depois consulta `other_clinics` em instrução separada (READ COMMITTED enxerga o que a transação anterior gravou; um EXISTS na mesma instrução usaria a foto antiga).
- E-mail já cadastrado nunca vira vínculo direto: só por convite com código entregue pessoalmente, aceito com a senha da própria pessoa. Quem só conhece a senha (por exemplo, quem a cadastrou em outra clínica) não ganha acesso (`test_who_only_knows_the_password_cannot_join_other_clinic`).
- E-mail inexistente gasta o mesmo tempo de um hash real (`burn_password_check`), para evitar enumeração por tempo de resposta (`service.verify_credentials`).
- Senhas com argon2id (`pwdlib` recommended). Nova senha: mínimo 10 caracteres (`schemas.py:NewPassword`) e diferente da atual.
- Em produção, `JWT_SECRET` padrão ou com menos de 32 caracteres impede a subida (`core/config.py:_check_production`).

## Tenancy e auditoria

- `login`, `me`, `equipe` (`/auth`), `primeiro-acesso` e `vinculos/aceitar` usam `get_db` (sessão global), porque leem só tabelas globais e acontecem antes de haver clínica. Quando precisam auditar, abrem `tenant_session(clinic_id)` à parte.
- `/auth/senha` e todo `/equipe/*` usam `get_tenant_db`: a auditoria e os pedidos (RLS) entram na mesma transação das tabelas globais.
- `get_current_user` usa uma sessão `get_db` separada da sessão de tenant do endpoint.
- Outros módulos devem usar `get_tenant_db` e nunca `get_db`. Quem precisa conferir se um usuário atua como dentista na clínica usa `service.active_role` (agenda, precificação, repasse, tratamento, prontuário, painel).

Ações auditadas (`audit.record`):

| Ação | Onde |
|---|---|
| `auth.login` | login bem-sucedido, e também o login final do primeiro acesso |
| `auth.senha_definida` | primeiro acesso, gravada em **todas** as clínicas ativas da pessoa |
| `auth.senha_trocada` | `/auth/senha` |
| `equipe.membro_adicionado`, `equipe.convite_criado`, `equipe.convite_renovado`, `equipe.convite_cancelado`, `equipe.convite_aceito` | cadastro e convites (o aceite grava na clínica do convite) |
| `equipe.membro_alterado` | só quando algo mudou; `details` traz papel/ativo com de/para e, para nome e CRO, apenas o nome do campo |
| `equipe.senha_redefinida` | redefinição pelo admin (a senha não vai ao log) |
| `equipe.solicitacao_criada`, `equipe.solicitacao_aceita`, `equipe.solicitacao_recusada`, `equipe.solicitacao_cancelada` | pedidos de mudança de admin |

Login com falha não é auditado (não há clínica para gravar).

## Decisões

| Decisão | Motivo |
|---|---|
| Papel consultado no banco a cada request | Revogação imediata, sem lista de bloqueio de tokens |
| `password_changed_at` + `iat_ms` em vez de lista de tokens | Trocar ou redefinir senha derruba as sessões antigas sem estado novo; precisa de milissegundos para pegar a troca no mesmo segundo do login |
| Senha provisória aleatória com `must_change_password` | O admin entrega a senha, mas ela só serve para a pessoa definir a dela |
| Convite com código de uso único para e-mail já cadastrado | O admin de uma clínica não pode se vincular a um usuário de outra só sabendo o e-mail |
| Tabelas de identidade e convites sem RLS | Login e aceite precisam delas antes de conhecer a clínica |
| Pedido aceito pelo próprio admin alvo para rebaixar/desativar | Um admin não tira outro do cargo sozinho, nem tem como tomar a conta dele |
| Pedidos em tabela de tenant (RLS) | São da clínica; só os envolvidos (admins dela) os veem |
| 409 para seleção de clínica | O mesmo endpoint resolve usuários de uma ou várias clínicas, e o front só reage ao 409 |
| CLI pede senha via `getpass` | A senha não fica no histórico do shell |

## Como estender

- **Novo papel:** adicione em `core/roles.py` **e** crie uma migração que recrie o CHECK `role_valid` de `clinic_memberships` **e de `membership_invites`** (a tupla `ROLES` das migrações 0001 e 0026 é fixa). O CHECK `new_role_valid` de `admin_change_requests` lista os papéis de destino do rebaixamento.
- **Proteger endpoint de outro módulo:**
  ```python
  user: CurrentUser = Depends(require_roles(Role.DENTISTA, Role.RECEPCAO)),
  db: Session = Depends(get_tenant_db),
  ```
  Se o endpoint só precisa dos papéis, use `dependencies=[Depends(require_roles(...))]`, como em `auditoria/router.py`.
- **Nova operação de equipe que mexe em admin:** chame `_lock_active_admins` antes de `get_member(lock=True)`, use `_check_admin_remains` e passe pela auditoria `equipe.*` no router, com commit no router.
- **Nova ação de pedido de admin:** inclua em `AdminChangeAction` e no CHECK `action_valid` (nova migração), trate em `accept_request`, e ajuste o validador de `schemas.py:AdminChangeCreate`.
- **Refresh token / troca de clínica sem novo login:** ainda não existem. O `typ` no payload já separa tipos de token.

## Tela

- `frontend/src/pages/config/Equipe.tsx`: aba "Equipe" de Configurações (só admin). Lista membros, convites e pedidos; mostra a senha provisória ou o código do convite uma única vez em modal (com cópia).
- `frontend/src/pages/config/Configuracoes.tsx`: abas Equipe (admin, aba inicial) e Anamnese.
- `frontend/src/pages/Login.tsx`: modos entrar, definir senha (reage ao 403 do login e chama `/auth/primeiro-acesso`, tratando o 409 de clínica) e aceitar convite (`/auth/vinculos/aceitar`).
- `frontend/src/components/TrocarSenha.tsx`: modal de troca da própria senha (`/auth/senha`), aberto pelo `layout/AppLayout.tsx`. O token novo devolvido substitui o da sessão.

## Armadilhas

- `create_clinic_with_admin` **reaproveita** um usuário existente com o mesmo e-mail. Nesse caso a senha informada é ignorada e o nome não é atualizado, e só o vínculo admin é criado.
- Sem limite de tentativas nas rotas públicas (`/auth/login`, `/auth/primeiro-acesso`, `/auth/vinculos/aceitar`). O código de convite (~49 bits) só é testado depois de e-mail e senha corretos, mas a senha provisória (~59 bits) não tem nenhuma barreira além do argon2.
- O cadastro revela a um admin se um e-mail já existe no sistema: `POST /equipe/membros` devolve `member`+`temporary_password` para e-mail novo e `invite`+`invite_code` para e-mail já cadastrado (e 409 se já está na equipe ou já tem convite).
- O aceite do convite grava o vínculo (commit) e só depois abre outra transação para a auditoria `equipe.convite_aceito`. Se a segunda falhar, o vínculo existe sem registro de auditoria. O mesmo vale para `auth.senha_definida` e `auth.login` no primeiro acesso, e para a troca de senha dele já commitada se o login final falhar.
- No primeiro acesso, a senha é trocada e commitada **antes** do login. Se o login seguinte falhar (por exemplo, sem vínculo ativo, ou o 409 de escolha de clínica), a senha provisória já não vale mais.
- Login **com falha** não é auditado, porque ainda não há clínica para gravar o registro.
- Convite vencido não some: aparece em `GET /equipe/convites` até ser renovado ou cancelado, e bloqueia novo convite ao mesmo e-mail ("Já existe um convite").
- `other_clinics` considera convite não vencido em outra clínica: um convite pendente já protege nome, CRO e senha da pessoa.
- Desativar um membro desativa só o vínculo (`clinic_memberships.active`); `users.active` não tem rota para mudar. Reativar é um `PATCH` com `active=true`.
- `GET /equipe/solicitacoes` escreve no banco (marca expiradas), apesar de ser GET.
- Cada request autenticado custa uma consulta extra (join de 3 tabelas em `session_role`). Lembre disso antes de colocar cache.
- `service.active_role` (sem checagem de senha/`iat`) continua em uso pelos outros módulos para validar dentistas; ele não substitui `session_role` na autenticação.
