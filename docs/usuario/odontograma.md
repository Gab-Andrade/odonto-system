---
modulo: odontograma
atualizado_em: 2f71133
---
# Odontograma

> Mostra o estado de cada dente e de cada face do paciente, em desenho 2D e em modelo 3D, e guarda o histórico de tudo o que foi marcado ou removido, com data e autor.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Ver o odontograma, o histórico, a arcada e a comparação antes e depois; marcar e remover dentes e faces; registrar a arcada; criar e alterar os itens da legenda |
| Gestor | Ver o odontograma, o histórico, a arcada e a comparação antes e depois; criar e alterar os itens da legenda |
| Dentista | Ver o odontograma, o histórico, a arcada e a comparação antes e depois; marcar e remover dentes e faces; registrar a arcada |
| ASB | Ver o odontograma, o histórico, a arcada e a comparação antes e depois; marcar e remover dentes e faces; registrar a arcada |
| Recepção | Não tem acesso ao odontograma |

(Perfis do sistema: Administrador, Gestor, Dentista, ASB (auxiliar de saúde bucal) e Recepção.)

## O que dá para fazer

### Ver a legenda da clínica

A legenda é a lista de itens que podem ser marcados no dente, como cárie, restauração ou implante. Cada item tem nome, cor, tipo e efeito no modelo 3D.

Na primeira vez que a clínica usa o odontograma, o sistema cria uma legenda padrão com 11 itens:

- **Patologia** (vermelho): Cárie (por face), Fratura (dente inteiro) e Ausente (dente inteiro).
- **Planejado** (laranja, o que ainda será feito): Restauração a fazer (por face), Tratamento de canal a fazer (dente inteiro) e Extração indicada (dente inteiro).
- **Realizado** (azul, o que já foi feito): Restauração (por face), Selante (por face), Tratamento de canal (dente inteiro), Coroa (dente inteiro) e Implante (dente inteiro).

Quem vê a legenda: Administrador, Gestor, Dentista e ASB. Você pode pedir a lista só com os itens ativos ou com todos, inclusive os desativados.

*Tela em construção.*

### Criar ou alterar um item da legenda

Quem pode: Administrador e Gestor.

1. Para criar um item novo, informe o nome, a cor, o tipo (patologia, planejado ou realizado), se ele vale para o dente inteiro ou por face, o efeito no modelo 3D e a ordem em que aparece.
2. Cada item tem um código próprio. Ele não pode repetir o código de outro item da clínica.
3. Para alterar um item existente, mude o nome, a cor, a ordem, o efeito no 3D ou ative e desative o item.
4. O tipo e a forma de marcar (dente inteiro ou por face) só podem ser mudados enquanto o item nunca foi usado. Depois de usado, crie outro item e desative o antigo.

Itens não são apagados. Quando não forem mais usados, desative-os. Criar ou alterar um item fica registrado no histórico de ações.

*Tela em construção.*

### Marcar um dente ou uma face

Quem pode: Administrador, Dentista e ASB.

1. Escolha o paciente. O cadastro precisa estar ativo.
2. Escolha o dente pela numeração de dois dígitos usada na odontologia (FDI). Os dentes permanentes vão de 11 a 48. Os dentes de leite vão de 51 a 85. Outros números são recusados.
3. Escolha o item da legenda.
4. Se o item é marcado por face, escolha a face (veja a seção "Bom saber"). Se ele vale para o dente inteiro, não informe face.
5. Se quiser, informe o atendimento que está aberto no prontuário e uma observação de até 500 caracteres.
6. Envie. Você pode enviar até 200 marcações de uma vez.

Se uma das marcações do envio for recusada, nenhuma delas é gravada. Corrija o item indicado e envie de novo.

O sistema recusa a marcação quando:

- o paciente está inativo;
- o item está desativado na legenda;
- o item já está marcado naquele dente ou face;
- o mesmo dente, face e item aparecem repetidos no mesmo envio;
- o atendimento não é deste paciente ou já está fechado;
- o item exige face e você não informou, ou não aceita face e você informou.

