---
modulo: agenda
atualizado_em: 3afacea
---
# Agenda de consultas

> Organiza os horários dos dentistas e das cadeiras: marcar consultas, bloquear horários e registrar se o paciente veio, faltou ou cancelou.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Tudo o que a equipe faz, e também cadastra e gerencia as cadeiras. Pode ser escolhido como dentista de uma consulta. |
| Gestor | Tudo o que a equipe faz, e também cadastra e gerencia as cadeiras. |
| Dentista | Ver a agenda, marcar, remarcar, bloquear horários e mudar a situação das consultas. |
| ASB | Ver a agenda, marcar, remarcar, bloquear horários e mudar a situação das consultas. |
| Recepção | Ver a agenda, marcar, remarcar, bloquear horários e mudar a situação das consultas. |

Toda a equipe usa a agenda da mesma forma. Só o Administrador e o Gestor mexem nas cadeiras.

## O que dá para fazer

### Ver a agenda de um dia
Onde: menu **Agenda**.

1. A tela mostra um dia por vez, com uma coluna para cada dentista. A grade vai das 07:00 às 21:00.
2. Mude o dia com as setas **‹** e **›**, com o campo **Dia** ou com o botão **Hoje**.
3. Para ver a agenda de um dentista só, escolha o nome no campo **Dentista**. Para voltar a ver todos, escolha **Todos**.
4. As cores mostram a situação de cada consulta. Bloqueios aparecem em cinza, com a palavra **Bloqueado**. Cancelados aparecem riscados e mais apagados.

Para ver todas as consultas de um paciente, abra a ficha do paciente e a aba **Agenda** (veja "Marcar uma consulta").

*Tela em construção.* Ainda não é possível ver vários dias de uma vez (até 62 dias) nem filtrar por cadeira. Esconder os cancelados também ainda não tem botão na tela.

### Marcar uma consulta
Onde: menu **Agenda**, botão **+ Agendar** (no topo). Você também pode tocar num horário vazio da coluna do dentista, que já preenche o horário. Na ficha do paciente, na aba **Agenda**, o link **Agendar** abre o formulário com o paciente já escolhido.

1. Escolha o paciente. O paciente precisa estar ativo no cadastro.
2. Escolha o dentista. Toda consulta precisa de um dentista.
3. Escolha a cadeira. Esse passo é opcional. Só aparecem as cadeiras ativas.
4. Informe o dia, o início e a duração. Na tela, a duração vai de 15 minutos a 2 horas. O sistema aceita consultas de até 12 horas.
5. Se quiser, escreva o procedimento previsto (até 200 caracteres) e observações (até 1000 caracteres).
6. Toque em **Salvar**.

O sistema não marca a consulta se o dentista ou a cadeira já estiver ocupado naquele horário. A mensagem de erro diz com quem há conflito.

### Bloquear um horário
Use o bloqueio para deixar um horário indisponível, por exemplo almoço, férias ou manutenção de uma cadeira.

Onde: menu **Agenda**, botão **Bloquear horário** (no topo). O botão aparece para Administrador, Gestor, Dentista e Recepção.

1. Escolha o dentista, a cadeira ou os dois. Pelo menos um deles é obrigatório.
2. Informe o dia, o início e o fim. Na tela, o bloqueio fica dentro de um mesmo dia. O sistema aceita bloqueios de até 31 dias.
3. Se quiser, escreva o motivo (até 1000 caracteres).
4. Toque em **Salvar**.

Enquanto o bloqueio existir, nenhuma consulta pode ser marcada por cima dele.

### Remarcar ou alterar uma consulta
Onde: menu **Agenda**, toque no agendamento e depois em **Remarcar** (o botão aparece enquanto ele está agendado ou confirmado).

1. Abra o agendamento e toque em **Remarcar**.
2. Escolha o **Novo dia** e o **Novo horário**. A duração não muda.
3. Toque em **Salvar**.

Horário, dentista e cadeira só mudam enquanto o agendamento estiver agendado ou confirmado. Se ele estava confirmado, volta para agendado, porque a confirmação era do horário antigo. A mesma regra vale para bloqueios.

O paciente de um agendamento não muda. Para trocar o paciente, cancele e marque outra consulta. Um bloqueio precisa continuar com dentista ou cadeira.

*Tela em construção.* Trocar o dentista ou a cadeira de uma consulta, e alterar o procedimento ou as observações, ainda não tem tela. Hoje a tela só troca o dia e o horário. Bloqueios também não podem ser remarcados pela tela; por enquanto, cancele e crie outro.

