---
modulo: inteligencia
atualizado_em: 3afacea
---
# Alertas da clínica

> Mostra os pacientes que pedem atenção, sem você precisar procurar: retornos atrasados, orçamentos parados, faltas repetidas, atendimentos abertos e contas em atraso. Você também pode esconder um alerta por um tempo e ajustar as regras da clínica.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Ver os alertas de todas as regras, dispensar e voltar a mostrar alertas, e ligar, desligar ou ajustar as regras |
| Gestor | Igual ao Administrador |
| Dentista | Ver e dispensar os alertas clínicos: profilaxia, canal, orçamentos, atendimento aberto e faltas. Não vê contas em atraso |
| ASB | Ver e dispensar os alertas de profilaxia, canal, orçamentos e faltas. Não vê atendimento aberto nem contas em atraso |
| Recepção | Ver e dispensar os alertas de profilaxia, orçamentos, faltas e contas em atraso. Não vê alertas de canal nem de atendimento aberto |

Todos os perfis podem ver a lista de regras. Só o Administrador e o Gestor podem alterá-las.

## O que dá para fazer

### Ver os alertas

O sistema mostra os alertas do seu perfil, do mais grave para o menos grave. Cada alerta traz:

- o paciente, com nome e telefone;
- o dentista responsável, quando houver;
- a data do fato que originou o alerta;
- uma explicação curta, por exemplo "Dente 16, realizado em 03/03/2026, sem retorno".

Você pode filtrar a lista por regra: escolha uma no campo **Regra** (o padrão é *Todas*). Dentista e Administrador veem também **Só meus pacientes**, que mostra só os alertas dos seus pacientes. Filtrar por paciente ainda não tem campo na tela. *Tela em construção.* Por padrão, os alertas escondidos não aparecem: marque **Mostrar dispensados** para vê-los.

Onde: menu **Alertas**, no topo da lista.

### Ver só as contagens

O sistema mostra o total de alertas que pedem atenção. Essa visão não mostra nomes de pacientes.

Onde: cartão **Alertas** na tela **Início** (o botão **Ver todos** leva à lista). Na **Gestão**, um aviso mostra o total e leva à lista.

A contagem por regra e o filtro por dentista ainda não aparecem na tela. *Tela em construção.*

### Esconder um alerta por um tempo

1. Clique em **Dispensar** no alerta.
2. Informe até quando quer escondê-lo. Se não informar, são 30 dias. O máximo é 365 dias.
3. Se quiser, escreva o motivo (até 300 caracteres).

O alerta sai da lista. Depois da data, ele volta sozinho se a situação continuar.

Onde: menu **Alertas**, botão **Dispensar** em cada alerta. A janela **Dispensar alerta** tem os campos **Voltar a mostrar em** (vazio = 30 dias) e **Motivo**.

### Voltar a mostrar um alerta escondido

1. Marque **Mostrar dispensados** para ver os alertas escondidos.
2. Clique em **Voltar a mostrar** no alerta.

O alerta volta à lista na hora.

Onde: menu **Alertas**, opção **Mostrar dispensados** e botão **Voltar a mostrar** em cada alerta escondido.

### Conhecer as regras e seus números

Todos os perfis veem o nome das regras no filtro **Regra**. A lista completa, com a descrição e os números em uso de cada regra, é vista por Gestor e Administrador. A tabela abaixo traz os valores padrão.