*Tela em construção.*

### Remover uma marcação

Quem pode: Administrador, Dentista e ASB.

Para tirar uma marcação do odontograma, registre a remoção daquele dente, face e item. A marcação some do odontograma atual, mas continua no histórico.

Só é possível remover o que está marcado. Tentar remover algo que não está marcado é recusado.

*Tela em construção.*

### Registrar a arcada do paciente

Quem pode: Administrador, Dentista e ASB.

A arcada é a lista de dentes que o paciente tem ou deve ter no odontograma. Ela pode ser de três tipos:

- **Permanente:** dentes de adulto.
- **Decídua:** dentes de leite.
- **Mista:** dentes de leite e de adulto juntos, comum entre 6 e 11 anos.

Para registrar:

1. Escolha o paciente.
2. Escolha o tipo de dentição.
3. Se for a permanente, escolha quais dos quatro dentes do siso (18, 28, 38 e 48) entram na arcada, de nenhum a todos. Se você não escolher, entram os quatro (32 dentes).
4. Se a boca do paciente não segue o padrão, você pode listar os dentes um a um, em vez de escolher o tipo e os sisos. Não use as duas opções juntas.
5. Se quiser, escreva uma observação de até 500 caracteres.

O sistema recusa a arcada quando:

- um número não é um dente válido;
- um dente aparece duas vezes;
- a lista tem mais de 52 dentes;
- a permanente tem dente de leite, ou a decídua tem dente de adulto;
- a mista não tem dente de leite e dente de adulto;
- um dente de leite e o adulto que o substitui aparecem juntos (ocupam a mesma posição);
- os sisos são informados para a decídua ou a mista.

A arcada não é apagada. Cada registro novo vale a partir do momento em que foi feito, e o último registro é o que vale. Você também pode ver a arcada como estava em uma data anterior.

Sem nenhum registro, o sistema sugere a arcada pela idade do paciente:

- até 5 anos: decídua;
- de 6 a 11 anos: mista típica;
- de 12 a 17 anos: permanente, sem sisos;
- 18 anos ou mais, ou sem data de nascimento: permanente, com os quatro sisos (32 dentes).

Dente perdido não muda a arcada. Para mostrar que o dente não existe mais, marque o item "Ausente" no dente.

*Tela em construção.*

### Ver o odontograma atual

Quem pode: Administrador, Gestor, Dentista e ASB.

O odontograma mostra cada dente com marcas. Para cada dente, aparecem:

- as marcações do dente inteiro;
- as marcações de cada face, com o nome clínico da face.

Só aparecem os dentes que têm alguma marcação.

Você também pode ver como o odontograma estava em uma data e hora anteriores. Isso ajuda a comparar o antes e o depois de um tratamento.

*Tela em construção.*

### Ver o odontograma em 2D e 3D

Quem pode: Administrador, Gestor, Dentista e ASB.

O sistema prepara uma única visão do odontograma que serve tanto para o desenho 2D (para registrar na cadeira) quanto para o modelo 3D (para mostrar ao paciente). Ela traz:

- a arcada do paciente, na ordem de leitura (de 18 a 11 e de 21 a 28 na parte de cima; de 48 a 41 e de 31 a 38 na parte de baixo);
- cada dente com as suas cinco faces (M, D, O, V e L) e a cor de cada uma;
- os dentes que devem ser ocultados no modelo 3D;
- a legenda apenas com os itens que aparecem no odontograma.

Você também pode ver essa visão como estava em uma data anterior.

*Tela em construção.* Visualização em 3D na tela: previsto.

### Comparar antes e depois

Quem pode: Administrador, Gestor, Dentista e ASB.

Escolha duas datas: o início (antes) e o fim (depois). Se não informar o fim, o sistema usa o momento atual. O início precisa ser anterior ao fim.

O resultado mostra:

- as marcações que entraram no período;
- as marcações que saíram no período;
- os dentes que mudaram.

*Tela em construção.*

### Ver o histórico de marcações

