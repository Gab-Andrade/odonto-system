---
modulo: prontuario
atualizado_em: 1982acb
---
# Prontuário: anamnese, atendimento e evolução

> Guarda a ficha clínica do paciente: a anamnese (questionário inicial, com alertas como alergias e uso de remédios), o registro de cada atendimento e a evolução clínica, que é o texto do que foi feito em cada consulta. Nada do que foi registrado é apagado. Correções entram como complemento.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Montar e publicar os modelos de anamnese. Preencher anamneses. Abrir atendimentos, registrar evoluções, fechar e fazer adendos, desde que seja o dentista do atendimento ou o autor da evolução. Ver anamneses, atendimentos e evoluções. |
| Gestor | Montar e publicar os modelos de anamnese. Ver anamneses, atendimentos e evoluções. Não preenche anamneses nem atende. |
| Dentista | Preencher anamneses. Abrir atendimentos, registrar evoluções, fechar o atendimento e fazer adendos. Ver anamneses, atendimentos e evoluções. Não altera os modelos. |
| ASB | Preencher anamneses. Ver anamneses, atendimentos e evoluções. Não abre atendimentos nem registra evoluções. Não altera os modelos. |
| Recepção | Não vê o conteúdo do prontuário: anamneses, alertas, atendimentos nem evoluções. |

## O que dá para fazer

### Abrir um atendimento

Quem pode: Dentista e Administrador.

1. Escolha o paciente. Ele precisa estar ativo.
2. Se o atendimento vem de um horário da agenda, informe esse agendamento. Para encaixe ou urgência, deixe em branco.
3. Informe o horário de início, se for diferente de agora. Pode ser até 7 dias para trás, nunca no futuro.

- Quem abre o atendimento passa a ser o dentista responsável por ele.
- **Substituição:** você pode abrir um atendimento a partir do horário de outro dentista. Nesse caso, o atendimento fica no seu nome.
- Ao abrir a partir de um horário da agenda, o horário passa a aparecer como "atendido". A agenda só aceita isso depois que o horário de início já chegou.
- Cada horário da agenda tem no máximo um atendimento. Só consultas podem ser usadas, e elas precisam ser do mesmo paciente.

*Tela em construção.*

### Registrar a evolução do atendimento

Quem pode: Dentista e Administrador, somente no atendimento que eles abriram.

1. Abra o atendimento.
2. Escreva o que foi feito. O texto é obrigatório e pode ter até 20.000 caracteres.
3. Informe a data do ato clínico, se for diferente de agora. Pode ser até 7 dias para trás, nunca no futuro.
4. Salve.

- Cada evolução guarda duas datas: a do ato clínico (quando aconteceu) e a do registro (quando foi gravada). Assim, um registro feito hoje sobre um atendimento de ontem fica claro.
- Não dá para registrar evolução em atendimento fechado. Nesse caso, faça um adendo.
- Quem não é o dentista do atendimento não registra nele.
- Ao salvar, a evolução recebe a sua assinatura simples (veja em Bom saber).

*Tela em construção.*

### Fazer um adendo (corrigir ou complementar uma evolução)

Quem pode: somente o autor da evolução (Dentista ou Administrador).

1. Abra a evolução.
2. Escreva o complemento ou a correção. O texto pode ter até 20.000 caracteres.
3. Salve.

- O adendo entra como um registro novo, ligado à evolução. O texto original continua como foi escrito.
- Dá para fazer adendo a qualquer tempo, inclusive depois que o atendimento foi fechado.
- A data do adendo é a data em que você o fez. Não aceita data retroativa.
- Não dá para fazer adendo sobre outro adendo. O complemento é sempre feito sobre a evolução.

*Tela em construção.*

### Fechar o atendimento

Quem pode: o dentista do atendimento (Dentista ou Administrador que o abriu).

1. Abra o atendimento.
2. Feche quando terminar.

- Pode fechar sem evolução, por exemplo quando o paciente veio e nada foi feito.
- Depois de fechado, não entram novas evoluções. Para complementar, use adendo.
- O sistema grava quem fechou e quando.
- Hoje o sistema não tem opção para reabrir um atendimento fechado.

*Tela em construção.*

### Ver um atendimento

Quem pode: Administrador, Gestor, Dentista e ASB.

- Veja a data de início, o dentista responsável, se veio de um horário da agenda e a situação (aberto ou fechado).
- Veja todas as evoluções e adendos do atendimento, na ordem em que foram registrados.
- Cada evolução e cada adendo mostra o autor, a data do ato clínico, a data do registro e as assinaturas.

Cada vez que você abre um atendimento, o sistema registra a ação no Histórico de ações. O registro não guarda o texto clínico.

*Tela em construção.*

### Ver os atendimentos de um paciente

Quem pode: Administrador, Gestor, Dentista e ASB.

