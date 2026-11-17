---
modulo: <nome>
atualizado_em: <hash curto do HEAD>
---
# <Nome do módulo>

> Uma frase: o que este módulo resolve.

## Responsabilidades

O que o módulo faz e, igualmente importante, o que fica **fora** dele (e em qual módulo isso mora).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `tabela` | sim/não (global) | uma linha |

Relações e restrições que não são óbvias pelo model (CHECKs, unicidade composta, ondelete, append-only).
Não liste colunas: elas estão no model e no OpenAPI.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/x` | admin, gestor | ... |

Códigos de resposta fora do padrão (ex.: 409 com corpo próprio).

## Regras de negócio e invariantes

Regras que, se quebradas, causam bug ou vazamento. Cada uma em uma linha, com onde é garantida (`arquivo:função`).

## Tenancy e auditoria

- Quais sessões usa (`get_tenant_db` / `get_db`) e por quê.
- Quais ações chamam `audit.record` e com qual `action`.

## Decisões

| Decisão | Motivo |
|---|---|

## Como estender

Passos concretos para as mudanças mais prováveis neste módulo.

## Armadilhas

Comportamentos surpreendentes, dívidas conhecidas e limitações atuais.