Quem pode: Administrador, Gestor, Dentista e ASB.

O histórico lista cada marcação e cada remoção do paciente, da mais recente para a mais antiga. Em cada linha aparecem a data, quem registrou, o dente, a face, o item, o atendimento (se houver) e a observação (se houver).

O histórico vem em páginas de até 500 registros por vez. O padrão são 100.

*Tela em construção.*

## Bom saber

- **Nada é apagado.** Cada marcação, remoção e registro de arcada fica guardado com data e autor. Para corrigir um erro, registre a remoção daquela marcação ou um novo registro de arcada.
- **Faces.** Por face, o sistema usa as letras M, D, O, V e L:
  - **M** e **D**: faces de contato com os dentes vizinhos. M é a face voltada para o meio do rosto e D é a face voltada para trás.
  - **O** é a face de mastigação. Nos dentes da frente ela aparece como **I** (incisal), que é a borda de corte.
  - **V** é a face voltada para os lábios ou para a bochecha.
  - **L** é a face voltada para a língua. Nos dentes de cima ela aparece como **P** (palatina).
  - Ao registrar, você pode usar I no lugar de O e P no lugar de L.
- **Cor de uma face ou de um dente.** Se a face tem marcações, a cor dela é a do item mais importante. Se não tem, vale a cor do item do dente inteiro. A ordem de importância é: patologia, depois planejado, depois realizado. Empatando, vale a ordem da legenda.
- **Efeito no 3D.** Cada item pode colorir o dente ou ocultá-lo no modelo 3D. Ocultar só vale para item de dente inteiro. Por padrão, "Ausente" oculta o dente e os demais coloridam.
- **Dente fora da arcada.** Você pode marcar um dente que não está na arcada do paciente. Ele aparece no odontograma, marcado como fora da arcada.
- **Item desativado.** Ele some das opções para novas marcações, mas as marcações antigas continuam aparecendo.
- **Paciente inativo.** Não recebe novas marcações. Reative o cadastro antes de marcar.
- **Atendimento aberto.** Quando você informa um atendimento, ele precisa ser deste paciente e estar aberto. Uma vez fechado, não recebe mais marcações.
- **Plano de tratamento.** Quando um procedimento do plano é marcado como feito, o odontograma é atualizado: o item "a fazer" sai e o item "feito" entra. Veja [Plano de tratamento e orçamento](tratamento.md).
- **Leitura é registrada.** Cada vez que alguém consulta o odontograma, o histórico, a arcada, a visão 2D e 3D ou a comparação de um paciente, isso fica no histórico de ações, para segurança e para a LGPD. A lista da legenda não é registrada, porque não tem dado de paciente.
- **Cada clínica só vê os próprios dados.**

## Perguntas frequentes

**Por que não consigo marcar um dente?**
Pode ser que o paciente esteja inativo, que o item esteja desativado, que a marcação já exista naquele dente ou face, ou que o atendimento escolhido esteja fechado. O sistema informa o motivo.

**Marquei a face errada. Como corrijo?**
Registre a remoção daquela marcação. Não é possível apagar o registro. A remoção fica no histórico junto com a marcação errada.

**Qual a diferença entre O e I?**
São a mesma face. Nos dentes da frente o nome clínico é incisal (I). Nos demais, é oclusal (O), a superfície de mastigação. O sistema mostra o nome certo para cada dente.

**Posso ver como estava o odontograma em uma data passada?**
Sim. O odontograma, a arcada e a visão 2D e 3D podem ser consultados para uma data e hora anteriores. Para comparar duas datas, use a comparação antes e depois.

**Um dente foi perdido. Preciso mudar a arcada?**
Não. A arcada descreve a dentição do paciente. Marque o item "Ausente" no dente.

**Por que a recepção não vê o odontograma?**
O perfil Recepção não tem permissão para acessar dados clínicos do paciente.

**Quem pode mudar a cor de uma marcação?**
Administrador e Gestor podem mudar a cor e o efeito no 3D de cada item da legenda. A mudança vale para todas as marcações desse item.