- Veja a lista de atendimentos do paciente, do mais recente para o mais antigo. Cada um mostra quantas evoluções tem.
- A lista vem em páginas de 100 atendimentos. Cada pedido aceita até 500.

Cada consulta a essa lista fica registrada no Histórico de ações, sem o texto clínico.

*Tela em construção.*

### Ver a linha do tempo de evoluções de um paciente

Quem pode: Administrador, Gestor, Dentista e ASB.

- Veja evoluções e adendos do paciente, do mais recente para o mais antigo, pela data do ato clínico.
- Adendos aparecem como registros próprios, ligados à evolução que complementam.
- A lista vem em páginas de 100. Cada pedido aceita até 500.

Cada consulta a essa linha do tempo fica registrada no Histórico de ações, sem o texto clínico.

*Tela em construção.*

### Criar um modelo de anamnese

Quem pode: Administrador e Gestor.

1. Dê um nome ao modelo (até 120 caracteres). Não pode haver dois modelos com o mesmo nome na clínica.
2. Escreva uma descrição, se quiser (até 500 caracteres).
3. Monte as perguntas agora ou depois, no rascunho.

Ao criar o modelo, o sistema já abre o rascunho 1 para você montar as perguntas.

*Tela em construção.*

### Montar as perguntas no rascunho

Quem pode: Administrador e Gestor.

Cada modelo tem um único rascunho em edição por vez. Enquanto ele existir, não dá para abrir outro.

- Inclua até 150 perguntas.
- Cada pergunta tem um código próprio (letras minúsculas, números e _, até 40 caracteres). Ele não pode se repetir no mesmo modelo.
- Para cada pergunta, informe o texto (até 300 caracteres) e o tipo: texto livre, sim ou não, escolha de uma opção, escolha de várias opções, número ou data.
- Seção e ajuda (até 300 caracteres) são opcionais.
- Perguntas de escolha precisam de pelo menos 2 opções e no máximo 50. Opções repetidas não são aceitas, e maiúsculas ou minúsculas não contam como diferença.
- Marque como obrigatória a pergunta que precisa ser respondida.
- Marque como alerta a pergunta cuja resposta merece atenção. Em perguntas de escolha, você pode escolher quais opções geram o alerta. Se não escolher nenhuma, qualquer opção gera.
- Ao salvar, o rascunho passa a ter exatamente a lista de perguntas enviada. A lista anterior é substituída.

Para mudar um modelo já publicado, crie um novo rascunho. Ele começa com as perguntas da versão publicada. Só o rascunho pode ser alterado.

*Tela em construção.*

### Publicar uma versão do modelo

Quem pode: Administrador e Gestor.

1. Confira as perguntas do rascunho.
2. Publique. O rascunho vira a versão publicada, com um número novo.
3. A versão publicada anterior passa a ser "substituída". Ela continua guardada.

Para publicar, o rascunho precisa ter ao menos uma pergunta. Se não quiser mais um rascunho, você pode descartá-lo. A versão publicada não pode ser apagada.

*Tela em construção.*

### Alterar ou desativar um modelo

Quem pode: Administrador e Gestor.

- Altere o nome, a descrição ou a situação (ativo ou inativo). O nome não pode ficar vazio.
- Um modelo inativo some da lista de modelos, a não ser que você peça para ver os inativos. Ele também não pode ser usado em novas anamneses.
- Anamneses já preenchidas com o modelo continuam visíveis.
- Ao salvar, o sistema registra quais campos foram mudados.

*Tela em construção.*

### Ver os modelos

Quem pode: Administrador, Gestor, Dentista e ASB.

- Veja a lista de modelos ativos. Os inativos aparecem se você pedir.
- Veja cada modelo com a versão publicada, o rascunho (se houver) e o histórico de versões.

Ver os modelos não fica registrado no Histórico de ações, pois não tem dado de paciente.

*Tela em construção.*

### Preencher a anamnese de um paciente

Quem pode: Administrador, Dentista e ASB.

1. Escolha o paciente e o modelo ativo que tenha versão publicada.
2. Responda as perguntas. Pode deixar em branco as que não se aplicam, exceto as obrigatórias.
3. Salve. A anamnese fica registrada com a data e com quem preencheu.

- O paciente precisa estar ativo. Se estiver inativo, reative o cadastro antes.
- Se o modelo foi atualizado enquanto a tela estava aberta, o sistema recusa o envio e pede para recarregar.
- Respostas em branco não são guardadas.
- Texto: até 2.000 caracteres.
- Número: até 1 bilhão, para mais ou para menos.
- Data: uma data válida, no formato dia, mês e ano.
- Escolhas: só as opções que aparecem na pergunta.

*Tela em construção.*

### Ver as anamneses de um paciente

Quem pode: Administrador, Gestor, Dentista e ASB.

