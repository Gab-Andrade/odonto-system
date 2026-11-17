---
modulo: repasse
atualizado_em: 89d842f
---
# Repasse de dentistas

> Aqui a gestão define quanto cada dentista recebe sobre o que os pacientes pagaram pelos procedimentos que ele realizou, confere a prévia e fecha o repasse até uma data. O dentista acompanha o próprio repasse.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Cadastrar as regras de repasse de cada dentista, ver a prévia de qualquer dentista, fechar o repasse e consultar os fechamentos de todos |
| Gestor | Tudo o que o Administrador faz neste módulo |
| Dentista | Ver as próprias regras, a própria prévia e os próprios fechamentos. Não vê o repasse de outros dentistas |

Recepção e ASB não acessam o repasse.

## O que dá para fazer

### Cadastrar a regra de repasse de um dentista
*Tela em construção.*

1. Escolha o dentista.
2. Escolha o tipo de regra:
   - **percentual**: uma porcentagem, de 0% a 100%, do valor que o paciente pagou;
   - **valor fixo**: um valor em reais por procedimento.
3. Escolha o alcance da regra:
   - **geral**: vale para todos os procedimentos desse dentista;
   - **específica**: vale só para um procedimento, pelo código dele.
4. Se for percentual, marque se o repasse desconta a taxa do cartão e/ou o custo dos materiais usados. No valor fixo, esses descontos não se aplicam.
5. Informe a data de início da regra. Se você não informar, ela vale a partir de hoje.
6. Salve. A regra fica registrada no histórico de ações, com quem cadastrou e quando.

### Ver a prévia do repasse
*Tela em construção.*

1. Escolha o dentista e a data até a qual quer calcular. O dentista não escolhe nada: a prévia é sempre a dele.
2. O sistema mostra:
   - desde quando o repasse está sendo contado;
   - o total a receber;
   - cada procedimento, com o valor já pago pelo paciente, os descontos e a comissão;
   - a lista de procedimentos realizados que estão sem regra de repasse.
3. A prévia não grava nada. Você pode consultá-la quantas vezes quiser.

### Fechar o repasse de um dentista
*Tela em construção.*

1. Escolha o dentista e a data até a qual o repasse será fechado. A data não pode ser futura: o máximo é hoje.
2. A data precisa ser posterior ao último fechamento desse dentista. Se já houver fechamento até essa data ou depois, o sistema recusa e mostra até quando já foi fechado.
3. Se quiser, escreva uma observação, de até 300 caracteres.
4. O sistema calcula o repasse, grava o fechamento com cada procedimento e registra a ação no histórico.
5. O fechamento paga só a diferença em relação ao que já foi fechado antes. Nada é pago duas vezes.

### Consultar os fechamentos
*Tela em construção.*

1. O Administrador e o Gestor veem os fechamentos de todos os dentistas, ou de um dentista escolhido.
2. O Dentista vê só os próprios fechamentos.
3. Cada fechamento mostra o período (de quando a quando), o total, a observação, quem fechou e quando, e a lista de procedimentos com valor recebido, descontos e comissão.

## Bom saber

- **O repasse segue o que o paciente pagou.** O cálculo usa o valor que o paciente já pagou de cada procedimento, não o valor do orçamento. Se o paciente pagou metade, o dentista recebe sobre a metade.
- **Só procedimentos realizados pelo dentista.** Entram os procedimentos que o dentista marcou como realizados no plano de tratamento.
- **O desconto do plano conta.** O valor usado é o do procedimento já com o desconto dado no plano de tratamento.
- **Cada fechamento paga só a diferença.** Exemplo, com um único procedimento de R$ 200 e regra de 50%: se até o primeiro fechamento o paciente pagou R$ 100, esse fechamento paga R$ 50. Quando o paciente pagar o restante, o fechamento seguinte paga os outros R$ 50.
- **Taxa do cartão.** Se a regra desconta a taxa, entra a parte da taxa referente ao que foi pago, antes do cálculo da porcentagem.
- **Materiais.** Se a regra desconta materiais, entra o custo dos materiais usados no procedimento, na mesma proporção do que foi pago, pelo custo dos lotes usados.
- **Valor fixo.** O dentista recebe o valor combinado por procedimento, na mesma proporção do que foi pago. Não há descontos de taxa nem de materiais.
- **Regra específica tem prioridade.** Se houver regra própria para o procedimento em vigor no dia em que ele foi feito, ela vale. Senão, vale a regra geral do dentista.
- **A data da regra vale para o dia do procedimento.** Cada procedimento usa a regra que estava em vigor no dia em que foi realizado. Para valer para procedimentos já feitos, a data de início precisa ser anterior a eles.
- **Procedimento sem regra fica de fora.** Ele aparece na lista de sem regra da prévia e não entra no fechamento. Quando houver regra que cubra o dia em que foi feito, ele entra no próximo fechamento.
- **Regra não se edita.** Para mudar uma regra, cadastre outra com a nova data de início. O que já foi fechado não muda.
- **Fechamento não se apaga.** O sistema não oferece como apagar nem alterar um fechamento. Confira a prévia antes de fechar.
- **Dias pelo horário da clínica.** O dia de cada procedimento e de cada pagamento é contado pelo horário da clínica.
- **Tudo fica registrado.** Cada regra cadastrada e cada fechamento vão para o histórico de ações, com quem fez e quando.
- **Previsto:** importar as regras de repasse de uma planilha, como na precificação. Ainda não está disponível.

## Perguntas frequentes

**Por que um procedimento não aparece no repasse?**
Pode ser que o paciente ainda não tenha pago nada dele até a data escolhida, que o procedimento não esteja marcado como realizado pelo dentista, ou que não exista regra em vigor no dia em que ele foi feito. No último caso, ele aparece na lista de sem regra da prévia.

**Cadastrei a regra hoje, mas ela não vale para um procedimento da semana passada. Por quê?**
A data de início padrão é hoje, e cada procedimento usa a regra em vigor no dia em que foi feito. Cadastre a regra com uma data de início anterior ao procedimento. Procedimentos que ficaram de fora de um fechamento entram no próximo, desde que tenham regra.

**Posso fechar o repasse até amanhã?**
Não. O fechamento pode ir até hoje, no máximo.

**O valor da prévia mudou. Por quê?**
Pode ser que tenham sido registrados pagamentos com data até a data escolhida, ou que uma regra nova com data de início anterior passe a valer para procedimentos antigos.

**Posso corrigir um fechamento errado?**
Não pelo sistema: não há como apagar nem alterar um fechamento. Por isso, confira a prévia antes de fechar.

**O dentista consegue ver o repasse de outro dentista?**
Não. O dentista vê só as próprias regras, a própria prévia e os próprios fechamentos.
