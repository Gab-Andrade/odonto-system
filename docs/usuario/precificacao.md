---
modulo: precificacao
atualizado_em: 59c8187
---
# Tabelas de preço

> Aqui a clínica define quanto custa cada procedimento. Ela pode digitar ou importar os preços de uma planilha, ou calcular os preços a partir dos custos (materiais, tempo de atendimento, custos fixos, impostos e margem). Também consulta o preço de um procedimento e pode guardar esse preço para um orçamento, para que ele não mude depois.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Tudo: criar e alterar tabelas, preparar e publicar versões, importar planilhas, atribuir tabelas, cadastrar fichas técnicas, variáveis e fórmulas, recalcular, consultar e congelar preços |
| Gestor | Tudo, igual ao Administrador |
| Dentista | Ver tabelas, versões, preços e atribuições, baixar a tabela em Excel, consultar e congelar o preço de um procedimento |
| Recepção | Igual ao Dentista |

- O ASB não tem acesso a este módulo.
- Custos, fichas técnicas, variáveis, fórmulas e a conta de cada preço calculado são vistos só pelo Administrador e pelo Gestor. Dentista e Recepção veem apenas os preços.

## O que dá para fazer

### Ver as tabelas de preço
1. Veja a lista de tabelas da clínica.
2. Escolha uma tabela para ver os dados dela e suas versões.
3. Escolha uma versão para ver os procedimentos e preços dela.

Todos os perfis com acesso ao módulo podem ver. *Tela em construção.*

### Criar uma tabela de preço
1. Dê um nome para a tabela e, se quiser, uma descrição. Não pode haver duas tabelas com o mesmo nome, mesmo que mudem as letras maiúsculas.
2. Escolha o tipo:
   - **Fixa**: você digita ou importa os preços. É o tipo padrão.
   - **Calculada**: os preços são gerados por fórmula, a partir dos custos. Veja "Montar uma tabela calculada por fórmula" mais abaixo.
3. Se a tabela fixa parte de outra, escolha a tabela de origem e informe o percentual de ajuste. Ex.: `15` quer dizer 15% a mais; `-10` quer dizer 10% a menos. O percentual só pode ser informado quando há tabela de origem.
4. Se a tabela for calculada, pode escolher um dentista de referência. As variáveis dele serão usadas no cálculo. Sem essa escolha, o sistema usa as variáveis da clínica.
5. Salve. A tabela fica pronta, com a versão 1 em rascunho.

Regras:
- A tabela de origem precisa estar ativa (não arquivada).
- Tabela calculada não herda de outra e não tem percentual de ajuste.
- A tabela de origem e o dentista de referência só são escolhidos na criação.

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
2. Abra um rascunho. O rascunho é uma cópia da última versão publicada: os preços, o percentual de ajuste e, se for tabela calculada, a fórmula.
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
- Em tabela calculada não se digita preço à mão. Os preços vêm do recálculo.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Publicar uma versão
1. Escolha o rascunho.
2. Escolha a data em que os preços começam a valer. Se não escolher, vale a partir de hoje. A data não pode ser no passado nem anterior à última versão publicada. Pode ser uma data futura, para agendar um reajuste.
3. Publique. Se a tabela calculada tiver procedimentos com erro, o sistema mostra a lista e pede confirmação antes de publicar.

Regras:
- Tabela arquivada não publica versões.
- Tabela que não herda de outra precisa ter pelo menos um procedimento.
- Tabela calculada precisa estar recalculada com os custos atuais. Se um custo, ficha técnica ou variável mudou depois do último cálculo, o sistema bloqueia a publicação e pede para recalcular.
- Tabela calculada cujo último recálculo deixou procedimentos de fora por erro: a publicação só acontece com a sua confirmação explícita. O sistema mostra a lista desses procedimentos. Se você confirmar, a versão é publicada sem eles, e no orçamento o preço deles virá da próxima tabela da prioridade. Se possível, corrija a ficha técnica ou as variáveis e recalcule antes de confirmar.
- Um rascunho aberto a partir de uma versão com esses erros herda a lista. Se você publicar sem recalcular, a confirmação é pedida de novo.

