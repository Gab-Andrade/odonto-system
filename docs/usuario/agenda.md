---
modulo: agenda
atualizado_em: 47b3794
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

### Ver a agenda de um período
1. Escolha a data e a hora de início e de fim. O período pode ter no máximo 62 dias.
2. Se quiser, filtre por dentista, por cadeira ou por paciente.
3. Por padrão, a lista mostra também os cancelados. Você pode escondê-los.

Para ver todas as consultas de um paciente, filtre só pelo paciente, sem período.

*Tela em construção.*

### Marcar uma consulta
1. Escolha o paciente. O paciente precisa estar ativo no cadastro.
2. Escolha o dentista. Toda consulta precisa de um dentista.
3. Escolha a cadeira. Esse passo é opcional.
4. Informe o início e o fim. Uma consulta dura no máximo 12 horas.
5. Se quiser, escreva o procedimento previsto (até 200 caracteres) e observações (até 1000 caracteres).

O sistema não marca a consulta se o dentista ou a cadeira já estiver ocupado naquele horário.

*Tela em construção.*

### Bloquear um horário
Use o bloqueio para deixar um horário indisponível, por exemplo almoço, férias ou manutenção de uma cadeira.

1. Escolha o dentista, a cadeira ou os dois. Pelo menos um deles é obrigatório.
2. Informe o início e o fim. Um bloqueio pode durar até 31 dias.
3. Se quiser, escreva observações (até 1000 caracteres).

Enquanto o bloqueio existir, nenhuma consulta pode ser marcada por cima dele.

*Tela em construção.*

### Remarcar ou alterar uma consulta
1. Abra o agendamento.
2. Mude o horário, o dentista ou a cadeira. Ou altere o procedimento ou as observações.

Horário, dentista e cadeira só mudam enquanto o agendamento estiver agendado ou confirmado. Se ele estava confirmado, volta para agendado, porque a confirmação era do horário antigo. A mesma regra vale para bloqueios.

O paciente de um agendamento não muda. Para trocar o paciente, cancele e marque outra consulta. Um bloqueio precisa continuar com dentista ou cadeira.

*Tela em construção.*

### Confirmar, marcar atendimento, falta ou cancelamento
A situação de uma consulta segue estas passagens:

- **Agendado** pode virar confirmado, atendido, falta ou cancelado.
- **Confirmado** pode virar atendido, falta ou cancelado.
- **Atendido**, **falta** e **cancelado** são finais. Não voltam para trás.

Você só marca **atendido** ou **falta** depois do horário de início da consulta.

Falta e cancelamento liberam o horário para outra marcação. Ao cancelar ou marcar falta, você pode escrever o motivo (até 300 caracteres).

Um bloqueio só pode ser cancelado.

*Tela em construção.*

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
