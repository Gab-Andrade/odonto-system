---
modulo: precificacao
atualizado_em: 6b1d10b
---
# Tabelas de preço

> Aqui a clínica monta seus preços: cria tabelas, decide a quem cada tabela se aplica e consulta quanto custa um procedimento para cada caso. Também pode guardar o preço de um orçamento, para que ele não mude depois.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Tudo: criar e alterar tabelas, abrir e publicar versões, atribuir tabelas, consultar e congelar preços |
| Gestor | Tudo: criar e alterar tabelas, abrir e publicar versões, atribuir tabelas, consultar e congelar preços |
| Dentista | Consultar tabelas e preços, e congelar o preço de um procedimento para um orçamento |
| Recepção | Consultar tabelas e preços, e congelar o preço de um procedimento para um orçamento |
| ASB | Não tem acesso a este módulo |

## O que dá para fazer

### Criar uma tabela de preço
1. Dê um nome para a tabela e, se quiser, uma descrição.
2. Se a tabela parte de outra, escolha a tabela de origem e informe o percentual de ajuste. Ex.: `15` significa 15% a mais; `-10` significa 10% a menos.
3. Salve. A tabela fica disponível para receber preços e atribuições.

Só o Administrador e o Gestor podem criar tabelas.

*Tela em construção.*

### Alterar os dados de uma tabela
1. Abra a tabela.
2. Mude o nome, a descrição ou a situação da tabela. A situação pode ser **ativa** ou **arquivada**.
3. Salve.

Uma tabela só pode ser arquivada se não estiver atribuída a ninguém e se nenhuma outra tabela ativa herdar dela.

Só o Administrador e o Gestor podem alterar. Todas as mudanças ficam registradas no [Histórico de ações](auditoria.md).

*Tela em construção.*

### Abrir uma nova versão para mudar preços
1. Escolha a tabela.
2. Abra um rascunho. O rascunho é uma cópia da última versão publicada.
3. Se quiser, ajuste o percentual da versão.

Cada versão tem uma de duas situações:
- **Rascunho**: pode ser alterada.
- **Publicada**: não muda mais. Para mudar preços, você abre um novo rascunho.

Os preços não mudam direto na versão publicada. Você mexe no rascunho e, depois, publica. As versões antigas continuam guardadas.

Só o Administrador e o Gestor podem abrir rascunhos.

*Tela em construção.*

### Preencher ou trocar os preços do rascunho
1. Abra o rascunho.
2. Informe a lista completa de procedimentos: código, descrição, categoria (opcional) e preço.
3. Salve.

A lista que você salva substitui a lista anterior do rascunho. Por isso, envie sempre todos os procedimentos da tabela.

Regras:
- Cada código de procedimento só pode aparecer uma vez. Se houver repetido, o sistema mostra quais códigos se repetem e não salva.
- O preço não pode ser negativo. Zero é aceito.
- A lista pode ter até 5.000 procedimentos.

Só o Administrador e o Gestor podem fazer isso.

*Tela em construção.*

### Publicar uma versão
1. Escolha o rascunho.
2. Escolha a data em que os preços começam a valer. Pode ser uma data futura, mas não pode ser uma data passada. Se não escolher, vale a partir de hoje.
3. Publique.

Depois de publicada, a versão não pode mais ser alterada. Ela passa a ser usada nos novos cálculos e orçamentos, a partir da data escolhida.

Só o Administrador e o Gestor podem publicar.

*Tela em construção.*

### Dizer a quem uma tabela se aplica
1. Escolha a tabela.
2. Escolha o alcance: a clínica toda, um dentista ou um convênio. Para dentista, só pode ser escolhida quem tem o papel de dentista ou de administrador.
3. Se quiser, defina a prioridade. Quanto menor o número, mais forte a tabela. Se não informar, o sistema usa o padrão do alcance:
   - Convênio: 10
   - Dentista: 20
   - Clínica: 30

   A clínica pode mudar esses números ao fazer a atribuição.
4. Salve.

Uma mesma tabela pode ser atribuída a vários alcances. Para tirar uma atribuição, use a opção de remover. Só o Administrador e o Gestor podem atribuir ou remover.

*Tela em construção.*

### Consultar o preço de um procedimento
1. Informe o código do procedimento.
2. Se souber, informe o dentista e o convênio do paciente.
3. Informe a data. Se não informar, o sistema usa hoje.
4. Veja o preço, a tabela e a versão de onde ele veio, e a explicação de como o sistema chegou a esse valor.

Essa consulta não grava nada. Ela serve para simular.

A busca é feita procedimento por procedimento, na ordem de prioridade. Se a tabela de maior prioridade não tiver aquele procedimento (nem herdar de outra tabela que o tenha), o sistema tenta a próxima tabela da ordem.

Se nenhuma tabela tiver o procedimento, o sistema avisa que o preço não foi encontrado e mostra por quais tabelas passou.

Todos os perfis com acesso ao módulo podem consultar.

*Tela em construção.*

### Congelar o preço para um orçamento
1. Faça a consulta do procedimento, como acima.
2. Confirme. O sistema guarda o preço, a tabela, a versão e a data.
3. Você pode consultar esse registro depois, pela identificação dele.

O preço congelado não muda, mesmo que a tabela seja alterada ou publicada de novo depois.

Administrador, Gestor, Dentista e Recepção podem congelar preços.

*Tela em construção.*

## Bom saber

- Quando há mais de uma tabela que vale para o mesmo caso, vence a de menor número de prioridade. Por padrão, a ordem é: tabela do convênio do paciente (10), depois a do dentista (20), depois a da clínica (30).
- Se um procedimento não estiver na tabela de maior prioridade, o sistema procura nas tabelas seguintes, uma por uma.
- Mudar uma tabela não altera orçamentos já feitos. Eles ficam com o preço congelado na data em que foram salvos.
- Criar, alterar, publicar, atribuir e congelar preços fica registrado no [Histórico de ações](auditoria.md), com quem fez e quando.
- Se o seu perfil não puder fazer uma ação, o sistema não faz e informa que seu perfil não tem permissão.
- Previsto, ainda não disponível: importar planilhas (CSV ou Excel), exportar a tabela para Excel, calcular preços por fórmula com custos, margens e impostos, calcular repasse ou comissão de dentistas, e escolher quem vê custos e margens.

## Perguntas frequentes

**Posso mudar um preço sem criar uma nova versão?**
Não. Você abre um rascunho, altera os preços e publica. Assim, fica claro a partir de que dia cada preço vale.

**Um orçamento antigo muda se eu alterar a tabela?**
Não. Quando o orçamento congela o preço, ele guarda o valor, a tabela e a versão usados naquele momento.

**Por que não vejo a opção de criar ou alterar tabelas?**
Só o Administrador e o Gestor configuram tabelas. Os outros perfis consultam os preços.

**Quem vence quando um dentista tem uma tabela própria e a clínica tem outra?**
Vence a tabela com o número de prioridade menor. Por padrão, a tabela do convênio (10) vence a do dentista (20), e a do dentista vence a da clínica (30). A clínica pode mudar esses números ao atribuir.