Depois de publicada, a versão não pode mais ser alterada. Ela passa a valer nos novos cálculos e orçamentos, a partir da data escolhida.

Só o Administrador e o Gestor podem publicar. *Tela em construção.*

### Importar uma planilha de preços
Use esta opção quando a clínica já tem os preços em uma planilha. Não serve para tabela calculada nem para tabela arquivada.

1. Escolha a tabela e envie o arquivo `.csv` ou `.xlsx`, de até 2 MB. Se for Excel, escolha a aba. Se não escolher, o sistema usa a primeira. Arquivos `.xls` (Excel antigo) não são aceitos: salve como `.xlsx`.
2. O sistema lê o arquivo e sugere quais colunas são o código, a descrição e o preço. Confira a sugestão. Você pode ajustá-la ou usar um perfil de importação salvo. A planilha pode ter até 5.000 linhas de procedimentos e 100 colunas.
3. Confira a validação. O sistema verifica cada linha, mostra quantas estão certas e quantas têm erro, e mostra o que muda em relação à versão atual (itens novos, alterados e removidos).
   - **Erro**: a linha não pode ser usada. Ex.: preço vazio, código repetido, descrição vazia. Linhas com erro bloqueiam a aplicação.
   - **Aviso**: a linha pode ser usada, mas precisa de conferência. Por exemplo, o preço `1.500` (ponto seguido de três números, sem vírgula) é lido como mil e quinhentos. Confira esses valores antes de aplicar.
   - Preços podem vir como `150,00` ou `R$ 150,00`. Mais de duas casas decimais é erro.
4. Aplique. Se houver linhas com erro, o sistema não grava nada, a menos que você escolha ignorar essas linhas. Se escolher, ele grava só as linhas certas no rascunho e descarta as que têm erro.
5. Publique o rascunho, se estiver de acordo. A publicação é um passo separado.

Regras:
- Aplicar a planilha substitui todos os preços que estavam no rascunho pelos da planilha.
- Se a tabela mudou desde a validação (outra versão publicada, ou preços editados no rascunho), o sistema pede para validar de novo.
- Uma importação já aplicada não pode ser aplicada outra vez. Envie o arquivo de novo.

Nas etapas de leitura e conferência, nada muda na tabela. Só a etapa de aplicar grava os preços, e grava no rascunho.

Você também pode ver as importações feitas antes, com as primeiras linhas lidas de cada uma.

Só o Administrador e o Gestor podem importar. *Tela em construção.*

### Baixar a planilha-modelo
1. Baixe a planilha-modelo. Ela traz as colunas esperadas e exemplos.
2. Preencha a planilha e use-a na importação.

Só o Administrador e o Gestor podem baixar o modelo. *Tela em construção.*

### Salvar um perfil de importação
Um perfil guarda a relação entre as colunas da sua planilha e os campos do sistema, para você não precisar refazer a mesma ligação toda vez.

1. Dê um nome ao perfil. Não pode haver dois perfis com o mesmo nome.
2. Informe qual coluna da planilha corresponde a Código, Descrição e Preço. Essas três são obrigatórias. Categoria é opcional.
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

Uma mesma tabela pode ser atribuída a vários alcances, mas não duas vezes ao mesmo alcance. Para mudar a prioridade de uma atribuição, remova a atribuição e crie outra. Tabela arquivada não pode ser atribuída.

Só o Administrador e o Gestor podem atribuir ou remover. Todos os perfis com acesso ao módulo podem ver as atribuições. *Tela em construção.*

### Cadastrar fichas técnicas
A ficha técnica diz quanto tempo um procedimento leva e quais materiais ele usa. Os materiais vêm do estoque, e o custo de cada um também. Esse é o ponto de partida das tabelas calculadas.

