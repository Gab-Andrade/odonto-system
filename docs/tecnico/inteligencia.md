---
modulo: inteligencia
atualizado_em: 1ee64af
---
# Inteligência (alertas por regra)

> Calcula na hora alertas acionáveis (recall, orçamento parado, faltas, inadimplência) a partir dos dados de outros módulos, com regras configuráveis por clínica e dispensa temporária por alerta.

## Responsabilidades

- Catálogo fixo de 7 regras em código (`regras.py:RULES`), configuração por clínica (liga/desliga e parâmetros), cálculo dos alertas, dispensa e reativação.
- **Não guarda alertas.** Só guarda configuração e dispensas. Cada listagem reexecuta as consultas.
- **Fora do módulo:** envio de mensagens (WhatsApp/e-mail estão em stand-by; nada é enviado). Os dados de origem moram em agenda, tratamento, prontuário, financeiro e pacientes. O módulo só lê essas tabelas.
- O painel reaproveita `service.summary` para as contagens (`painel/router.py`, importa `alerts_service`).

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `alert_rule_settings` | sim | Configuração da clínica por regra (ligada e parâmetros em JSONB) |
| `alert_dismissals` | sim | "Dispensar até a data" de um alerta específico, append-only |

- Unicidade `(clinic_id, code)` em `alert_rule_settings`. Sem linha, a regra vale com os padrões do catálogo e está ligada.
- `code` tem CHECK na migração `0019_inteligencia_alertas.py` com a lista fechada de códigos. **Regra nova exige nova migração** que altere esse CHECK nas duas tabelas.
- `alert_dismissals`: a migração revoga UPDATE/DELETE/TRUNCATE do `odonto_app`. Vale o registro mais recente de cada `(code, alert_key)`; reativar é inserir um novo registro com `until = hoje`. `created_at` usa `clock_timestamp()` para a ordem real dentro da mesma transação.
- `alert_key` é um texto de 80 caracteres, mas na prática é sempre um UUID (ver Regras).

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| GET | `/inteligencia/regras` | todos | Catálogo com configuração efetiva e `param_spec` |
| PUT | `/inteligencia/regras/{code}` | admin, gestor | Liga/desliga e grava parâmetros |
| GET | `/inteligencia/alertas` | todos (filtrado por papel) | Lista alertas; filtros `regra`, `paciente_id`, `dentista_id`, `incluir_dispensados` |
| GET | `/inteligencia/alertas/resumo` | todos (filtrado por papel) | Contagem por regra, sem dado de paciente |
| POST | `/inteligencia/alertas/dispensar` | todos | Esconde um alerta até uma data (201) |
| POST | `/inteligencia/alertas/reativar` | todos | Volta a mostrar (201) |

- 404 para regra inexistente **ou não visível ao papel** e para alerta que não existe mais; 422 para parâmetro/chave/data inválidos (`router.py:_http`). O filtro `regra` desconhecido em `/alertas` dá 422.

## Regras de negócio e invariantes

- Visibilidade por papel: `regras.RuleDef.roles` (`CLINICAL_ROLES`, `FINANCE_ROLES` etc.). `service.compute_alerts` só roda regras visíveis ao papel, ligadas e, se pedido, filtradas. Recepção não vê "canal sem retorno"; dentista e ASB não veem contas em atraso.
- Todo `FINDERS[code]` precisa existir para cada regra do catálogo: há um `assert` na carga do módulo (`service.py`).
- Parâmetros: `regras.validate_params` rejeita desconhecidos, não inteiros (inclusive `bool`) e fora da faixa; termos são normalizados (minúsculo, espaços colapsados, sem duplicados, máximo 10 de até 40 caracteres). Parâmetros omitidos no PUT **voltam ao padrão** (`service.save_rule`).
- `regras.effective_params` tolera valor guardado inválido (faixa mudou) voltando ao padrão em vez de quebrar a listagem.
- Dispensa (`service.dismiss`): `alert_key` precisa ser UUID; `until` deve ser futuro e no máximo 365 dias (padrão 30, `regras.check_snooze`); o alerta tem de existir hoje entre os calculados para o papel, senão 404. Dispensa vale só enquanto `until > hoje`; depois disso o alerta volta sozinho se a condição persistir.
- Reativar (`service.restore`) só funciona se há dispensa ativa.
- Fuso: datas de corte usam `clinic_timezone` (`service.tz/today/_instant`).
- "Consulta futura" (`_has_future_appointment`): agendamento do tipo consulta, status agendado ou confirmado, a partir de agora. Silencia profilaxia, canal e orçamento aprovado sem agendamento.
- Só pacientes ativos geram alertas, **exceto** `conta_em_atraso` (a dívida persiste com cadastro desativado) e `atendimento_aberto` (não filtra paciente).
- Chaves dos alertas: paciente (profilaxia, faltas, conta em atraso), item do plano (canal), plano (orçamentos), atendimento (atendimento aberto).
- Ordenação: severidade (alta, média, baixa), depois data do fato, depois nome do paciente.

