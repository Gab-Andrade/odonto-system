---
modulo: estoque
atualizado_em: 3afacea
---
# Estoque de materiais

> Controla os materiais da clínica por lote e validade: quanto há de cada um, quando cada lote vence, o que saiu para cada paciente e quando é hora de repor. Também guarda o cadastro, com a unidade de uso e o custo de cada material.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Cadastrar, alterar, desativar e reativar materiais. Ver custos. Dar entrada, dar saída e fazer inventário. Ver o histórico de movimentos e o rastreio de pacientes. |
| Gestor | Igual ao Administrador. |
| Dentista | Consultar materiais, saldos, alertas e lotes, sem ver custos. Consultar o que foi usado em um paciente. Os materiais de um procedimento saem sozinhos quando ele marca o procedimento como realizado no próprio atendimento. |
| ASB | Consultar materiais, saldos, alertas e lotes, sem ver custos. Dar entrada e saída de materiais, sem informar custo. Consultar o que foi usado em um paciente. |
| Recepção | Não tem acesso ao estoque. |

## O que dá para fazer

### Cadastrar um material
Onde: menu Estoque, aba Materiais, botão **+ Novo material**.

Só Administrador e Gestor cadastram materiais. Informe:
1. O nome do material (até 150 letras).
2. A unidade de uso, como `un`, `ml`, `g`, `cx`, `par` ou `tubo` (até 20 letras).
3. A categoria, se quiser (até 100 letras). É opcional.
4. O custo por unidade de uso, com até 4 casas decimais. O valor não pode ser negativo.
5. O estoque mínimo, se quiser. É a quantidade abaixo da qual o sistema avisa que é hora de repor. Sem mínimo, o material nunca aparece como abaixo do mínimo.

O sistema não aceita dois materiais com o mesmo nome. Não faz diferença entre letras maiúsculas e minúsculas, então "Luva" e "luva" são o mesmo nome.

### Consultar a lista de materiais
Onde: menu Estoque, aba Materiais (só Administrador e Gestor). Marque **Mostrar desativados** para ver também os inativos. Os demais perfis veem os materiais pela aba Saldos e lotes.

Todos os perfis, exceto a Recepção, veem a lista de materiais em ordem de nome.
- Por padrão, a lista mostra só os materiais ativos.
- Quem pede também os inativos vê os desativados.
- O custo aparece só para Administrador e Gestor. Para os outros perfis, a lista mostra nome, unidade, categoria, estoque mínimo e se o material está ativo.

### Ver os dados de um material

Todos os perfis, exceto a Recepção, abrem um material da lista para ver os seus dados. O custo segue a mesma regra da lista: só Administrador e Gestor o veem.

Se o material não existir na sua clínica, o sistema avisa que ele não foi encontrado.

### Alterar um material
Onde: menu Estoque, aba Materiais, botão **Editar** na linha do material.

Só Administrador e Gestor alteram um material. É possível mudar o nome, a unidade, a categoria, o custo, o estoque mínimo (inclusive retirá-lo) e a situação (ativo ou inativo). Você muda só o que precisa. O restante continua como está.

As mesmas regras do cadastro valem para a alteração. Por exemplo, você não consegue dar a um material um nome que já existe em outro.

### Desativar ou reativar um material
Onde: menu Estoque, aba Materiais, **Editar** e depois **Desativar** (ou **Reativar**, com **Mostrar desativados** marcado).

Em vez de apagar, o sistema desativa o material. Para isso, Administrador ou Gestor altera a situação do material para inativo. Para voltar a usá-lo, basta mudar para ativo.

### Dar entrada de materiais (compra ou reposição)
Onde: menu Estoque, aba Saldos e lotes, botão **+ Entrada de material** no topo, ou **Entrada** no cartão do material (já vem com ele escolhido). O campo de custo só aparece para Administrador e Gestor.