1. Informe o código e a descrição do procedimento. Categoria é opcional.
2. Informe o tempo do procedimento, em minutos (de 1 a 1.440).
3. Adicione os materiais: escolha o material do estoque e a quantidade usada. A quantidade precisa ser maior que zero e pode ter até 4 casas decimais. A ficha aceita até 100 materiais.
4. Salve.

Regras:
- Cada procedimento tem uma única ficha. Se já existir uma, o sistema recusa a nova.
- O mesmo material não pode aparecer duas vezes na mesma ficha.
- Material inativo, ou que não existe na clínica, não pode ser usado.
- Ao alterar uma ficha, você substitui a ficha inteira (tempo e materiais).
- Ao apagar ou alterar uma ficha, os preços calculados só mudam depois de recalcular.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Cadastrar as variáveis de custo
Variáveis são números que a fórmula usa. Exemplos: custos fixos do mês, horas de atendimento, pró-labore, impostos, taxa de cartão e margem.

1. Dê um nome à variável, com letras minúsculas, números e `_` (ex.: `custos_fixos_mensais`). Não use os nomes que o sistema já usa: `custo_materiais`, `tempo_minutos`, `tempo_horas`, `min`, `max`, `arredondar`, `se` e `preco`.
2. Informe o valor.
3. Se quiser, escreva um rótulo para explicar a variável.
4. Escolha o alcance: o padrão da clínica, ou um dentista específico.
5. Salve. Se já existir uma variável com o mesmo nome e o mesmo alcance, o valor é atualizado.

Para a fórmula padrão, cadastre estas variáveis:

| Variável | O que é |
|---|---|
| `custos_fixos_mensais` | aluguel, salários, contas etc. por mês (R$) |
| `horas_produtivas_mes` | horas de atendimento por mês |
| `pro_labore_hora` | remuneração do dentista por hora (R$) |
| `impostos_pct` | impostos sobre o faturamento (%) |
| `taxa_cartao_pct` | taxa média de cartão (%) |
| `margem_pct` | margem de lucro desejada (%) |

Valor próprio de um dentista prevalece sobre o padrão da clínica. O que o dentista não tiver, usa o padrão da clínica. Só quem tem o papel de Dentista, ou Administrador que também atende, pode ter valor próprio.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Montar uma tabela calculada por fórmula
1. Crie uma tabela do tipo calculada. Ela começa com a fórmula padrão, o "preço por dentro". Veja "Criar uma tabela de preço".
2. Cadastre as fichas técnicas dos procedimentos e as variáveis que a fórmula pede.
3. Se quiser, ajuste a fórmula no rascunho. Veja "Ajustar a fórmula de uma tabela calculada".
4. Recalcule o rascunho. O sistema gera um preço para cada ficha técnica.
5. Confira o relatório do recálculo: quantos preços foram gerados e quais procedimentos deram erro, com o motivo.
6. Publique a versão.

Regras:
- Se faltar alguma variável que a fórmula usa, o recálculo não roda. O sistema diz quais faltam.
- Sem nenhuma ficha técnica, o recálculo não roda.
- Procedimento com erro fica de fora dos preços e aparece no relatório. Os outros são gerados normalmente.
- Recalcular substitui os preços do rascunho.
- Ao mudar a fórmula, o sistema marca o cálculo como desatualizado. Você precisa recalcular antes de publicar.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Ajustar a fórmula de uma tabela calculada
Só é possível mudar a fórmula em rascunho de tabela calculada.

1. Abra o rascunho.
2. Informe os passos da fórmula, na ordem. Cada passo tem um nome e uma conta. Um passo pode usar o resultado dos passos anteriores.
3. Salve. O sistema confere a fórmula antes de gravar.
4. Teste com um procedimento antes de recalcular. Veja "Testar uma fórmula".