| Regra | Quando aparece | Padrão | Valores aceitos | Quem recebe | Gravidade |
|---|---|---|---|---|---|
| Profilaxia atrasada | Paciente ativo cuja última profilaxia registrada foi há mais de N meses, e sem consulta marcada para o futuro. Quem nunca fez profilaxia no sistema não entra | 6 meses. Termos: "profilaxia", "limpeza" | 1 a 36 meses | Todos | Média |
| Tratamento de canal sem retorno | Canal feito há mais de N dias, sem atendimento depois dele e sem consulta marcada. Vale o dente marcado como canal no odontograma ou o procedimento com um dos termos | 30 dias. Termos: "canal", "endodont" | 1 a 365 dias | Administrador, Gestor, Dentista, ASB | Alta |
| Orçamento aprovado sem agendamento | Orçamento aprovado há mais de N dias, com procedimentos ainda por fazer e sem consulta marcada | 7 dias | 0 a 365 dias | Todos | Média |
| Orçamento sem resposta | Orçamento emitido há mais de N dias, ainda dentro da validade, sem decisão do paciente | 7 dias | 1 a 365 dias | Todos | Baixa |
| Atendimento aberto há muito tempo | Atendimento iniciado há mais de N dias e ainda não fechado | 1 dia | 1 a 90 dias | Administrador, Gestor, Dentista | Média |
| Faltas repetidas | Paciente com N faltas ou mais nos últimos D dias | 2 faltas em 180 dias | 1 a 20 faltas; 7 a 730 dias | Todos | Baixa |
| Conta a receber em atraso | Parcelas vencidas há mais de N dias, com saldo em aberto | 1 dia | 0 a 365 dias | Administrador, Gestor, Recepção | Média |

Onde: menu **Alertas**, botão **Configurar regras**. Só aparece para Gestor e Administrador.

### Ligar, desligar ou ajustar uma regra

1. Escolha a regra.
2. Ligue ou desligue a regra.
3. Se quiser, mude os números.
4. Clique em **Salvar** na própria regra.

Ao salvar, os números que você não informar voltam ao padrão. Para mudar um número sem perder os outros, mantenha os demais como estão. A mudança vale para toda a clínica e começa a valer na próxima vez que a lista for vista.

Onde: menu **Alertas**, botão **Configurar regras**, na janela **Regras de alerta**. Cada regra tem a caixa para ligar ou desligar, os campos de número e o seu botão **Salvar**.

## Bom saber

- **Os alertas não ficam guardados.** Eles são calculados na hora, a partir do que já está no sistema. Quando a situação se resolve (consulta marcada, pagamento feito, atendimento fechado), o alerta some sozinho.
- **Esconder não resolve.** Um alerta escondido só sai da lista até a data. Se o problema continuar, ele volta.
- **Você só mexe nos alertas que recebe.** Não dá para esconder um alerta de uma regra que o seu perfil não vê.
- **Os alertas são ordenados pela gravidade.** Alta vem primeiro, depois média e depois baixa.
- **O filtro por dentista tem limite.** Ele mostra só os alertas com dentista responsável. Faltas e contas em atraso não têm dentista e não aparecem nesse filtro.
- **Cadastro desativado.** Na maioria dos alertas, pacientes com cadastro desativado não aparecem. A exceção é a conta em atraso: a dívida continua aparecendo.
- **Termos.** Os termos são palavras procuradas no código ou na descrição do procedimento. A clínica pode ter até 10 termos, com até 40 letras cada um. Não há diferença entre maiúsculas e minúsculas.
- **Tudo fica registrado.** Ligar, desligar ou mudar uma regra, esconder e voltar a mostrar um alerta ficam no Histórico de ações. Cada consulta à lista também fica registrada, com a quantidade de alertas que apareceram, mas sem os nomes dos pacientes.
- **Privacidade.** A lista traz nome e telefone do paciente, por isso só quem recebe a regra a vê. Cada clínica só vê os próprios alertas.
- **Previsto, ainda não existe:**
  - envio dos alertas por WhatsApp e e-mail (em stand-by; hoje o sistema não envia nada sozinho);
  - previsão de faltas e de abandono de tratamento, em fase posterior, quando houver dados acumulados.

## Perguntas frequentes

**Um paciente sumiu da lista. O que aconteceu?**
Pode ser que a situação foi resolvida (consulta marcada, pagamento feito, atendimento fechado), que alguém escondeu o alerta, ou que a regra foi desligada. Confira no Histórico de ações.

**Escondi um alerta sem querer. Como desfaço?**
Volte a mostrar o alerta. Ele aparece de novo na hora.

**Por que eu não vejo alertas de contas em atraso?**
Essa regra é só para Administrador, Gestor e Recepção.

**Posso ter um prazo diferente para cada dentista?**
Não. Cada regra tem uma configuração só, que vale para a clínica inteira.

**Vou receber aviso no WhatsApp quando um alerta aparecer?**
Ainda não. O envio por WhatsApp e e-mail está previsto, mas em stand-by.
