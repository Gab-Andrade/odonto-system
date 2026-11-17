---
modulo: precificacao
atualizado_em: 12bcf0e
---
# Tabelas de preço

> Aqui a clínica monta seus preços: cria tabelas, importa preços de uma planilha, decide a quem cada tabela se aplica e consulta quanto custa um procedimento em cada caso. Também pode guardar o preço de um orçamento, para que ele não mude depois.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Tudo: criar e alterar tabelas, preparar e publicar versões, importar planilhas, atribuir tabelas, consultar e congelar preços |
| Gestor | Tudo, igual ao Administrador |
| Dentista | Ver tabelas, versões, preços e atribuições, baixar a tabela em Excel, consultar e congelar o preço de um procedimento |
| Recepção | Ver tabelas, versões, preços e atribuições, baixar a tabela em Excel, consultar e congelar o preço de um procedimento |

O ASB não tem acesso a este módulo.

## O que dá para fazer

### Ver as tabelas de preço
1. Veja a lista de tabelas da clínica.
2. Escolha uma tabela para ver os dados dela e suas versões.
3. Escolha uma versão para ver os procedimentos e preços dela.

Todos os perfis com acesso ao módulo podem ver. *Tela em construção.*

### Criar uma tabela de preço
1. Dê um nome para a tabela e, se quiser, uma descrição.
2. Se a tabela parte de outra, escolha a tabela de origem e informe o percentual de ajuste. Ex.: `15` quer dizer 15% a mais; `-10` quer dizer 10% a menos. O percentual só pode ser informado quando há tabela de origem.
3. Salve. A tabela fica pronta para receber preços e atribuições. O percentual informado vira o ajuste da versão 1.

A tabela de origem só é escolhida na criação. A tabela de origem também precisa estar ativa (não arquivada).

Só o Administrador e o Gestor podem criar tabelas. *Tela em construção.*

### Alterar os dados de uma tabela
1. Abra a tabela.
2. Mude o nome, a descrição ou a situação da tabela.
3. Salve.

Se o sistema não aceitar a mudança, ele recusa e explica o motivo. Alguns casos:
- **Arquivar** uma tabela é bloqueado enquanto ela estiver atribuída a alguém (dentista, convênio ou clínica) ou enquanto outra tabela ativa herdar dela. Remova as atribuições ou arquive antes a tabela filha.
- **Reativar** uma tabela filha é bloqueado enquanto a tabela-pai estiver arquivada. Reative a tabela-pai primeiro.

Só o Administrador e o Gestor podem alterar. Toda mudança fica registrada no [Histórico de ações](auditoria.md). *Tela em construção.*

### Preparar uma nova versão para mudar preços
1. Escolha a tabela.
2. Abra um rascunho. O rascunho é uma cópia da última versão publicada, inclusive do percentual de ajuste dela.
3. Se quiser, ajuste o percentual do rascunho antes de publicar. Esse ajuste é da versão, não da tabela: cada versão tem o seu.

Cada versão está em uma de duas situações:
- **Rascunho**: pode ser alterado.
- **Publicada**: não muda mais. Para mudar preços, abra um novo rascunho.

Os preços não mudam direto na versão publicada. As versões antigas continuam guardadas.

Só o Administrador e o Gestor podem abrir rascunhos. *Tela em construção.*

### Informar ou trocar os preços do rascunho
1. Abra o rascunho.
2. Informe a lista completa de procedimentos: código, descrição, categoria (opcional) e preço.
3. Salve.

A lista salva substitui a lista anterior do rascunho. Por isso, envie sempre todos os procedimentos da tabela.

Regras:
- Cada código de procedimento só pode aparecer uma vez. Se houver repetido, o sistema mostra quais códigos se repetem e não salva.
- O preço não pode ser negativo. Zero é aceito.
- A lista pode ter até 5.000 procedimentos.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Publicar uma versão
1. Escolha o rascunho.
2. Escolha a data em que os preços começam a valer. Se não escolher, vale a partir de hoje. A data não pode ser no passado nem anterior à última versão publicada. Pode ser uma data futura, para agendar um reajuste.
3. Publique.

Depois de publicada, a versão não pode mais ser alterada. Ela passa a valer nos novos cálculos e orçamentos, a partir da data escolhida.

Só o Administrador e o Gestor podem publicar. *Tela em construção.*

### Importar uma planilha de preços
Use esta opção quando a clínica já tem os preços em uma planilha.

1. Escolha a tabela e envie o arquivo `.csv` ou `.xlsx`, de até 2 MB. Se for Excel, escolha a aba. Se não escolher, o sistema usa a primeira.
2. O sistema lê o arquivo e sugere quais colunas são o código, a descrição e o preço. Confira a sugestão. Você pode ajustá-la ou usar um perfil de importação salvo.
3. Confira a validação. O sistema verifica cada linha, mostra quantas estão certas e quantas têm erro, e mostra o que muda em relação à versão atual.
   - **Erro**: a linha não pode ser usada (ex.: preço vazio, código repetido). Linhas com erro bloqueiam a aplicação.
   - **Aviso**: a linha pode ser usada, mas precisa de conferência. Por exemplo, o preço `1.500` (ponto seguido de três números, sem vírgula) é lido como mil e quinhentos. Confira esses valores antes de aplicar.
4. Aplique. Se houver linhas com erro, o sistema não grava nada, a menos que você escolha ignorar essas linhas. Se escolher, ele grava só as linhas certas no rascunho e descarta as que têm erro.
5. Publique o rascunho, se estiver de acordo. A publicação é um passo separado.