A fórmula padrão faz isto:
- `custo_hora` = custos fixos do mês ÷ horas produtivas do mês
- `custo_clinico` = custo_hora × tempo em horas
- `pro_labore` = pro-labore por hora × tempo em horas
- `custo_total` = custo de materiais + custo clínico + pro-labore
- `preco` = custo_total ÷ (1 − (impostos + taxa de cartão + margem) ÷ 100)

Regras da fórmula:
- Tem de 1 a 30 passos.
- Cada passo tem um nome próprio, com letras minúsculas, números e `_`, sem espaços. Não pode usar os nomes reservados pelo sistema.
- Um passo só pode usar variáveis cadastradas, as entradas do sistema e os passos anteriores.
- O último passo tem de se chamar `preco`, e só ele.
- Contas aceitas: números, nomes, parênteses, `+`, `-`, `*` e `/`. Comparações (maior que, menor que, igual) são aceitas, uma por vez.
- Funções aceitas:
  - `min(a, b, ...)`: menor valor.
  - `max(a, b, ...)`: maior valor.
  - `arredondar(valor, casas)`: arredonda, com de 0 a 6 casas, meio para cima.
  - `se(condição, valor_se_verdadeiro, valor_se_falso)`.
- Entradas do sistema, vindas da ficha técnica:
  - `custo_materiais`: soma de quantidade × custo de cada material.
  - `tempo_minutos`: tempo do procedimento em minutos.
  - `tempo_horas`: o mesmo tempo, em horas.
- Nenhuma outra conta ou função é aceita. O sistema não executa nada além disso.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Testar uma fórmula
O teste calcula um procedimento sem gravar nada. Serve para conferir a conta antes de recalcular.

1. Informe o código de um procedimento que tenha ficha técnica. Sem ficha, o sistema avisa.
2. Se quiser, informe um dentista, para usar os valores dele.
3. Escreva a fórmula que quer testar, ou deixe em branco para usar a fórmula padrão.
4. Veja o preço e a conta passo a passo: os materiais usados, o custo de cada um, as variáveis e de onde vieram (clínica ou dentista) e o resultado de cada passo.

Só o Administrador e o Gestor podem fazer isso. *Tela em construção.*

### Ver a conta de um preço calculado
Mostra como um preço de uma versão calculada foi formado: materiais, variáveis e passos da fórmula. É a mesma conta do teste, mas para o preço que já está na versão.

Só o Administrador e o Gestor podem ver. *Tela em construção.*

### Consultar o preço de um procedimento
1. Informe o código do procedimento.
2. Se souber, informe o dentista e o convênio do paciente.
3. Informe a data. Se não informar, o sistema usa hoje. Em uma data passada ou futura, o sistema usa a versão que valia naquele dia.
4. Veja o preço, a tabela e a versão de onde ele veio, e a explicação do caminho que o sistema seguiu para chegar a esse valor.

Essa consulta não grava nada. Serve para simular.

Se nenhuma tabela tiver o procedimento, o sistema avisa que o preço não foi encontrado e mostra por quais tabelas passou. Se não houver nenhuma tabela atribuída ao caso, ele avisa isso.

Todos os perfis com acesso ao módulo podem consultar. *Tela em construção.*

### Congelar o preço para um orçamento
1. Faça a consulta do procedimento, como acima.
2. Confirme. O sistema guarda o preço, a tabela, a versão, a data, o dentista e o convênio informados, a explicação do cálculo e quem fez o registro.
3. Guarde a identificação do registro. Com ela, você consulta o mesmo preço depois.

O preço congelado não muda, mesmo que a tabela seja alterada ou publicada de novo.

Administrador, Gestor, Dentista e Recepção podem congelar preços. *Tela em construção.*

## Bom saber

