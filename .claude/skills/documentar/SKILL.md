---
name: documentar
description: Cria ou atualiza a documentação de um módulo do backend nas duas versões, técnica (docs/tecnico/) e para público não técnico (docs/usuario/), disparando os agentes doc-tecnico e doc-usuario em paralelo. Use quando um módulo for criado ou alterado, ou quando o usuário pedir para documentar.
argument-hint: <modulo> [<modulo> ...]
---
# Documentar módulo(s)

Módulos: `$ARGUMENTS` (nomes das pastas em `backend/app/modules/`). Sem argumento, pergunte qual.

Você só **orquestra**. Não leia o código do módulo nem escreva a documentação. Os agentes fazem isso em contextos próprios.

## 1. Decidir o modo de cada módulo (barato: só git)

Para cada módulo, leia apenas o cabeçalho (primeiras ~6 linhas) de `docs/tecnico/<modulo>.md`:

- Arquivo não existe → modo `completo`.
- Existe, com `atualizado_em: <hash>` → rode
  `git diff --stat <hash>..HEAD -- backend/app/modules/<modulo> backend/alembic backend/tests` e
  `git status --porcelain -- backend/app/modules/<modulo>`.
  - Nada mudou → pule o módulo e avise o usuário.
  - Mudou → modo `incremental` com base `<hash>`.
  - Se o diff tocar mais da metade dos arquivos do módulo, use `completo` (reescrever sai mais barato que remendar).

Faça o mesmo com `docs/usuario/<modulo>.md`, já que os dois podem estar em commits diferentes.

## 2. Disparar os agentes em paralelo

Numa **única mensagem**, uma chamada `Agent` por (módulo × público):

- `subagent_type: doc-tecnico`, prompt: `modulo=<m> modo=<completo|incremental> base=<hash|->`
- `subagent_type: doc-usuario`, prompt: `modulo=<m> modo=<completo|incremental> base=<hash|->`

Com 2 módulos, são 4 chamadas na mesma mensagem. Cada agente escreve só o próprio arquivo e a própria linha do índice, então não há conflito.

## 3. Fechar

Repasse ao usuário só o resumo devolvido por cada agente (uma linha por documento). Não releia os documentos gerados.

Se algum agente apontar uma **decisão de arquitetura** nova, proponha uma linha para "Decisões registradas" em `docs/PLANO.md` e pergunte antes de escrever.
