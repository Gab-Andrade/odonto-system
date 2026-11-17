---
modulo: tratamento
atualizado_em: f320bfa
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
*Tela em construção.*

1. Escolha o paciente. O paciente precisa estar ativo no cadastro.
2. Informe o dentista responsável. Se não informar, o responsável é quem está criando o plano.
3. Dê um título e observações, se quiser.
4. Inclua os procedimentos. Para cada um, informe o código do procedimento e, se quiser, o dente (numeração FDI), as faces (por exemplo, "MOD") e observações.
5. Se quiser que o procedimento apareça no odontograma, escolha o item da legenda que indica "a fazer" e o item que indica "feito". Isso só funciona com dente informado.
6. Para cada procedimento, o sistema mostra o preço que seria cobrado hoje. Se a clínica não tiver preço para ele, o sistema mostra o motivo.

### Editar um rascunho
*Tela em construção.*

1. Só é possível mudar um plano enquanto ele estiver em **rascunho**.
2. Você pode trocar o título, as observações e o dentista responsável.
3. Você pode incluir, trocar ou tirar procedimentos e mudar a ordem deles.
4. Depois de emitido, o plano não muda. Para alterar um orçamento emitido, use "duplicar" (veja abaixo).

### Dar desconto
*Tela em construção.*

1. Informe o desconto em porcentagem, de 0% a 100%.
2. Até o limite da clínica, o Dentista e a Recepção podem dar o desconto. Acima do limite, só o Administrador ou o Gestor.
3. O desconto vale sobre os procedimentos aprovados e realizados. Os recusados e os cancelados não entram no cálculo.
4. Só é possível dar desconto enquanto o plano estiver em rascunho.

### Emitir o orçamento
*Tela em construção.*

1. Antes de emitir, o plano precisa ter ao menos um procedimento.
2. Todos os procedimentos precisam ter preço. Se algum não tiver, o sistema lista quais são e não emite nada.
3. Ao emitir, o sistema guarda o preço de cada procedimento e o desconto. Esses valores não mudam mais, mesmo que a tabela de preço da clínica mude depois.
4. A validade do orçamento é contada a partir do dia da emissão. O padrão é 30 dias.
5. Depois de emitido, o orçamento pode receber a decisão do paciente.

### Registrar a decisão do paciente
*Tela em construção.*

1. Com o paciente, marque quais procedimentos ele aprovou. Os que ficarem de fora são marcados como recusados.
2. Você pode aprovar só uma parte do orçamento.
3. Se ao menos um procedimento for aprovado, o orçamento fica como "aprovado". Se nenhum for, fica como "recusado".
4. A decisão só pode ser registrada enquanto o orçamento estiver emitido e dentro da validade.

### Realizar um procedimento no atendimento
*Tela em construção.*

1. Abra o atendimento do paciente. O atendimento precisa estar aberto.
2. Escolha o procedimento aprovado e informe o atendimento em que ele foi feito.
3. Só o dentista que está com esse atendimento aberto pode registrar o procedimento como realizado.
4. Se o procedimento estiver ligado a um dente no odontograma, o sistema tira a marca de "a fazer" e marca "feito" no dente, dentro do mesmo atendimento.
5. Quando todos os procedimentos aprovados forem realizados ou cancelados, e ao menos um tiver sido realizado, o plano fica como "concluído". Se todos forem cancelados sem nenhum realizado, o plano fica como "cancelado".

### Cancelar um plano
*Tela em construção.*

1. Só é possível cancelar planos em rascunho ou emitidos.
2. Informe o motivo, com até 300 caracteres.
3. Um plano já aprovado não é cancelado de uma vez. Cancele os procedimentos um a um.

### Cancelar um procedimento aprovado
*Tela em construção.*

1. Só é possível cancelar procedimentos que foram aprovados e ainda não foram realizados.
2. Informe o motivo, com até 300 caracteres.

### Duplicar um plano
*Tela em construção.*

1. O sistema cria um novo rascunho com os mesmos procedimentos, o mesmo dentista, o mesmo título e as mesmas observações.
2. Use para refazer um orçamento vencido, um orçamento recusado ou para atualizar os preços.
3. O rascunho novo começa sem preço congelado, sem decisão do paciente e **sem desconto**. Informe o desconto de novo, se for o caso.

### Ver os planos de um paciente
*Tela em construção.*

1. Veja a lista de planos do paciente, do mais recente para o mais antigo.
2. Abra um plano para ver os procedimentos, o preço de cada um e os totais: valor proposto, valor aprovado antes do desconto, desconto e valor final aprovado.
3. Todo plano aberto fica registrado no histórico de ações.

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
- **Cobrança:** depois da aprovação, a recepção parcela o orçamento (entrada e parcelas) no [Financeiro](financeiro.md). Se um procedimento aprovado for cancelado depois, refaça o parcelamento.

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