- Quando mais de uma tabela vale para o mesmo caso, vence a de menor número de prioridade. Por padrão, a ordem é: convênio do paciente (10), depois o dentista (20), depois a clínica (30). A clínica pode trocar esses números.
- Se um procedimento não estiver na tabela de maior prioridade, o sistema procura nas tabelas seguintes, uma por uma. Tabelas arquivadas e tabelas sem versão valendo na data são puladas.
- Uma tabela pode herdar de outra. Ela usa os preços da tabela de origem, somados ao ajuste da versão que está valendo, a menos que tenha preço próprio para aquele procedimento.
- Uma versão publicada não é alterada. Para corrigir um preço, abra um novo rascunho e publique de novo, com data de vigência.
- Mudar uma tabela não altera orçamentos já feitos. Eles ficam com o preço congelado.
- Na fórmula padrão, o "preço por dentro", impostos, taxa de cartão e margem são calculados sobre o preço de venda. Eles não são somados ao custo. Somar esses percentuais ao custo deixa o preço abaixo do necessário.
- Se a soma de impostos, taxa de cartão e margem chegar a 100%, o cálculo não tem solução. O procedimento aparece com erro no relatório.
- Preço máximo aceito: R$ 9.999.999.999,99.
- Por enquanto, o sistema não confere se o convênio informado existe. Confira o convênio antes de atribuir uma tabela a ele.
- Criar, alterar, publicar, importar, atribuir, remover e congelar preços fica registrado no [Histórico de ações](auditoria.md), com quem fez e quando. O mesmo vale para fichas técnicas, variáveis, fórmulas e recálculos. Quando você publica confirmando procedimentos de fora, o registro traz a lista deles.
- Se o seu perfil não puder fazer uma ação, o sistema não faz e informa que seu perfil não tem permissão.
- Previsto, ainda não disponível:
  - Repasse e comissão de dentistas (percentual ou valor fixo por procedimento), usando estas mesmas tabelas.
  - Regras de ajuste de preço: desconto à vista, acréscimo no parcelamento, arredondamento (ex.: final ,90) e preço mínimo.
  - Escolher quem vê custos e margens. Hoje, só Administrador e Gestor veem.
  - Escolher quais perfis podem criar e alterar tabelas. Hoje, só Administrador e Gestor podem.
  - Atribuir tabelas a unidades e campanhas. Hoje, a atribuição é para a clínica, para dentista ou para convênio.
  - Processamento de planilhas grandes em segundo plano, com acompanhamento do andamento.

## Perguntas frequentes

**Posso mudar um preço sem criar uma nova versão?**
Não. Você prepara um rascunho, altera os preços e publica. Assim fica claro a partir de que dia cada preço vale.

**Um orçamento antigo muda se eu alterar a tabela?**
Não. Quando o preço é congelado, o sistema guarda o valor, a tabela e a versão usados naquele momento.

**Por que não vejo a opção de criar ou alterar tabelas?**
Só o Administrador e o Gestor configuram tabelas. Os outros perfis consultam os preços.

**Quem vence quando um dentista tem uma tabela própria e a clínica tem outra?**
Vence a tabela com o menor número de prioridade. Por padrão, a tabela do convênio (10) vence a do dentista (20), e a do dentista vence a da clínica (30). A clínica pode definir outros números ao atribuir.

**Por que o sistema pede para recalcular antes de publicar?**
Porque algum custo, ficha técnica, variável ou a própria fórmula mudou depois do último cálculo. Recalcule o rascunho e publique de novo.

**Por que não vejo as fichas técnicas, os custos ou a fórmula?**
Esses dados são só do Administrador e do Gestor. Dentista e Recepção veem apenas os preços.

**Por que um procedimento ficou de fora do recálculo?**
Ele aparece no relatório com o motivo. O mais comum é um cálculo impossível, como divisão por zero, ou um valor fora do limite permitido. Confira a ficha técnica e as variáveis, e recalcule.

**Por que o sistema pediu confirmação para publicar?**
Porque a tabela calculada tem procedimentos que deram erro no último recálculo. Eles ficariam sem preço nesta tabela. Veja a lista. Se for possível, corrija e recalcule. Se preferir publicar assim mesmo, confirme.
