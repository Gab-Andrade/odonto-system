---
modulo: estoque
atualizado_em: 6363519
---
# Estoque

> Cadastro de materiais com custo unitário, que alimenta o custo de materiais da ficha técnica na precificação por custo.

## Responsabilidades

- Cadastrar, alterar e desativar materiais da clínica e expor o custo unitário atual a outros módulos (`service.py:material_costs`).
- Controlar quem vê o custo: só admin e gestor (`router.py:_out`).
- **Fora do módulo:** fichas técnicas, quantidades por procedimento e cálculo de preço (módulo [precificacao](precificacao.md), que referencia `materials` por FK). Lotes, validade, entradas/saídas, baixa automática e estoque mínimo ainda não existem; o `models.py` os prevê para a Fase 3, neste mesmo módulo.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `materials` | sim | Material com unidade de uso, categoria opcional, custo unitário e flag `active` |

- `uq_materials_id_clinic (id, clinic_id)` existe para que `cost_sheet_items` use FK composta `(material_id, clinic_id)` e o banco garanta que a ficha só aponta para material da mesma clínica (`precificacao/models.py`, `fk_cost_sheet_items_material_same_clinic`).
- `uq_materials_clinic_name (clinic_id, name)` é sensível a maiúsculas no banco, mas o service compara com `lower()` (ver Armadilhas).
- CHECK `unit_cost >= 0`. `unit_cost` é `Numeric(12, 4)` (4 casas, pois o material é comprado em caixa e usado em frações).
- `clinic_id` tem `ondelete=RESTRICT`. Não há exclusão de material: só desativação.
- Migração: `0004_estoque_materiais.py` (RLS via `enable_tenant_rls`). A tabela está no `TRUNCATE` de `clean_db`.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/estoque/materiais` | admin, gestor, dentista, asb | Lista ordenada por nome; `?incluir_inativos=true` inclui inativos |
| POST | `/estoque/materiais` | admin, gestor | Cria material |
| GET | `/estoque/materiais/{id}` | admin, gestor, dentista, asb | Detalhe |
| PATCH | `/estoque/materiais/{id}` | admin, gestor | Altera campos enviados, inclusive `active` |

- 404 para material inexistente ou de outra clínica; 409 para nome duplicado (`router.py:_http`).
- Recepção recebe 403 em todas as rotas.
- Para dentista e ASB, as respostas de GET omitem `unit_cost` e `updated_at` (schema `MaterialOut` em vez de `MaterialCostOut`).

## Regras de negócio e invariantes

- Nome único por clínica sem diferenciar maiúsculas/minúsculas: `service.py:_ensure_unique_name` (na criação e no PATCH, excluindo o próprio id).
- Custo sempre normalizado para 4 casas antes de gravar: `service.py:_cost`.
- Material nunca é excluído; fichas técnicas dependem dele: não há DELETE.
- Custo não é exposto a dentista/ASB: `router.py:_out` decide o schema pelo papel. Rotas de escrita já exigem `MANAGE`.
- PATCH: `name`, `unit`, `unit_cost` e `active` com valor `null` são ignorados; só `category` aceita `null` explícito para limpar (`service.py:update_material`, usa `"category" in changes`).

## Tenancy e auditoria

- Todas as rotas usam `get_tenant_db`; nenhuma consulta filtra `clinic_id`, o RLS cuida disso. `get_material` devolve 404 para material de outra clínica pelo mesmo motivo.
- `audit.record` e commit ficam no router, não no service:
  - `estoque.material_criado` (details: `unit_cost`)
  - `estoque.material_alterado` (details: campos alterados e novos valores como string)
- Leituras não são auditadas, mesmo expondo custo.

## Decisões

| Decisão | Motivo |
|---|---|
| Versão mínima, sem lotes | Atende só a precificação por custo; o custo unitário virá dos lotes depois sem mudar quem consome via `material_costs` |
| Outros módulos usam `service.material_costs` (dataclass `MaterialCost`), não o model | Isola a futura mudança da origem do custo |
| Só desativar, nunca excluir | Fichas técnicas referenciam o material |
| Custo oculto para dentista/ASB | Eles consultam o cadastro no dia a dia, mas custo é dado financeiro |

## Como estender

- **Novo campo no material:** model, migração nova (não edite a 0004), `MaterialCreate`/`MaterialUpdate`/`MaterialOut` e `update_material`, que trata campo a campo.
- **Lotes/entradas/saídas:** novas tabelas neste módulo com `TenantMixin`, `enable_tenant_rls`, import em `app/models.py` e `TRUNCATE` em `tests/conftest.py`. Faça `material_costs` derivar o custo dos lotes mantendo a assinatura e `MaterialCost`.
- **Novo papel de leitura:** ajuste `READ` em `router.py`; mantenha custo restrito a `MANAGE`.

## Armadilhas

- A unicidade de nome é inconsistente entre camadas: a checagem do service ignora caixa, mas `uq_materials_clinic_name` não. Numa corrida entre duas requisições, ambas passam pelo service e podem gravar nomes que só diferem na caixa ("Resina" e "resina"). Corridas com nome idêntico caem na constraint e o handler global de `IntegrityError` em `app/main.py` responde 409.
- `material_costs` devolve inclusive materiais inativos (o campo `active` vai no resultado); quem consome decide. Comportamento intencional: a precificação rejeita inativos ao montar a ficha (`precificacao/service.py:_validate_materials`), mas fichas existentes continuam custeadas com o material desativado (teste `test_inactive_material_still_costs_existing_sheets` em `tests/test_formulas_integration.py`).
- `response_model` das rotas GET é uma união (`MaterialCostOut | MaterialOut`); o OpenAPI mostra as duas formas.
- Alterar `unit_cost` muda imediatamente o preço calculado de qualquer ficha que use o material; o módulo não guarda histórico de custo (snapshots ficam em precificação).
- `details` da auditoria de alteração grava o valor novo apenas, sem o anterior.
