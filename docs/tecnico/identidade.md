---
modulo: identidade
atualizado_em: 0207683
---
# Identidade

> Quem é o usuário, em qual clínica ele está atuando e com qual papel.

## Responsabilidades

- Cadastro de clínicas, usuários e vínculos usuário↔clínica com papel.
- Login por e-mail e senha, com emissão de JWT de acesso.
- Dependências FastAPI usadas por **todos** os outros módulos: `get_current_user`, `require_roles`, `get_tenant_db` (`deps.py`).
- Comando administrativo `python -m app.cli criar-clinica` (`app/cli.py`).

Fora daqui: hash e JWT ficam em `app/core/security.py`, a sessão de tenant em `app/core/db.py`, e o registro de auditoria em `app/core/audit.py`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `clinics` | não (global) | clínica; `slug` único; `active` desliga a clínica inteira |
| `users` | não (global) | pessoa; um usuário pode atuar em várias clínicas |
| `clinic_memberships` | não (global) | vínculo usuário↔clínica com `role`; `active` revoga só aquele vínculo |

- As três tabelas são globais de propósito: o login precisa lê-las antes de saber a clínica. Por isso o isolamento delas fica na camada de serviço, e nenhuma consulta pode expor dados de outra clínica.
- `users.email` tem CHECK `email = lower(email)`. Normalize com `service.normalize_email` antes de gravar ou consultar.
- `clinic_memberships`: unicidade `(user_id, clinic_id)`. `role` é `String(20)` com CHECK na migração, e o model usa `Enum(native_enum=False, create_constraint=False)`.
- `ondelete`: vínculos caem em cascata com usuário ou clínica. Tabelas de tenant usam `RESTRICT` para `clinics`, então na prática clínica não se apaga, se desativa.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| POST | `/auth/login` | público | autentica e devolve `access_token` + clínica + papel |
| GET | `/auth/me` | qualquer autenticado | dados do usuário e da clínica do token |

- `POST /auth/login` responde **409** com `ClinicSelectionResponse` (lista de clínicas) quando o usuário tem mais de um vínculo ativo e não enviou `clinic_id`. O cliente deve reenviar o login com `clinic_id`.
- Credencial errada, usuário inativo, sem vínculo ativo ou `clinic_id` inválido: tudo vira o mesmo **401** genérico.

## Regras de negócio e invariantes

- O papel **não** vem do token. `get_current_user` chama `service.active_role` a cada request, e usuário, vínculo ou clínica inativos geram 401 na hora (`deps.py:get_current_user`).
- O JWT exige `exp`, `sub`, `cid` e `typ == "access"` (`core/security.py:decode_access_token`).
- E-mail inexistente gasta o mesmo tempo de um hash real (`burn_password_check`), para evitar enumeração de e-mails por tempo de resposta (`service.authenticate`).
- Senhas com argon2id (`pwdlib` recommended).
- Em produção, `JWT_SECRET` padrão ou com menos de 32 caracteres impede a subida (`core/config.py:_check_production`).

## Tenancy e auditoria

- `login` e `me` usam `get_db` (sessão global), porque leem só tabelas globais.
- Login bem-sucedido abre uma `tenant_session` da clínica escolhida só para gravar `audit.record(..., "auth.login", request=request)`.
- Outros módulos devem usar `get_tenant_db` (que já depende de `get_current_user`) e nunca `get_db`.

## Decisões

| Decisão | Motivo |
|---|---|
| Papel consultado no banco a cada request | Revogação imediata, sem lista de bloqueio de tokens |
| Tabelas de identidade sem RLS | O login precisa delas antes de conhecer a clínica |
| 409 para seleção de clínica | O mesmo endpoint resolve usuários de uma ou várias clínicas, e o front só reage ao 409 |
| CLI pede senha via `getpass` | A senha não fica no histórico do shell |

## Como estender

- **Novo papel:** adicione em `core/roles.py` **e** crie uma migração que recria o CHECK `role_valid` de `clinic_memberships` (a tupla `ROLES` da 0001 é fixa).
- **Proteger endpoint de outro módulo:**
  ```python
  user: CurrentUser = Depends(require_roles(Role.DENTISTA, Role.RECEPCAO)),
  db: Session = Depends(get_tenant_db),
  ```
  Se o endpoint só precisa dos papéis, use `dependencies=[Depends(require_roles(...))]`, como em `auditoria/router.py`.
- **Refresh token / troca de clínica sem novo login:** ainda não existem. O `typ` no payload já separa tipos de token.

## Armadilhas

- `create_clinic_with_admin` **reaproveita** um usuário existente com o mesmo e-mail. Nesse caso a senha informada é ignorada e o nome não é atualizado, e só o vínculo admin é criado.
- Login **com falha** não é auditado, porque ainda não há clínica para gravar o registro. Só o sucesso gera `auth.login`.
- Cada request autenticado custa uma consulta extra (join de 3 tabelas em `active_role`). Lembre disso antes de colocar cache.
- `get_current_user` usa uma sessão `get_db` separada da sessão de tenant do endpoint, então são duas conexões por request.
- Não há rate limit no login até o momento.
