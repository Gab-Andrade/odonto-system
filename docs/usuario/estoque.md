---
modulo: estoque
atualizado_em: 6363519
---
# Estoque de materiais

> Guarda o cadastro dos materiais que a clínica usa (luvas, resinas, anestésicos, e assim por diante), com a unidade de uso e o custo de cada um. Esse custo alimenta os cálculos de preço da clínica.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Cadastrar, alterar, desativar e reativar materiais. Ver o custo de cada um. |
| Gestor | Cadastrar, alterar, desativar e reativar materiais. Ver o custo de cada um. |
| Dentista | Consultar a lista de materiais e os dados de cada um, sem ver o custo. |
| ASB | Consultar a lista de materiais e os dados de cada um, sem ver o custo. |
| Recepção | Não tem acesso ao cadastro de materiais. |

## O que dá para fazer

### Cadastrar um material
*Tela em construção.*

Só Administrador e Gestor cadastram materiais. Informe:
1. O nome do material (até 150 letras).
2. A unidade de uso, como `un`, `ml`, `g`, `cx`, `par` ou `tubo` (até 20 letras).
3. A categoria, se quiser (até 100 letras). É opcional.
4. O custo por unidade de uso, com até 4 casas decimais. O valor não pode ser negativo.

O sistema não aceita dois materiais com o mesmo nome. Não faz diferença entre letras maiúsculas e minúsculas, então "Luva" e "luva" são o mesmo nome.

### Consultar a lista de materiais
*Tela em construção.*

Todos os perfis, exceto a Recepção, veem a lista de materiais em ordem de nome.
- Por padrão, a lista mostra só os materiais ativos.
- Quem pede também os inativos vê os desativados.
- O custo aparece só para Administrador e Gestor. Para os outros perfis, a lista mostra nome, unidade, categoria e se o material está ativo.

### Ver os dados de um material
*Tela em construção.*

Todos os perfis, exceto a Recepção, abrem um material da lista para ver os seus dados. O custo segue a mesma regra da lista: só Administrador e Gestor o veem.

Se o material não existir na sua clínica, o sistema avisa que ele não foi encontrado.

### Alterar um material
*Tela em construção.*

Só Administrador e Gestor alteram um material. É possível mudar o nome, a unidade, a categoria, o custo e a situação (ativo ou inativo). Você muda só o que precisa. O restante continua como está.

As mesmas regras do cadastro valem para a alteração. Por exemplo, você não consegue dar a um material um nome que já existe em outro.

### Desativar ou reativar um material
*Tela em construção.*

Em vez de apagar, o sistema desativa o material. Para isso, Administrador ou Gestor altera a situação do material para inativo. Para voltar a usá-lo, basta mudar para ativo.

## Bom saber

- **Não é possível apagar um material.** Desative-o. Assim, as fichas técnicas e os cálculos de preço que já usam o material continuam funcionando.
- **Material inativo não entra em novas fichas técnicas.** Na área de precificação, a ficha de um procedimento só aceita materiais ativos. Ver [Tabelas de preço](precificacao.md).
- **Mudar o custo de um material não muda os preços sozinho.** Os preços já publicados continuam os mesmos. Para o novo custo entrar nos preços, o Gestor abre uma nova versão da tabela calculada e manda recalcular. Se o custo mudar depois do recálculo e antes da publicação, o sistema não deixa publicar e pede um novo recálculo. Assim, nenhum preço é publicado com custo antigo. Ver [Tabelas de preço](precificacao.md).
- **Cada cadastro e cada alteração ficam registrados** no [histórico de ações](auditoria.md), com o nome de quem fez e a data.
- **Cada clínica só vê os próprios materiais.** Materiais de outras clínicas não aparecem na sua lista.
- **Previsto:** controle de quantidade em estoque, lotes e datas de validade, baixa automática do estoque ao realizar um procedimento e alertas de estoque baixo ou de lote perto do vencimento. Nada disso está disponível ainda.

## Perguntas frequentes

**Por que eu não vejo o custo dos materiais?**
Só Administrador e Gestor veem o custo. Os demais perfis veem o cadastro sem esse valor.

**Por que não consigo apagar um material?**
O sistema não apaga materiais, porque eles podem estar em fichas técnicas e cálculos de preço. Desative o material para tirá-lo do uso no dia a dia.

**Desativei um material por engano. Como volto atrás?**
Peça a um Administrador ou Gestor para alterar a situação do material para ativo.

**Por que o sistema não aceitou o nome do material?**
Já existe outro material com esse nome na clínica, sem diferença entre maiúsculas e minúsculas. Escolha outro nome ou altere o existente.
