---
modulo: financeiro
atualizado_em: 30ed9b3
---
# Financeiro

> Aqui a recepção transforma o orçamento aprovado em parcelas, registra o que o paciente paga e consulta o extrato de cada paciente. A gestão corrige erros, cancela contas e controla o que a clínica tem a pagar.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Tudo o que a Recepção faz, além de estornar recebimentos, cancelar contas e parcelamentos, e cuidar das contas a pagar |
| Gestor | Tudo o que a Recepção faz, além de estornar recebimentos, cancelar contas e parcelamentos, e cuidar das contas a pagar |
| Dentista | Não acessa o financeiro |
| ASB | Não acessa o financeiro |
| Recepção | Parcelar orçamento aprovado, cobrar conta avulsa, registrar recebimentos, ver as contas a receber e o extrato do paciente |

## O que dá para fazer

### Parcelar um orçamento aprovado
*Tela em construção.*

1. Só é possível parcelar orçamento aprovado (ou concluído). Os valores vêm do orçamento, já com o desconto aplicado.
2. Informe a entrada, se houver. A entrada pode ser zero, mas não pode ser maior que o total.
3. Informe a quantidade de parcelas, de 1 a 48. Se a entrada cobrir o total, não há parcelas.
4. A data da entrada é hoje, se você não informar outra. A primeira parcela vence um mês depois da entrada, se você não informar outra data. A primeira parcela não pode vencer antes da entrada.
5. As parcelas seguintes vencem todo mês, no mesmo dia. Quando o mês não tem esse dia, a parcela vence no último dia do mês. Por exemplo, um vencimento no dia 31 passa para o dia 30 ou para o último dia de fevereiro.
6. Os centavos que sobram da divisão entram na primeira parcela, para a soma bater com o total.
7. Cada parcela vira uma conta a receber, com o nome "entrada" ou "parcela 1 de 3", por exemplo.
8. Um orçamento só pode ser parcelado uma vez. Para refazer o parcelamento, cancele o atual antes (veja "Cancelar uma conta ou o parcelamento").

### Cobrar uma conta avulsa
*Tela em construção.*

1. Use para cobrar algo que não está em um orçamento.
2. Escolha o paciente, escreva a descrição (até 200 caracteres), informe a data de vencimento e o valor. O valor precisa ser maior que zero.

### Registrar um recebimento
*Tela em construção.*

1. Abra a conta a receber. Contas canceladas não recebem pagamento.
2. Informe o valor recebido e a forma de pagamento (dinheiro, Pix, cartão de débito, cartão de crédito, boleto ou transferência). O valor não pode passar do saldo da conta.
3. Se houver taxa de cartão ou de boleto, informe a porcentagem, de 0% a 100%. Se não informar, a taxa é zero.
4. O sistema guarda a taxa e calcula o valor líquido (o que sobra depois da taxa). A taxa não diminui o que o paciente deve: o saldo cai pelo valor total recebido.
5. A data do recebimento é hoje, se você não informar outra. Não é possível colocar data futura.
6. Você pode escrever uma observação, de até 300 caracteres.
7. Pagamento parcial é aceito. A conta fica como "parcial" até ser quitada.

### Estornar um recebimento
*Tela em construção.*

1. Só o Administrador e o Gestor podem estornar.
2. Informe o motivo, de até 300 caracteres.
3. O estorno aparece como um lançamento negativo, com a mesma forma de pagamento, o mesmo valor e a mesma taxa. O recebimento original continua registrado.
4. Não é possível estornar um estorno, nem estornar o mesmo recebimento duas vezes.
5. Depois do estorno, o saldo da conta volta ao valor anterior. Assim, você pode registrar o recebimento de novo, se for o caso.

### Cancelar uma conta ou o parcelamento
*Tela em construção.*

1. Só o Administrador e o Gestor podem cancelar.
2. Informe o motivo.
3. Só é possível cancelar a conta se ela não tiver recebimento. Se tiver, estorne os recebimentos antes.
4. Para cancelar o parcelamento de um orçamento, o sistema cancela todas as parcelas de uma vez. A mesma regra vale: nenhuma parcela pode ter recebimento.
5. Contas canceladas saem da lista normal. Para vê-las, peça para incluir as canceladas. Elas também não entram no total do extrato.

