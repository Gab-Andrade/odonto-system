---
modulo: tratamento
atualizado_em: 3afacea
---
# Plano de tratamento e orçamento

> Aqui o dentista monta o plano de tratamento do paciente, a recepção negocia o orçamento e dá o desconto dentro do limite, e o paciente aprova tudo ou parte. Os procedimentos realizados marcam o odontograma sozinhos.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Montar e editar planos, dar desconto de qualquer valor, emitir, registrar a decisão do paciente, cancelar planos e procedimentos, duplicar planos, definir as regras da clínica e ver os planos |
| Gestor | Dar desconto de qualquer valor, emitir, registrar a decisão do paciente, cancelar planos e procedimentos aprovados, definir as regras da clínica e ver os planos |
| Dentista | Montar e editar planos, dar desconto até o limite da clínica, emitir, registrar a decisão do paciente, cancelar planos e procedimentos aprovados, duplicar planos, realizar procedimentos no próprio atendimento e ver os planos |
| ASB | Ver os planos e o orçamento de cada paciente |
| Recepção | Dar desconto até o limite da clínica, emitir, registrar a decisão do paciente, cancelar planos e ver os planos |

## O que dá para fazer

### Montar um plano de tratamento
Onde: ficha do paciente → aba **Planos e orçamentos** → botão **+ Novo plano**. Só Administrador e Dentista veem o botão.

1. Abra a ficha do paciente. O paciente precisa estar ativo no cadastro.
2. Clique em **+ Novo plano**. O plano nasce como rascunho, com o título "Plano de tratamento", e o responsável é quem criou o plano. A tela ainda não pergunta outro dentista. Para trocar o responsável: *Tela em construção.*
3. Trocar o título e as observações também está em *Tela em construção.*
4. Na tela do plano, clique em **+ Procedimento**. Informe o código do procedimento (pode escolher da lista) e, se quiser, o dente (numeração FDI), as faces (por exemplo, "MOD").
5. Se quiser que o procedimento apareça no odontograma, escolha no campo "No odontograma, 'a fazer'" o item que indica "a fazer" e, no campo "Ao realizar, marcar", o item que indica "feito". Isso só funciona com dente informado.
6. Para cada procedimento, a tabela mostra o preço que seria cobrado hoje. Se a clínica não tiver preço para ele, aparece em vermelho o motivo.

### Editar um rascunho
Onde: aba **Planos e orçamentos** → abra o plano em rascunho. Os botões de edição só aparecem enquanto o plano está em rascunho.

1. Só é possível mudar um plano enquanto ele estiver em **rascunho**.
2. Trocar o título, as observações e o dentista responsável: *Tela em construção.*
3. Para incluir um procedimento, clique em **+ Procedimento**. Para tirar um, clique em **Remover** na linha dele. Para trocar um procedimento, tire o errado e inclua o certo.
4. Mudar a ordem dos procedimentos e corrigir os dados de um procedimento já incluído (dente, faces, observações): *Tela em construção.*
5. Depois de emitido, o plano não muda. Para alterar um orçamento emitido, use "duplicar" (veja abaixo).

### Dar desconto
Onde: plano em rascunho → botão **Desconto**. Abre uma janela para informar a porcentagem.

1. Informe o desconto em porcentagem, de 0% a 100%.
2. Até o limite da clínica, o Dentista e a Recepção podem dar o desconto. Acima do limite, só o Administrador ou o Gestor.
3. O desconto vale sobre os procedimentos aprovados e realizados. Os recusados e os cancelados não entram no cálculo.
4. Só é possível dar desconto enquanto o plano estiver em rascunho.

### Emitir o orçamento
Onde: plano em rascunho → botão **Emitir orçamento**. Fica desligado enquanto o plano não tiver procedimento.

1. Antes de emitir, o plano precisa ter ao menos um procedimento.
2. Todos os procedimentos precisam ter preço. Se algum não tiver, o sistema lista quais são e não emite nada.
3. Ao emitir, o sistema guarda o preço de cada procedimento e o desconto. Esses valores não mudam mais, mesmo que a tabela de preço da clínica mude depois.
4. A validade do orçamento é contada a partir do dia da emissão. O padrão é 30 dias.
5. Depois de emitido, o orçamento pode receber a decisão do paciente.

### Registrar a decisão do paciente
Onde: plano emitido e dentro da validade → botão **Registrar decisão**. Abre a janela "Decisão do paciente".

1. Na janela, todos os procedimentos já vêm marcados. Desmarque os que o paciente não aprovou. Os que ficarem de fora são marcados como recusados.
2. Você pode aprovar só uma parte do orçamento.
3. Se ao menos um procedimento for aprovado, o orçamento fica como "aprovado". Se nenhum for, fica como "recusado". Com tudo desmarcado, o botão mostra "Registrar recusa".
4. A decisão só pode ser registrada enquanto o orçamento estiver emitido e dentro da validade.

### Realizar um procedimento no atendimento
Onde: plano aprovado → botão **Realizado**, na linha do procedimento. Antes, abra o paciente na aba **Atendimentos** e deixe um atendimento seu aberto. Sem ele, o botão fica desligado e a tela avisa.