- Veja a lista de anamneses do paciente, da mais recente para a mais antiga. A mais recente de cada modelo aparece como "atual".
- Abra uma anamnese para ver as perguntas da versão em que foi respondida e as respostas.
- Veja os alertas das anamneses atuais, uma por modelo. Eles servem para o cabeçalho da ficha do paciente.

Cada vez que você lista, abre ou consulta os alertas de um paciente, o sistema registra a ação no Histórico de ações. O registro não guarda as respostas.

*Tela em construção.*

## Bom saber

- **Evolução não se apaga nem se altera.** Se houve erro ou faltou algo, faça um adendo. Quem ler vê o texto original e o complemento, cada um com a sua data.
- **Assinatura simples em cada registro.** Cada evolução e cada adendo é assinado, na hora, por quem o escreveu. O sistema guarda quem assinou, quando, e um código calculado sobre o texto. Se o texto for mudado depois, o código deixa de bater. A assinatura digital ICP-Brasil, exigida para prontuário eletrônico, está prevista.
- **Datas retroativas.** Atendimento, evolução e horário de início aceitam data de até 7 dias atrás. Mais antigo que isso, o sistema recusa. Data no futuro também é recusada, com uma pequena folga para relógios levemente adiantados.
- **Um atendimento por horário da agenda.** Cada horário de consulta tem no máximo um atendimento.
- **Substituição.** Quem abre o atendimento fica responsável por ele, mesmo que o horário fosse de outro dentista.
- **Paciente inativo.** Não é possível abrir atendimento para paciente inativo. Reative o cadastro antes.
- **Anamnese não se altera nem se apaga.** Se houve erro, preencha a anamnese de novo. A nova passa a ser a atual, e a anterior fica no histórico.
- **Versão publicada não se altera.** Para mudar um modelo, crie um novo rascunho e publique.
- **Cada anamnese guarda a versão em que foi respondida.** Mudanças posteriores no modelo não alteram o que já foi respondido.
- **Versões antigas ficam guardadas.** Ao publicar uma nova versão, a anterior vira "substituída", mas continua no histórico do modelo.
- **Modelo sem versão publicada não aparece para preencher.** Ele precisa de ao menos uma versão publicada.
- **Como um alerta é gerado:**
  - Sim ou não: gera alerta quando a resposta é "sim".
  - Escolha de uma ou de várias opções: se a clínica escolheu opções de alerta, gera alerta só com elas. Se não escolheu, qualquer resposta gera.
  - Texto, número e data: qualquer resposta preenchida gera alerta.
  - Só perguntas marcadas como alerta geram alertas.
- **Sigilo:** a Recepção não tem acesso ao prontuário. Cada clínica só vê os próprios modelos, anamneses, atendimentos e evoluções. Algo de outra clínica aparece como "não encontrado".
- **Registro de ações (LGPD):** toda leitura de anamnese, alerta, atendimento ou evolução de paciente fica no Histórico de ações, com quem fez e quando. Abrir, registrar, fazer adendo e fechar também ficam registrados. Os registros não guardam o texto clínico nem as respostas.
- **Previsto:** assinatura digital ICP-Brasil e anexos, como PDF e imagens.

## Perguntas frequentes

**Por que não consigo registrar uma evolução?**
Confira se o atendimento está aberto, se você é o dentista que o abriu e se a data do ato clínico está dentro de 7 dias. Se o atendimento já foi fechado, use adendo.

**Errei uma evolução. Posso apagá-la?**
Não. Faça um adendo com a correção. O texto original continua visível, com a data em que foi escrito.

**Esqueci de registrar a evolução de ontem. Posso?**
Sim, se o atendimento ainda estiver aberto ou se você abrir um atendimento novo com a data de ontem. Informe a data do ato clínico. O limite é de 7 dias para trás.

**Posso fechar um atendimento sem evolução?**
Sim. Use isso quando o paciente veio e nada foi feito.

**O paciente veio para substituir outro dentista. Posso atendê-lo?**
Sim. Abra o atendimento a partir do horário, se houver. O atendimento fica no seu nome.

**Por que não consigo preencher a anamnese de um paciente?**
Confira se o paciente está ativo, se o modelo está ativo e se ele tem uma versão publicada. Se a tela estava aberta enquanto o modelo mudou, recarregue a página.

**Errei uma resposta da anamnese. Como corrijo?**
Preencha a anamnese de novo. A nova resposta vira a atual, e a anterior continua no histórico.

**Por que não consigo publicar o rascunho?**
O rascunho precisa ter ao menos uma pergunta.

**Um alerta apareceu por engano. Posso apagá-lo?**
Não. O alerta vem da resposta. Para mudar, preencha uma nova anamnese com as respostas corretas. Os alertas passam a seguir a anamnese mais recente.