## Tenancy e auditoria

- Tudo usa `get_tenant_db`: as consultas leem tabelas de outros módulos confiando no RLS, sem filtrar `clinic_id`.
- Ações auditadas, com commit no router:
  - `inteligencia.regra_alterada` (detalhes: campos alterados e `ativa`)
  - `inteligencia.alertas_listados` (só contagem e regras, sem nomes; `entity_id` = paciente quando filtrado)
  - `inteligencia.alerta_dispensado`
  - `inteligencia.alerta_reativado`
- `/alertas/resumo` **não é auditado** porque não traz dado de paciente. Mas `/alertas` traz nome e telefone, daí a auditoria.

## Decisões

| Decisão | Motivo |
|---|---|
| Alertas calculados na hora, não persistidos | Sem estado a sincronizar: resolver a causa (agendar, receber) faz o alerta sumir sozinho |
| Dispensa append-only por `(code, key)` | Mantém histórico de quem dispensou o quê; reativar não apaga nada |
| Catálogo de regras em código, não em tabela | Cada regra tem consulta SQL própria; a tabela só guarda o que a clínica ajusta |
| Dispensa só aceita alerta que existe agora | Impede acumular dispensas de chaves arbitrárias |
| Sem envio externo | WhatsApp/e-mail em stand-by |

## Como estender

Nova regra:
1. Adicionar um `RuleDef` em `regras.py:RULES` (código, severidade, papéis, parâmetros).
2. Escrever o finder em `service.py` e registrar em `FINDERS` (a `assert` falha se faltar).
3. Nova migração alterando o CHECK `code_valid` das duas tabelas (skill `nova-migracao`).
4. Cobrir em `tests/test_inteligencia_unit.py` e `test_inteligencia_integration.py`; documentar a regra na doc de usuário.

Novo parâmetro: incluir `IntParam`/`TermsParam` na regra. Configurações já guardadas continuam válidas porque faltantes assumem o padrão.

## Armadilhas

- `alerts_listados` e `compute_alerts` executam todas as regras ligadas do papel a cada chamada; o painel chama `summary`, então o custo cresce com a base. Não há cache nem índice dedicado.
- `dismiss` recalcula todos os alertas da regra para validar a chave.
- `_canal` casa por `ToothStatus.code == "endodontia"` do odontograma **ou** pelos termos; se a legenda da clínica não tiver esse código, só os termos valem.
- Busca por termos usa `LIKE` no código + descrição do item (`escape_like`); termos genéricos (ex.: "canal") podem gerar falsos positivos.
- Em `_canal`, "retorno" é qualquer atendimento do paciente iniciado depois do item e diferente do atendimento em que foi realizado, mesmo que não seja do dentista responsável.
- `save_rule` com `params` vazio redefine tudo para os padrões, não preserva o que estava salvo.
- `dentista_id` do alerta vem de `performed_by` (profilaxia, canal) ou do dentista do plano/atendimento; `faltas_repetidas` e `conta_em_atraso` têm `dentist_id` nulo, então filtrar por dentista as exclui.
- `_check_key` valida papel com 404 (esconde a existência da regra), diferente do 403 usado em outros módulos.