Administrador, Gestor e ASB dão entrada. Cada entrada cria um **lote**, que é um conjunto do mesmo material que chegou junto. Informe:
1. O material. Ele precisa estar ativo.
2. A quantidade recebida, maior que zero, com até 4 casas decimais.
3. O custo por unidade nesta compra. **Administrador e Gestor informam esse valor, e ele é obrigatório para eles.** A ASB não informa custo: o lote entra pelo custo atual do material.
4. Opcionais: código do lote, data de validade, fornecedor e data de recebimento. Se não informar a data de recebimento, o sistema usa a data de hoje. Ela não pode ser futura.

Sem data de validade, o lote sai por último nos procedimentos.

**Custo médio.** Quando Administrador ou Gestor dá entrada, o custo do material passa a ser a média dos custos de todos os lotes com saldo, pesada pela quantidade de cada um. Exemplo: se você tem 10 unidades a R$ 2,00 e recebe mais 10 a R$ 3,00, o custo passa a ser R$ 2,50.

### Dar saída de materiais (perda, vencido ou uso fora de procedimento)
Onde: menu Estoque, aba Saldos e lotes, botão **Saída** na linha do lote.

Administrador, Gestor e ASB dão saída. Informe:
1. O lote de onde o material saiu.
2. A quantidade. Ela não pode ser maior que o saldo do lote.
3. O motivo, obrigatório, até 300 letras. Por exemplo: "perda na abertura" ou "vencido".

Um lote vencido aceita saída. É assim que você tira do saldo o material que venceu.

### Fazer inventário (acertar o saldo de um lote)
Onde: menu Estoque, aba Saldos e lotes, botão **Inventário** na linha do lote.

Só Administrador e Gestor fazem inventário. Informe a quantidade que você contou no lote e o motivo. O sistema calcula a diferença e a registra como ajuste. Se a contagem bater com o saldo, nada é registrado.

### Ver saldos e alertas
Onde: menu Estoque, aba Saldos e lotes. Use **Buscar material** para achar pelo nome e marque **Só o que pede atenção** para ver apenas os materiais com alerta. Os alertas aparecem como etiquetas no cartão: *abaixo do mínimo*, *lote vencido* ou *vence em breve*.

Todos os perfis, exceto a Recepção, veem o saldo de cada material. Para cada um, aparecem o saldo total, o estoque mínimo, se está abaixo do mínimo e os lotes com saldo.

Cada lote mostra a situação da validade:
- **ok**: vence depois de 30 dias.
- **vence em breve**: vence em até 30 dias, inclusive hoje.
- **vencido**: a validade já passou.
- **sem validade**: o lote não tem data de validade.

Os alertas são:
- o material está abaixo do estoque mínimo;
- o material tem algum lote vencido ou que vence em breve.

Você pode pedir só os materiais com alerta. Por padrão, a lista mostra só os materiais ativos.

O custo de cada lote aparece só para Administrador e Gestor.

### Ver o histórico de movimentos
Onde: menu Estoque, aba Movimentos. Escolha um material para filtrar, ou deixe em *Todos* para ver os 200 mais recentes.

Só Administrador e Gestor veem o histórico. Ele lista entradas, saídas, ajustes e baixas por procedimento, do mais recente para o mais antigo. Você pode filtrar por material ou por lote. Por padrão, mostra os 200 movimentos mais recentes (no máximo 500 de uma vez).

Cada consulta ao histórico fica registrada no [histórico de ações](auditoria.md).

### Ver o que foi usado em um paciente (rastreio)
*Tela em construção.*

Administrador, Gestor, Dentista e ASB consultam o rastreio de um paciente. Ele mostra cada material usado nele, com o lote, a validade, a quantidade e a data. Serve para saber, por exemplo, qual lote de implante foi colocado e até quando ele era válido.

Cada consulta ao rastreio fica registrada no [histórico de ações](auditoria.md).

### Baixa automática ao realizar um procedimento

