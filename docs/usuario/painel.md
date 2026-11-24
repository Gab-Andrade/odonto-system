---
modulo: painel
atualizado_em: 3afacea
---
# Painel do gestor

> Mostra, em um lugar só, como está a clínica hoje e no mês: quem vem às consultas, quanto entrou e o que ainda vai entrar, o que está atrasado, os orçamentos sem resposta e o estoque que precisa de atenção. Compara cada mês com o anterior, mostra a equipe lado a lado, acompanha metas e mostra a cada dentista os próprios números.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Ver a visão geral da clínica inteira. Ver a equipe, as tendências e as metas. Ver o próprio desempenho, como dentista. |
| Gestor | Ver a visão geral da clínica inteira. Ver a equipe, as tendências e as metas. |
| Dentista | Ver só o próprio desempenho, inclusive a própria evolução mês a mês. |
| ASB | Não tem acesso ao painel. |
| Recepção | Não tem acesso ao painel. |

## O que dá para fazer

### Ver a visão geral da clínica
Onde: **Gestão**, aba **Visão geral**. Só Administrador e Gestor veem essa aba.

Administrador e Gestor veem os números da clínica inteira. Você pode escolher o mês no campo **Mês**, no topo da tela. Se não escolher, o painel mostra o mês atual. O "hoje" do painel é o dia de hoje no fuso horário da clínica.

Na tela **Início**, o cartão **Alertas** mostra o total de alertas ativos. Administrador e Gestor também veem um atalho para **Gestão**.

Cada bloco abaixo diz de onde vem o número.

#### Agenda de hoje
- Conta só as consultas que começam hoje. Bloqueios de horário não entram.
- Separa as consultas em: total, agendadas (ainda sem confirmação), confirmadas, atendidas, faltas e canceladas.
- Os números mudam conforme a recepção confirma e a equipe registra cada atendimento na [agenda](agenda.md).
- Na tela, aparece só o total de consultas de hoje. Ao passar o mouse sobre o indicador, aparecem as confirmadas e as sem confirmação.

#### Recebido e previsto no mês
- **Recebido:** soma dos pagamentos com data no mês, já descontados os estornos.
- **Recebido líquido:** o recebido menos as taxas de cartão. Ainda não aparece na tela.
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

#### Indicadores do mês e comparação com o mês anterior
Na visão geral aparecem só o recebido e o valor aprovado, com a variação. Os demais indicadores ficam na aba **Equipe** (por dentista) e na aba **Tendências** (mês a mês). Novos pacientes ainda não aparece em nenhuma tela de Gestão.

- **Recebido:** o mesmo número do bloco de recebido.
- **Produção:** valor dos procedimentos realizados no mês, com o desconto do plano.
- **Procedimentos:** quantidade de procedimentos realizados no mês.
- **Valor aprovado:** valor dos procedimentos aprovados em orçamentos decididos no mês, pelo preço cheio.
- **Orçamentos emitidos:** quantos foram emitidos no mês.
- **Conversão:** orçamentos aprovados dividido pelos decididos no mês, em porcentagem. Fica vazia se não houve decisão.
- **Ticket médio:** valor aprovado dividido pelo número de orçamentos aprovados. Fica vazio se nenhum foi aprovado.
- **Consultas:** consultas do mês, sem as canceladas.
- **Faltas e taxa de faltas:** faltas do mês, e a porcentagem delas sobre as consultas atendidas somadas às faltas. Fica vazia se não houve nenhuma consulta fechada.
- **Atendimentos:** atendimentos abertos no mês.
- **Novos pacientes:** pacientes cadastrados no mês.

Ao lado de cada número que pode ser comparado, o painel mostra a variação em porcentagem contra o mês anterior. Quando o mês anterior está zerado ou não existe, a variação fica vazia. Recebido e novos pacientes só aparecem na visão da clínica inteira.

#### Metas da clínica
- Mostra as metas da clínica para o mês e quanto já foi realizado até agora, em valor e em porcentagem.
- Metas são opcionais. Sem metas, o painel funciona normalmente.
- Para criar ou trocar uma meta, veja "Definir uma meta" abaixo.

#### Alertas ativos
- Mostra só a quantidade de alertas ativos, por tipo de regra.
- Para ver quais são os alertas e com quem eles se relacionam, use a tela **Alertas**, no menu.

### Ver a equipe lado a lado
Onde: **Gestão**, aba **Equipe**. Só Administrador e Gestor veem essa aba.

Administrador e Gestor veem, para o mês escolhido, uma linha por dentista. Cada linha mostra:
- os mesmos indicadores do mês (produção, procedimentos, atendimentos, conversão, ticket médio, consultas e faltas);
- as metas daquele dentista, com o realizado e a porcentagem.

Entram os dentistas e administradores ativos da clínica. Se um dentista saiu da clínica mas teve produção no mês, ele continua na lista, com o nome "(sem vínculo)".

Recebido e novos pacientes não aparecem por dentista, porque não são atribuídos a um profissional.

### Acompanhar a evolução mês a mês
Onde: **Gestão**, aba **Tendências** (Administrador e Gestor). O dentista vê a própria evolução em **Gestão**, aba **Meu desempenho**, logo abaixo dos números.

A tela mostra 6 meses, terminando no mês escolhido no campo **Mês** do topo. Para cada mês aparecem gráficos dos indicadores do mês, com a variação contra o mês anterior. O botão **Ver como tabela** mostra os mesmos números em tabela. Recebido aparece só na visão da clínica. Trocar a quantidade de meses ainda não está na tela.

- **Administrador e Gestor:** veem a clínica inteira. Também podem escolher um dentista no campo **Dentista** para ver a evolução só dele.
- **Dentista:** vê a própria evolução. Administrador também vê a própria, como dentista.

