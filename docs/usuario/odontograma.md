---
modulo: odontograma
atualizado_em: 02cafc0
---
# Odontograma

> Mostra o estado de cada dente e de cada face do paciente, e guarda o histórico de tudo o que foi marcado ou removido, com data e autor.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Ver o odontograma e o histórico, marcar e remover dentes e faces, e criar ou alterar os itens da legenda |
| Gestor | Ver o odontograma e o histórico, e criar ou alterar os itens da legenda |
| Dentista | Ver o odontograma e o histórico, e marcar e remover dentes e faces |
| ASB | Ver o odontograma e o histórico, e marcar e remover dentes e faces |
| Recepção | Não tem acesso ao odontograma |

## O que dá para fazer

### Ver a legenda da clínica

A legenda é a lista de itens que podem ser marcados no dente, como cárie, restauração ou implante. Cada item tem nome, cor e tipo.

Na primeira vez que a clínica usa o odontograma, o sistema cria uma legenda padrão com 11 itens:

- **Patologia** (vermelho): Cárie (por face), Fratura (dente inteiro) e Ausente (dente inteiro).
- **Planejado** (laranja, o que ainda será feito): Restauração a fazer (por face), Tratamento de canal a fazer (dente inteiro) e Extração indicada (dente inteiro).
- **Realizado** (azul, o que já foi feito): Restauração (por face), Selante (por face), Tratamento de canal (dente inteiro), Coroa (dente inteiro) e Implante (dente inteiro).

Quem vê a legenda: Administrador, Gestor, Dentista e ASB. Você pode pedir a lista só com os itens ativos ou com todos, inclusive os desativados.

*Tela em construção.*

### Criar ou alterar um item da legenda

Quem pode: Administrador e Gestor.

1. Para criar um item novo, informe o nome, a cor, o tipo (patologia, planejado ou realizado), se ele vale para o dente inteiro ou por face, e a ordem em que aparece.
2. Cada item tem um código próprio. Ele não pode repetir o código de outro item da clínica.
3. Para alterar um item existente, mude o nome, a cor, a ordem ou ative e desative o item.
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

### Ver o odontograma atual

Quem pode: Administrador, Gestor, Dentista e ASB.

O odontograma mostra cada dente com marcas. Para cada dente, aparecem:

- as marcações do dente inteiro;
- as marcações de cada face, com o nome clínico da face.

Só aparecem os dentes que têm alguma marcação.

Você também pode ver como o odontograma estava em uma data e hora anteriores. Isso ajuda a comparar o antes e o depois de um tratamento.

*Tela em construção.*

### Ver o histórico de marcações

Quem pode: Administrador, Gestor, Dentista e ASB.

O histórico lista cada marcação e cada remoção do paciente, da mais recente para a mais antiga. Em cada linha aparecem a data, quem registrou, o dente, a face, o item, o atendimento (se houver) e a observação (se houver).

O histórico vem em páginas de até 500 registros por vez. O padrão são 100.

*Tela em construção.*

## Bom saber

- **Nada é apagado.** Cada marcação e cada remoção fica registrada com data e autor. Para corrigir um erro, registre a remoção daquela marcação.
- **Faces.** Por face, o sistema usa as letras M, D, O, V e L:
  - **M** e **D**: faces de contato com os dentes vizinhos. M é a face voltada para o meio do rosto e D é a face voltada para trás.
  - **O** é a face de mastigação. Nos dentes da frente ela aparece como **I** (incisal), que é a borda de corte.
  - **V** é a face voltada para os lábios ou para a bochecha.
  - **L** é a face voltada para a língua. Nos dentes de cima ela aparece como **P** (palatina).
  - Ao registrar, você pode usar I no lugar de O e P no lugar de L.
- **Item desativado.** Ele some das opções para novas marcações, mas as marcações antigas continuam aparecendo.
- **Paciente inativo.** Não recebe novas marcações. Reative o cadastro antes de marcar.
- **Atendimento aberto.** Quando você informa um atendimento, ele precisa ser deste paciente e estar aberto. Uma vez fechado, não recebe mais marcações.
- **Leitura é registrada.** Cada vez que alguém consulta o odontograma ou o histórico de um paciente, isso fica no histórico de ações, para segurança e para a LGPD.
- **Cada clínica só vê os próprios dados.**
- **Previsto:** transformar um achado do odontograma em item do plano de tratamento, que depois vira orçamento.

## Perguntas frequentes

**Por que não consigo marcar um dente?**
Pode ser que o paciente esteja inativo, que o item esteja desativado, que a marcação já exista naquele dente ou face, ou que o atendimento escolhido esteja fechado. O sistema informa o motivo.

**Marquei a face errada. Como corrijo?**
Registre a remoção daquela marcação. Não é possível apagar o registro. A remoção fica no histórico junto com a marcação errada.

**Qual a diferença entre O e I?**
São a mesma face. Nos dentes da frente o nome clínico é incisal (I). Nos demais, é oclusal (O), a superfície de mastigação. O sistema mostra o nome certo para cada dente.

**Posso ver como estava o odontograma em uma data passada?**
Sim, o odontograma pode ser consultado para uma data e hora anteriores.

**Por que a recepção não vê o odontograma?**
O perfil Recepção não tem permissão para acessar dados clínicos do paciente.

**Quem pode mudar a cor de uma marcação?**
Administrador e Gestor podem alterar a cor dos itens da legenda.
