---
modulo: painel
atualizado_em: c4e9fa2
---
# Painel do gestor

> Mostra, em um lugar só, como está a clínica hoje e no mês: quem vem às consultas, quanto entrou e o que ainda vai entrar, o que está atrasado, os orçamentos sem resposta e o estoque que precisa de atenção. Também mostra a cada dentista os próprios números.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Ver a visão geral da clínica inteira. Ver o próprio desempenho, como dentista. |
| Gestor | Ver a visão geral da clínica inteira. |
| Dentista | Ver só o próprio desempenho. |
| ASB | Não tem acesso ao painel. |
| Recepção | Não tem acesso ao painel. |

## O que dá para fazer

### Ver a visão geral da clínica
*Tela em construção.*

Administrador e Gestor veem os números da clínica inteira. Você pode escolher o mês. Se não escolher, o painel mostra o mês atual. O "hoje" do painel é o dia de hoje no fuso horário da clínica.

Cada bloco abaixo diz de onde vem o número.

#### Agenda de hoje
- Conta só as consultas que começam hoje. Bloqueios de horário não entram.
- Separa as consultas em: total, agendadas (ainda sem confirmação), confirmadas, atendidas, faltas e canceladas.
- Os números mudam conforme a recepção confirma e a equipe registra cada atendimento na [agenda](agenda.md).

#### Recebido e previsto no mês
- **Recebido:** soma dos pagamentos com data no mês, já descontados os estornos.
- **Recebido líquido:** o recebido menos as taxas de cartão.
- **Previsto:** soma do valor total das contas a receber com vencimento no mês. Contas canceladas não entram. O previsto não desconta o que já foi pago.

Por isso, recebido e previsto não se comparam diretamente. O previsto mostra quanto deveria entrar no mês. O recebido mostra quanto já entrou. Detalhes em [Financeiro](financeiro.md).

#### Contas a receber em atraso
- Conta as contas com vencimento antes de hoje que ainda têm saldo em aberto.
- O saldo é o valor da conta menos o que já foi pago.
- Mostra quantas contas são e quanto falta receber delas. Contas canceladas não entram.

#### Contas a pagar
- **Vencidas:** contas em aberto com vencimento antes de hoje. Mostra a quantidade e o valor cheio de cada conta.
- **Vencem nos próximos 7 dias:** contas em aberto com vencimento de hoje até daqui a 7 dias.
- Contas já pagas não entram.

#### Orçamentos aguardando resposta
- **Aguardando:** orçamentos emitidos que ainda não tiveram decisão. Veja o [plano de tratamento](tratamento.md).
- **Há mais de 7 dias:** parte dos aguardando que foi emitida há mais de 7 dias.
- **Emitidos no mês:** orçamentos emitidos com data no mês.
- **Aprovados no mês:** orçamentos decididos no mês com aprovação.
- **Valor aprovado no mês:** soma dos procedimentos aprovados desses orçamentos, pelo preço congelado no orçamento. Este valor **não** desconta o desconto dado no plano.

#### Estoque
- **Abaixo do mínimo:** materiais ativos com saldo abaixo do estoque mínimo cadastrado. Material sem mínimo não entra.
- **Lotes vencidos com saldo:** lotes com validade já passada e que ainda têm quantidade.
- **Lotes que vencem em até 30 dias:** lotes com saldo cuja validade cai entre hoje e os próximos 30 dias. Um lote que vence hoje entra aqui, não entre os vencidos. Lotes sem validade não entram.

Detalhes em [Estoque de materiais](estoque.md).

#### Produção por dentista
- Lista cada dentista com os procedimentos marcados como realizados no mês, pelo dentista que os realizou.
- **Procedimentos:** quantidade desses procedimentos.
- **Valor:** soma desses procedimentos pelo preço congelado no orçamento, já com o desconto do plano.
- A lista vai do maior para o menor valor.
- O nome pode aparecer em branco se a pessoa não tiver mais vínculo com a clínica.

Produção é o valor do que foi feito no mês. Não é o dinheiro que entrou. Para o dinheiro, veja o bloco de recebido.

### Ver o meu desempenho
*Tela em construção.*

Dentista e Administrador veem só os próprios números. Você também pode escolher o mês. Se não escolher, o painel mostra o mês atual.

- **Agenda de hoje:** suas consultas de hoje, com a mesma contagem da visão geral.
- **Atendimentos no mês:** quantos atendimentos você abriu no mês.
- **Produção no mês:** quantos procedimentos você realizou e o valor deles, já com o desconto do plano. Se não houve nenhum, aparece zero.
- **Orçamentos sob sua responsabilidade:** os mesmos números de orçamentos da visão geral, mas só dos planos em que você é o dentista responsável.
- **Último repasse fechado:** a data final do período e o total do último fechamento de repasse seu. Se ainda não houve fechamento, este item fica vazio. Veja [Repasse de dentistas](repasse.md).

## Bom saber

- **Só números, sem dados de paciente.** O painel não mostra o nome nem o histórico de nenhum paciente. Para ver um paciente, abra o [prontuário](prontuario.md), e esse acesso fica registrado.
- **Abrir o painel não gera registro no [histórico de ações](auditoria.md)**, porque ele não mostra dados individuais de paciente.
- **O painel só lê.** Ele não altera agenda, contas, orçamentos nem estoque.
- **Cada um vê o seu.** Dentista não vê os números dos outros dentistas nem da clínica inteira.
- **Cada clínica só vê os próprios números.**
- **Acompanhamento, não vigilância.** A equipe deve saber quais números são acompanhados pelo painel.
- **Os números são calculados no momento em que você abre o painel.**
- **Previsto (ainda não está no sistema):** metas de faturamento, pacientes para retorno, tratamentos parados, ocupação da agenda por dentista e por cadeira, faltas por paciente, conversão de orçamentos e ticket médio por dentista, pendências clínicas, repasse a pagar, margem por procedimento e comparativo entre unidades. Alertas por WhatsApp também ainda não existem.

## Perguntas frequentes

**Por que o recebido do mês é diferente do previsto?**
O recebido é o dinheiro que entrou no mês. O previsto é o valor total das contas com vencimento no mês, sem descontar o que já foi pago. Contas de meses anteriores que ainda estão em atraso não entram no previsto.

**Por que a produção e o valor aprovado de orçamentos têm valores diferentes?**
A produção já inclui o desconto do plano. O valor aprovado de orçamentos mostra o preço cheio dos procedimentos, antes do desconto.

**Por que o nome de um dentista aparece em branco na produção?**
A pessoa pode não ter mais vínculo com a clínica. O número continua valendo, só o nome não aparece.

**Por que um lote vencido não aparece nos lotes que vencem em breve?**
Lote vencido é aquele cuja validade já passou. Lote que vence hoje ainda não está vencido, por isso entra como "vence em breve".

**Por que eu não vejo "meu desempenho"?**
Esse item é para Dentista e Administrador. Gestor e outros perfis não veem.