Nas etapas de leitura e conferência, nada muda na tabela. Só a etapa de aplicar grava os preços, e grava no rascunho.

Você também pode ver as importações feitas antes, com as primeiras linhas lidas de cada uma.

Só o Administrador e o Gestor podem importar. *Tela em construção.*

### Baixar a planilha-modelo
1. Baixe a planilha-modelo. Ela traz as colunas esperadas e exemplos.
2. Preencha a planilha e use-a na importação.

Só o Administrador e o Gestor podem baixar o modelo. *Tela em construção.*

### Salvar um perfil de importação
Um perfil guarda a relação entre as colunas da sua planilha e os campos do sistema, para você não precisar refazer a mesma ligação toda vez.

1. Dê um nome ao perfil.
2. Informe qual coluna da planilha corresponde a cada campo.
3. Se quiser, informe as colunas que devem ser guardadas como campos extras do procedimento.
4. Salve.

Você também pode apagar um perfil que não usa mais.

Só o Administrador e o Gestor podem salvar ou apagar perfis. *Tela em construção.*

### Baixar a tabela em Excel
1. Escolha a tabela e a versão.
2. Baixe o arquivo.

O arquivo sai no mesmo formato aceito pela importação. Assim você pode editar e enviar de volta.

Todos os perfis com acesso ao módulo podem baixar. *Tela em construção.*

### Dizer a quem uma tabela se aplica
1. Escolha a tabela.
2. Escolha o alcance: a clínica toda, um dentista ou um convênio. Para dentista, pode ser escolhido quem tem o papel de Dentista ou de Administrador que também atende.
3. Se quiser, informe a prioridade. Quanto menor o número, mais forte a tabela. Se não informar, o sistema usa o padrão do alcance:
   - Convênio: 10
   - Dentista: 20
   - Clínica: 30

   A clínica pode trocar esses números ao fazer a atribuição.
4. Salve.

Uma mesma tabela pode ser atribuída a vários alcances. Para mudar a prioridade de uma atribuição, remova a atribuição e crie outra.

Só o Administrador e o Gestor podem atribuir ou remover. Todos os perfis com acesso ao módulo podem ver as atribuições. *Tela em construção.*

### Consultar o preço de um procedimento
1. Informe o código do procedimento.
2. Se souber, informe o dentista e o convênio do paciente.
3. Informe a data. Se não informar, o sistema usa hoje.
4. Veja o preço, a tabela e a versão de onde ele veio, e a explicação do caminho que o sistema seguiu para chegar a esse valor.

Essa consulta não grava nada. Serve para simular.

Se nenhuma tabela tiver o procedimento, o sistema avisa que o preço não foi encontrado e mostra por quais tabelas passou.

Todos os perfis com acesso ao módulo podem consultar. *Tela em construção.*

### Congelar o preço para um orçamento
1. Faça a consulta do procedimento, como acima.
2. Confirme. O sistema guarda o preço, a tabela, a versão, a data e quem fez o registro.
3. Guarde a identificação do registro. Com ela, você consulta o mesmo preço depois.

O preço congelado não muda, mesmo que a tabela seja alterada ou publicada de novo.

Administrador, Gestor, Dentista e Recepção podem congelar preços. *Tela em construção.*

## Bom saber

- Quando mais de uma tabela vale para o mesmo caso, vence a de menor número de prioridade. Por padrão, a ordem é: convênio do paciente (10), depois o dentista (20), depois a clínica (30). A clínica pode trocar esses números.
- Se um procedimento não estiver na tabela de maior prioridade, o sistema procura nas tabelas seguintes, uma por uma.
- Uma tabela pode herdar de outra. Ela usa os preços da tabela de origem, somados ao ajuste da versão que está valendo, a menos que tenha preço próprio para aquele procedimento.
- Uma versão publicada não é alterada. Para corrigir um preço, abra um novo rascunho e publique de novo, com data de vigência.
- Mudar uma tabela não altera orçamentos já feitos. Eles ficam com o preço congelado.
- Criar, alterar, publicar, importar, atribuir, remover e congelar preços fica registrado no [Histórico de ações](auditoria.md), com quem fez e quando.
- Se o seu perfil não puder fazer uma ação, o sistema não faz e informa que seu perfil não tem permissão.
- Previsto, ainda não disponível: preços calculados por fórmula, com custos, materiais, margens e impostos; cálculo de repasse ou comissão de dentistas; escolher quem vê custos e margens; atribuir tabelas a unidades e campanhas; escolher quais perfis podem criar e alterar tabelas.

## Perguntas frequentes

**Posso mudar um preço sem criar uma nova versão?**
Não. Você prepara um rascunho, altera os preços e publica. Assim fica claro a partir de que dia cada preço vale.

**Um orçamento antigo muda se eu alterar a tabela?**
Não. Quando o preço é congelado, o sistema guarda o valor, a tabela e a versão usados naquele momento.

**Por que não vejo a opção de criar ou alterar tabelas?**
Só o Administrador e o Gestor configuram tabelas. Os outros perfis consultam os preços.

**Quem vence quando um dentista tem uma tabela própria e a clínica tem outra?**
Vence a tabela com o menor número de prioridade. Por padrão, a tabela do convênio (10) vence a do dentista (20), e a do dentista vence a da clínica (30). A clínica pode definir outros números ao atribuir.