### Ver o meu desempenho
Onde: **Gestão**, aba **Meu desempenho**. Dentista e Administrador veem essa aba. Gestor não vê.

Dentista e Administrador veem só os próprios números. Você também pode escolher o mês no campo **Mês** do topo. Se não escolher, o painel mostra o mês atual.

- **Consultas hoje:** quantas consultas você tem hoje.
- **Atendimentos no mês:** quantos atendimentos você abriu no mês.
- **Produção no mês:** quantos procedimentos você realizou e o valor deles, já com o desconto do plano. Se não houve nenhum, aparece zero.
- **Orçamentos sob sua responsabilidade:** aguardando e aprovado no mês, só dos planos em que você é o dentista responsável.
- **Indicadores do mês e comparação:** só com os seus números. Na tela, aparecem produção, procedimentos e atendimentos, com a variação contra o mês anterior.
- **Evolução:** os últimos 6 meses, com os mesmos gráficos da aba Tendências (veja "Acompanhar a evolução mês a mês" acima).
- **Minhas metas:** as metas definidas para você no mês, com o realizado e a porcentagem.
- **Alertas:** quantos alertas ativos estão em casos sob sua responsabilidade.
- **Último repasse fechado:** a data final do período e o total do último fechamento de repasse seu. Se ainda não houve fechamento, este item fica vazio. Veja [Repasse de dentistas](repasse.md).

### Definir uma meta
Onde: **Gestão**, aba **Metas**, bloco **Definir meta**. Só Administrador e Gestor. O mês é o do campo **Mês** do topo.

Administrador e Gestor podem criar uma meta ou trocar o valor de uma meta que já existe. Cada mês tem, no máximo, uma meta por indicador para a clínica e uma por indicador para cada dentista.

1. Confira o mês no topo da tela.
2. Escolha o indicador: **recebido**, **produção**, **procedimentos** ou **aprovado** (na tela, aparecem como Recebido, Produção, Procedimentos e Valor aprovado).
3. Escolha o dentista em **De quem**, ou deixe em **Clínica** para a meta da clínica.
4. Informe o valor em **Valor (R$)**. Para procedimentos, informe a **Quantidade**. O valor precisa ser maior que zero.
5. Clique em **Salvar meta**.

Regras:
- Meta de **recebido** é só da clínica. Recebimento não é atribuído a dentista.
- Meta de **procedimentos** é um número inteiro, sem casas decimais.
- O dentista escolhido precisa estar ativo na clínica.
- O mês precisa estar entre os anos de 2000 e 2100.
- Se já existir meta para o mesmo mês, indicador e dentista, o valor é substituído.

### Apagar uma meta
Onde: **Gestão**, aba **Metas**, na lista **Metas do mês**, botão **Remover** ao lado da meta.

Administrador e Gestor podem apagar uma meta. O painel deixa de mostrar o progresso dela. Os números do mês continuam iguais.

## Bom saber

- **Só números, sem dados de paciente.** O painel não mostra o nome nem o histórico de nenhum paciente. Para ver um paciente, abra o [prontuário](prontuario.md), e esse acesso fica registrado.
- **Abrir o painel não gera registro no [histórico de ações](auditoria.md)**, porque ele não mostra dados individuais de paciente.
- **Metas ficam registradas.** Criar, trocar ou apagar uma meta gera registro no [histórico de ações](auditoria.md), com quem fez e quando.
- **O painel só lê.** Ele não altera agenda, contas, orçamentos nem estoque. A única coisa que o painel grava são as metas.
- **Cada um vê o seu.** Dentista não vê os números dos outros dentistas nem da clínica inteira.
- **Cada clínica só vê os próprios números.**
- **Acompanhamento, não vigilância.** A equipe deve saber quais números são acompanhados pelo painel.
- **Os números são calculados no momento em que você abre o painel.**
- **Previsto (ainda não está no sistema):** pacientes para retorno, tratamentos parados, ocupação da agenda por dentista e por cadeira, pendências clínicas (evoluções sem assinatura e prontuários incompletos), repasse a pagar no período, margem por procedimento e por dentista, tempo real × tempo previsto por procedimento, e comparativo entre unidades. Alertas por WhatsApp também ainda não existem.

## Perguntas frequentes

**Por que o recebido do mês é diferente do previsto?**
O recebido é o dinheiro que entrou no mês. O previsto é o valor total das contas com vencimento no mês, sem descontar o que já foi pago. Contas de meses anteriores que ainda estão em atraso não entram no previsto.

**Por que a produção e o valor aprovado de orçamentos têm valores diferentes?**
A produção já inclui o desconto do plano. O valor aprovado de orçamentos mostra o preço cheio dos procedimentos, antes do desconto.

**Por que o nome de um dentista aparece em branco na produção?**
A pessoa pode não ter mais vínculo com a clínica. O número continua valendo, só o nome não aparece. Na equipe, o nome aparece como "(sem vínculo)".

**Por que um lote vencido não aparece nos lotes que vencem em breve?**
Lote vencido é aquele cuja validade já passou. Lote que vence hoje ainda não está vencido, por isso entra como "vence em breve".

**Por que a variação de um indicador aparece vazia?**
Ela fica vazia quando o mês anterior está zerado ou não existe. Sem base de comparação, o painel não calcula a porcentagem.

**Por que eu não consigo definir uma meta?**
Metas são de Administrador e Gestor. Se a mensagem disser que o dentista não foi encontrado, confira se ele está ativo na clínica. Meta de recebido não aceita dentista.

**Por que eu não vejo "meu desempenho"?**
Esse item é para Dentista e Administrador. Gestor e outros perfis não veem.
