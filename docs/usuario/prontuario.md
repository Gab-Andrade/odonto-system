---
modulo: prontuario
atualizado_em: 4346a5f
---
# Prontuário e anamnese

> Guarda a anamnese de cada paciente, o questionário inicial que a clínica monta do seu jeito, e os alertas que as respostas geram, como alergias ou uso de remédios. As anotações de cada atendimento (evolução clínica) virão depois.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Montar e publicar os modelos de anamnese, preencher anamneses e ver as respostas e os alertas dos pacientes. |
| Gestor | Montar e publicar os modelos de anamnese e ver as respostas e os alertas dos pacientes. Não preenche anamneses. |
| Dentista | Preencher anamneses e ver as respostas e os alertas dos pacientes. Não altera os modelos. |
| ASB | Preencher anamneses e ver as respostas e os alertas dos pacientes. Não altera os modelos. |
| Recepção | Não vê o conteúdo das anamneses nem os alertas. |

## O que dá para fazer

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
- **Sigilo:** a Recepção não tem acesso às anamneses nem aos alertas. Cada clínica só vê os próprios modelos e anamneses. Um modelo ou uma anamnese de outra clínica aparece como "não encontrado".
- **Registro de ações (LGPD):** toda leitura de anamnese ou de alertas de paciente e toda gravação fica no Histórico de ações, com quem fez e quando. Os registros não guardam as respostas.
- **Previsto:** a evolução clínica (anotações de cada atendimento) e os anexos, como PDF e imagens. A evolução não poderá ser apagada: correções entram como complemento, sem alterar o texto original.

## Perguntas frequentes

**Por que não consigo preencher a anamnese de um paciente?**
Confira se o paciente está ativo, se o modelo está ativo e se ele tem uma versão publicada. Se a tela estava aberta enquanto o modelo mudou, recarregue a página.

**Errei uma resposta. Como corrijo?**
Preencha a anamnese de novo. A nova resposta vira a atual, e a anterior continua no histórico.

**Por que não consigo publicar o rascunho?**
O rascunho precisa ter ao menos uma pergunta.

**Um alerta apareceu por engano. Posso apagá-lo?**
Não. O alerta vem da resposta. Para mudar, preencha uma nova anamnese com as respostas corretas. Os alertas passam a seguir a anamnese mais recente.