### Ver as contas a receber
*Tela em construção.*

1. Filtre por paciente, por período de vencimento e, se quiser, inclua as canceladas.
2. A lista mostra, no máximo, 200 contas por vez. O limite máximo é de 500.
3. Cada conta aparece com uma situação:
   - **aberta**: ainda não recebeu nada e não venceu;
   - **parcial**: já recebeu parte do valor;
   - **paga**: quitada;
   - **vencida**: passou do vencimento e não está quitada, mesmo que já tenha pago uma parte;
   - **cancelada**: foi cancelada.

### Ver o extrato do paciente
*Tela em construção.*

1. O extrato reúne, para um paciente, as contas e os recebimentos.
2. Ele mostra quatro valores:
   - **total cobrado**: soma das contas, sem as canceladas;
   - **total recebido**: soma dos recebimentos, já descontados os estornos;
   - **saldo a pagar**: total cobrado menos total recebido;
   - **em atraso**: soma do saldo das contas vencidas.
3. Cada consulta ao extrato fica registrada no histórico de ações, por causa da LGPD.

### Registrar uma conta a pagar
*Tela em construção.*

1. Só o Administrador e o Gestor podem usar as contas a pagar.
2. Informe o fornecedor (obrigatório, até 150 caracteres).
3. Você pode informar a categoria (até 80 caracteres) e uma descrição (até 300 caracteres).
4. Informe a data de vencimento e o valor, maior que zero.

### Pagar uma conta a pagar
*Tela em construção.*

1. Só é possível pagar conta que esteja em aberto.
2. Informe a forma de pagamento.
3. A data do pagamento é hoje, se você não informar outra. Não é possível colocar data futura.

### Cancelar uma conta a pagar
*Tela em construção.*

1. Só é possível cancelar conta que esteja em aberto. Conta já paga não pode ser cancelada.
2. Informe o motivo.

### Ver as contas a pagar
*Tela em construção.*

1. Filtre por período de vencimento e por situação.
2. A lista mostra, no máximo, 200 contas por vez. O limite máximo é de 500.
3. Uma conta em aberto com vencimento anterior a hoje aparece marcada como vencida.

## Bom saber

- **O registro é manual.** O sistema não se conecta a bancos. Tudo o que entra ou sai é lançado por alguém da equipe.
- **Nada é apagado.** Para corrigir um recebimento, use o estorno. Para desfazer uma conta, use o cancelamento. Tudo fica registrado no histórico de ações, com quem fez e quando.
- **Valor não passa do saldo.** O sistema não aceita recebimento maior que o que falta pagar na conta.
- **A taxa não muda o saldo do paciente.** A taxa só fica registrada, para a clínica saber quanto realmente entrou.
- **A Recepção não vê as contas a pagar.** Esse controle fica com o Administrador e o Gestor.
- **Dentista e ASB não acessam o financeiro.**
- **Repasse:** o que o paciente paga aqui é a base do [repasse dos dentistas](repasse.md). A produção do dentista no painel de gestão ainda está prevista.

## Perguntas frequentes

**Por que o sistema não deixa parcelar o orçamento?**
Pode ser que o orçamento ainda não esteja aprovado, que já tenha um parcelamento ativo ou que a entrada seja maior que o total. A mensagem na tela mostra o motivo.

**O paciente pagou mais do que a conta. Como registro?**
Não é possível. O recebimento não pode passar do saldo. Registre só o que falta e, se for o caso, cobre o restante em outra conta avulsa.

**Errei o valor de um recebimento. Como corrijo?**
O Administrador ou o Gestor estorna o recebimento, com um motivo. Depois, a Recepção registra o valor certo.

**Posso cancelar uma conta que já foi paga?**
Não diretamente. Primeiro estorne os recebimentos dessa conta. Depois, cancele a conta.

**Por que a conta aparece como vencida, se o paciente já pagou uma parte?**
Porque a conta venceu e ainda não está quitada. Quando o saldo for zerado, ela passa para "paga".

**A taxa do cartão diminui o que o paciente deve?**
Não. A taxa só reduz o valor que sobra para a clínica. O saldo do paciente cai pelo valor total que ele pagou.

**Quem pode estornar um recebimento?**
Só o Administrador e o Gestor.
