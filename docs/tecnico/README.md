# Documentação técnica

Para quem vai mexer no código, sejam pessoas ou agentes. Visão de produto e roadmap estão em [PLANO.md](../PLANO.md). Comandos e convenções rápidas estão em [CLAUDE.md](../../CLAUDE.md).

Cada módulo tem um documento próprio, gerado e atualizado pela skill `documentar`. Leia o do módulo antes de alterá-lo.

## Módulos

| Módulo | Resumo |
|---|---|
| [identidade](identidade.md) | Clínicas, usuários, vínculos, login (JWT), cadastro de equipe só pelo admin (senha provisória, convites com código, pedidos para mudar admin) e dependências de autenticação/papéis usadas por todos os módulos |
| [auditoria](auditoria.md) | Consulta do log de auditoria (LGPD) da clínica |
| [precificacao](precificacao.md) | Tabelas de preço versionadas com herança, atribuição por escopo, resolução com memória de cálculo, snapshots, importação de planilhas e tabelas calculadas por fórmula (fichas técnicas, variáveis; publicação com confirmação de erros de cálculo) |
| [estoque](estoque.md) | Materiais, lotes com validade, movimentos append-only, estoque mínimo, custo médio ponderado e baixa automática FEFO pela ficha técnica ao realizar item do plano; rastreio por paciente |
| [pacientes](pacientes.md) | Cadastro de pacientes com busca por nome, CPF ou telefone, responsável de menores e consentimentos LGPD append-only; leituras auditadas |
| [agenda](agenda.md) | Cadeiras, agendamentos e bloqueios sem conflito de dentista/cadeira (constraint de exclusão), máquina de status e histórico append-only |
| [prontuario](prontuario.md) | Anamnese configurável (modelos versionados, respostas imutáveis, alertas) e atendimento com evolução clínica imutável, adendos, assinatura e transferência entre dentistas; toda leitura auditada, sem acesso da recepção |
| [odontograma](odontograma.md) | Legenda de marcações por clínica (com cor pessoal por usuário e região coroa/raiz), histórico append-only por dente/face (FDI), anotações append-only por dente e arcada do paciente; odontograma reconstruído em qualquer data, comparação entre momentos, visualização 2D/3D e biblioteca de dentes 3D (.glb gerado por código); leituras auditadas |
| [tratamento](tratamento.md) | Plano de tratamento e orçamento: itens por dente/face, emissão com preço congelado (snapshots), validade, desconto com limite por papel, aprovação parcial e realização vinculada ao atendimento, ao odontograma e à baixa de estoque |
| [financeiro](financeiro.md) | Contas a receber (parcelamento do orçamento aprovado e avulsas), recebimentos append-only com estorno e taxa, extrato do paciente (dentista lê se a clínica liberar) e contas a pagar; invariantes de valor em gatilhos do banco, registro manual sem gateway |
| [repasse](repasse.md) | Comissão de dentistas sobre o recebido: regras por dentista/procedimento com vigência, prévia e fechamentos acumulados append-only |
| [inteligencia](inteligencia.md) | Alertas por regra calculados na hora (recall, orçamento parado, faltas, atraso), com regras configuráveis por clínica, visibilidade por papel e dispensa temporária append-only |
| [imagens](imagens.md) | Exames de raio-X DICOM por paciente: arquivo em armazenamento local ou S3 com metadados lidos do cabeçalho, classificação por tipo/dentes, arquivo e metadados imutáveis, invalidação com motivo (sem exclusão); toda leitura auditada, sem acesso da recepção |
| [painel](painel.md) | Indicadores agregados calculados na hora: visão do gestor, desempenho do dentista, equipe, tendências mensais e metas (única escrita, auditada em `panel_goals`) |

## Fundação (válida para todos os módulos)

### Isolamento entre clínicas

O banco tem dois roles:

| Role | Uso | RLS |
|---|---|---|
| `odonto` | dono do schema; roda migrações e as fixtures de limpeza dos testes | `FORCE ROW LEVEL SECURITY` vale até para ele |
| `odonto_app` | a aplicação | sem `BYPASSRLS` e não é dono das tabelas, então as policies sempre valem |

Fluxo de uma requisição autenticada:

```
Bearer JWT ─► identidade.deps.get_current_user   (sessão global get_db)
                 └─ active_role(): papel relido do banco
          ─► identidade.deps.get_tenant_db       (tenant_session(clinic_id))
                 └─ listener after_begin (core/db.py):
                    set_config('app.clinic_id', <id>, true) em TODA transação
          ─► policy tenant_isolation (core/rls.py) filtra USING e WITH CHECK
```

Consequências:
- Consultas em sessão de tenant não filtram `clinic_id`, porque o banco já filtra. Uma escrita com `clinic_id` de outra clínica falha com erro de RLS.
- Sessão sem tenant (`get_db`) enxerga **zero** linhas de tabelas com RLS, porque o predicado resulta em `NULL`.
- `set_config(..., true)` é local à transação. Por isso o listener reaplica o valor a cada `begin`, inclusive depois de um `commit()` no meio do request.

Toda tabela nova de clínica precisa de `TenantMixin` no model **e** de `enable_tenant_rls()` na migração (skill `nova-migracao`). Isso é conferido pelo agente `revisor-tenancy`.

### Autorização

Papéis em `app/core/roles.py`: `admin`, `gestor`, `dentista`, `asb`, `recepcao`. Endpoints usam `require_roles(...)` de `identidade.deps`. Detalhes em [identidade](identidade.md).

### Auditoria

`app.core.audit.record()` adiciona um `AuditLog` à sessão de tenant, e quem chama faz o commit. A tabela é append-only para `odonto_app`. Detalhes em [auditoria](auditoria.md).

### Testes

- Unitários não usam banco. Os de integração (`@pytest.mark.integration`) recriam o schema inteiro (downgrade base → upgrade head) por sessão de testes.
- `clean_db` faz `TRUNCATE` como `odonto` antes de cada teste. Tabela nova precisa entrar nessa lista.
- `make_clinic(role=...)` cria clínica + usuário + vínculo e devolve `(clinic, user, password)`.