1. Abra o atendimento do paciente. O atendimento precisa estar aberto.
2. Clique em **Realizado** no procedimento aprovado. O sistema usa o atendimento aberto que é seu.
3. Só o dentista que está com esse atendimento aberto pode registrar o procedimento como realizado.
4. Se o procedimento estiver ligado a um dente no odontograma, o sistema tira a marca de "a fazer" e marca "feito" no dente, dentro do mesmo atendimento.
5. Ao realizar, o sistema também dá baixa no estoque dos materiais da ficha técnica daquele procedimento (a lista de materiais que ele usa). Saem primeiro os lotes que vencem antes, e nunca lote vencido. Sem ficha técnica, nada sai do estoque.
6. Se faltar material, o procedimento é registrado do mesmo jeito. A tela mostra um aviso em amarelo dizendo o que faltou e quanto. O aviso aparece só logo depois de realizar. Confira o saldo no [Estoque](estoque.md).
7. Quando todos os procedimentos aprovados forem realizados ou cancelados, e ao menos um tiver sido realizado, o plano fica como "concluído". Se todos forem cancelados sem nenhum realizado, o plano fica como "cancelado".

### Cancelar um plano
Onde: plano em rascunho ou emitido → botão **Cancelar** (vermelho). Abre uma janela pedindo o motivo.

1. Só é possível cancelar planos em rascunho ou emitidos.
2. Informe o motivo, com até 300 caracteres.
3. Um plano já aprovado não é cancelado de uma vez. Cancele os procedimentos um a um.

### Cancelar um procedimento aprovado
Onde: plano aprovado → botão **Cancelar** na linha do procedimento. Abre uma janela pedindo o motivo.

1. Só é possível cancelar procedimentos que foram aprovados e ainda não foram realizados.
2. Informe o motivo, com até 300 caracteres.

### Duplicar um plano
Onde: plano → botão **Duplicar**. Na tela, o botão aparece para orçamento vencido, recusado ou cancelado. Só Administrador e Dentista veem.

1. O sistema cria um novo rascunho com os mesmos procedimentos, o mesmo dentista, o mesmo título e as mesmas observações.
2. Use para refazer um orçamento vencido, um orçamento recusado ou para atualizar os preços.
3. O rascunho novo começa sem preço congelado, sem decisão do paciente e **sem desconto**. Informe o desconto de novo, se for o caso.

### Ver os planos de um paciente
Onde: ficha do paciente → aba **Planos e orçamentos**. Todos os perfis veem essa aba.

1. Veja a lista de planos do paciente, do mais recente para o mais antigo. Cada linha mostra a situação, a validade e o desconto.
2. Clique em um plano para ver os procedimentos, o preço de cada um e os totais: valor proposto, desconto e valor aprovado.
3. Em qualquer plano que não esteja em rascunho, dá para clicar em **Imprimir**. A folha traz uma linha para a assinatura do paciente ou do responsável.
4. Todo plano aberto fica registrado no histórico de ações.

### Ver e definir as regras da clínica
*Tela em construção.*

1. Todos da equipe podem ver a validade dos orçamentos e o limite de desconto.
2. O Administrador e o Gestor podem mudar essas regras:
   - validade do orçamento: de 1 a 365 dias (padrão: 30 dias);
   - desconto máximo sem autorização especial: de 0% a 100% (padrão: 5%).

## Bom saber

- **O preço fica travado na emissão.** Se a tabela de preço mudar depois, o orçamento emitido continua com o valor original.
- **Orçamento vencido não aceita decisão.** Depois da validade, o sistema não registra a aprovação. Duplique o plano e emita de novo para atualizar os preços.
- **Aprovação parcial é normal.** Os procedimentos recusados não voltam para o orçamento sozinhos. Se o paciente mudar de ideia depois, duplique o plano e emita um novo orçamento.
- **Rascunho é o único estado que aceita mudanças.** Depois de emitido, o orçamento só recebe a decisão do paciente ou cancelamento.
- **Procedimento realizado não é cancelado.** Ele fica registrado no atendimento em que foi feito.
- **O odontograma só muda pelo procedimento realizado.** Quando um procedimento é realizado, a marca de "a fazer" some e a marca de "feito" aparece no dente.
- **Leitura é registrada.** Cada vez que alguém abre um plano, a ação fica no histórico, por causa da LGPD.
- **Cobrança:** depois da aprovação, a recepção (ou o Administrador e o Gestor) parcela o orçamento (entrada e parcelas) pelo botão **Parcelar**, na tela do plano aprovado. As parcelas aparecem no [Financeiro](financeiro.md). Se um procedimento aprovado for cancelado depois, refaça o parcelamento.
- **Falta de material não barra o atendimento.** O procedimento é registrado mesmo com estoque insuficiente. O aviso mostra o que faltou. Confira o saldo no [Estoque](estoque.md).
- **Baixa automática no estoque.** Ela acontece só ao realizar o procedimento, nunca ao aprovar ou emitir o orçamento.

## Perguntas frequentes

**Posso mudar o preço de um orçamento que já foi emitido?**
Não. Duplique o plano e emita de novo. O novo orçamento usa a tabela de preço atual.

**O sistema não deixa emitir. Por quê?**
Ou o plano não tem procedimentos, ou algum procedimento não tem preço na tabela da clínica. A mensagem mostra qual é o caso e quais procedimentos estão sem preço.

**O paciente aprovou só uma parte. Como faço para aprovar o resto depois?**
Duplique o plano, inclua de novo os procedimentos que faltam e emita um novo orçamento.

**Quem pode dar um desconto maior do que o limite?**
Só o Administrador e o Gestor.

**Quanto tempo o orçamento vale?**
O padrão é 30 dias a partir da emissão. A clínica pode mudar esse prazo, de 1 a 365 dias.

**Posso realizar um procedimento que outro dentista está atendendo?**
Não. Só o dentista que está com o atendimento aberto registra o procedimento como realizado.

**Por que o botão "Realizado" está desligado?**
Você não tem um atendimento aberto com este paciente. Abra o atendimento na aba Atendimentos e tente de novo.

**O procedimento foi realizado, mas a tela mostrou falta de material. E agora?**
O procedimento já está registrado. Avise quem cuida do estoque da clínica para repor o material.