### Confirmar, marcar atendimento, falta ou cancelamento
Onde: menu **Agenda**, toque no agendamento. Os botões de ação aparecem na janela que abre:

- **Confirmar**
- **Marcar atendido**
- **Faltou**
- **Cancelar**

Só aparecem as ações que valem para a situação atual da consulta. O campo **Motivo** fica logo acima dos botões.

A situação de uma consulta segue estas passagens:

- **Agendado** pode virar confirmado, atendido, falta ou cancelado.
- **Confirmado** pode virar atendido, falta ou cancelado.
- **Atendido**, **falta** e **cancelado** são finais. Não voltam para trás.

Você só marca **atendido** ou **falta** depois do horário de início da consulta.

Falta e cancelamento liberam o horário para outra marcação. Ao cancelar ou marcar falta, você pode escrever o motivo (até 300 caracteres).

Um bloqueio só pode ser cancelado. Na tela, ele só mostra o botão **Cancelar**.

**Iniciar atendimento.** Para Dentista e Administrador, a janela da consulta também tem o botão **Iniciar atendimento** (enquanto ela está agendada ou confirmada). Ele abre o atendimento desse paciente e leva você para a ficha, na aba **Atendimentos**. A consulta passa para **atendido** nesse momento.

### Ver o histórico de um agendamento
Ao abrir um agendamento, você vê os dados dele e a lista do que aconteceu com ele: criação, remarcações e mudanças de situação. Cada item mostra a data, a hora e quem fez a alteração.

*Tela em construção.*

### Cadastrar e gerenciar as cadeiras (Administrador e Gestor)
1. **Cadastrar:** dê um nome à cadeira (até 80 caracteres). Duas cadeiras não podem ter o mesmo nome.
2. **Renomear:** troque o nome de uma cadeira.
3. **Desativar:** só é possível se a cadeira não tiver agendamentos futuros. Remaneje esses agendamentos antes.
4. **Reativar:** volte a usar uma cadeira desativada.

Uma cadeira desativada não recebe novas consultas nem bloqueios. Na lista de cadeiras, ela aparece só se você pedir as inativas.

*Tela em construção.*

## Bom saber

- **Sem conflito de horário.** O sistema não deixa dois compromissos no mesmo horário para o mesmo dentista ou para a mesma cadeira. A mensagem diz com quem há conflito e em que horário.
- **Bloqueio só de cadeira.** A tela mostra cada dentista em uma coluna. Um bloqueio que tem só a cadeira, sem dentista, não aparece em nenhuma coluna por enquanto. Ele continua valendo: impede consultas naquela cadeira.
- **Quem pode ser dentista.** Só dentistas e o Administrador podem ser escolhidos como dentista de uma consulta.
- **Paciente inativo** não recebe consulta nova.
- **Nada é apagado.** Para desfazer uma marcação, cancele. O cancelamento fica registrado.
- **Nome social.** A agenda mostra o nome social do paciente quando ele existe.
- **Informações clínicas.** A agenda mostra nome do paciente, horário e procedimento previsto. Evite colocar informações clínicas nas observações.
- **Registro de ações.** Marcar, remarcar, bloquear e mudar a situação de uma consulta ficam no Histórico de ações, com quem fez e quando. Consultar a agenda não fica registrado.
- **Previsto:** confirmação e lembretes por WhatsApp e e-mail, e a visão da agenda por unidade da clínica.

## Perguntas frequentes

**Por que o sistema não deixou marcar o horário?**
Porque o dentista ou a cadeira já tem outro compromisso ou bloqueio naquele horário. A mensagem diz qual é.

**Posso apagar uma consulta?**
Não. Cancele a consulta. O cancelamento fica no histórico e libera o horário.

**O paciente faltou. Posso marcar a falta antes da hora?**
Não. A falta só pode ser marcada depois do horário de início.

**Remarquei uma consulta confirmada. Ela continua confirmada?**
Não. Ela volta para agendada, porque a confirmação era do horário antigo. Confirme de novo.

**Posso desfazer um cancelamento ou uma falta?**
Não. Atendido, falta e cancelado são finais. Marque uma nova consulta.

**Não vejo o botão Bloquear horário. Por quê?**
Ele aparece só para Administrador, Gestor, Dentista e Recepção. Se você é ASB, peça a um desses perfis para criar o bloqueio.