Você não dá baixa à parte. Quando o dentista do atendimento marca um item do [plano de tratamento](tratamento.md) como realizado, o sistema:
1. Lê a ficha técnica do procedimento, que diz quais materiais e quantidades ele usa. A ficha é definida na [precificação](precificacao.md). Se o procedimento não tiver ficha, nada sai do estoque.
2. Para cada material, tira a quantidade do lote que vence primeiro.
3. Não usa lotes vencidos.
4. Se faltar material, dá baixa do que houver e mostra um aviso: "Estoque insuficiente de ...: faltou ...". O procedimento é registrado do mesmo jeito.

Em cada baixa, o sistema guarda o paciente, o item do plano e o lote usado. Por isso o rastreio mostra o lote de cada paciente.

## Bom saber

- **A ordem dos lotes segue a validade.** Sai primeiro o lote que vence antes. Lote sem validade sai por último. Entre lotes com a mesma validade, sai o que chegou primeiro.
- **Lote vencido não sai em procedimento.** Mas ele continua no saldo do material até você dar saída ou fazer inventário. Por isso, o saldo total pode parecer maior do que o que está bom para uso.
- **O sistema aceita o cadastro de um lote já vencido,** mas ele nunca é usado em procedimento. Use a saída para dar baixa nele.
- **Falta de material não impede o procedimento.** O aviso aparece para a equipe, e a reposição fica a cargo da clínica.
- **Não há como apagar entradas, saídas, ajustes ou baixas.** Para corrigir um erro, use um ajuste de inventário ou uma saída com motivo.
- **Cada entrada, saída e ajuste fica registrado** no [histórico de ações](auditoria.md), com o nome de quem fez e a data.
- **Material desativado não recebe entrada.** Reative o material antes de dar entrada.
- **Lote com saldo zero sai da lista de saldos,** mas continua no histórico de movimentos.
- **Cadastro e custo.** Cada cadastro e cada alteração ficam registrados no [histórico de ações](auditoria.md). Mudar o custo de um material não muda os preços sozinho. Os preços já publicados continuam os mesmos. Para o novo custo entrar nos preços, o Gestor abre uma nova versão da tabela calculada e manda recalcular. Se o custo mudar depois do recálculo e antes da publicação, o sistema não deixa publicar e pede um novo recálculo. Ver [Tabelas de preço](precificacao.md).
- **Cada clínica só vê os próprios dados.** Materiais, lotes e movimentos de outras clínicas não aparecem.

## Perguntas frequentes

**Por que eu não vejo o custo dos materiais?**
Só Administrador e Gestor veem o custo, tanto no cadastro quanto nos lotes. Os demais perfis veem o cadastro e o saldo sem esse valor.

**Por que não consigo apagar um material?**
O sistema não apaga materiais, porque eles podem estar em fichas técnicas e cálculos de preço. Desative o material para tirá-lo do uso no dia a dia.

**Desativei um material por engano. Como volto atrás?**
Peça a um Administrador ou Gestor para alterar a situação do material para ativo.

**Por que o sistema não aceitou o nome do material?**
Já existe outro material com esse nome na clínica, sem diferença entre maiúsculas e minúsculas. Escolha outro nome ou altere o existente.

**Um procedimento foi realizado, mas o sistema avisou que faltou material. E agora?**
O procedimento continua registrado. Dê entrada na reposição assim que ela chegar. Se o saldo ficou diferente do que existe na prateleira, o Gestor pode fazer um inventário para acertá-lo.

**Por que um lote vencido ainda aparece no saldo?**
Ele continua no estoque até você dar saída com motivo ou fazer um inventário. Ele só deixa de ser usado em procedimentos.

**Por que um material não aparece como abaixo do mínimo?**
Ele pode não ter estoque mínimo cadastrado. Sem mínimo, o sistema não gera esse alerta. Peça a um Administrador ou Gestor para informar o mínimo na alteração do material.
