---
modulo: pacientes
atualizado_em: 3afacea
---
# Cadastro de pacientes

> Guarda a ficha de cada paciente da clínica: dados pessoais, endereço, responsável (quando o paciente é menor), observações e os consentimentos para o uso dos dados.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador, Gestor, Dentista, ASB e Recepção | Buscar pacientes, cadastrar, alterar e consultar a ficha, e ver e registrar consentimentos. |

O cadastro é igual para toda a equipe. O conteúdo clínico tem regras próprias: a anamnese é vista por dentistas, ASB, gestor e administrador, mas não pela recepção (veja [Prontuário e anamnese](prontuario.md)). O mesmo vale para evolução clínica ([Prontuário](prontuario.md)) e odontograma ([Odontograma](odontograma.md)).

## O que dá para fazer

### Buscar um paciente

**Onde:** menu **Pacientes**, campo **Buscar**.

1. Digite parte do nome, o nome social, o CPF ou o telefone. A lista muda enquanto você digita.
2. Confira a lista. Cada linha mostra nome, nome social, idade, data de nascimento, telefone e só uma parte do CPF (por exemplo, ***.456.789-**).
3. Clique no paciente para abrir a ficha.

- **Por nome:** basta um trecho. Não importam acentos nem letras maiúsculas, e todas as palavras digitadas precisam aparecer no nome.
- **Por CPF ou telefone:** digite só os números, com pelo menos 4 dígitos. O CPF precisa ser digitado por inteiro. O telefone pode ser achado pelos últimos números.
- **Pacientes inativos** não aparecem na busca, a não ser que você marque **Incluir inativos**.
- A tela mostra até 50 pacientes por busca.

### Cadastrar um paciente

**Onde:** menu **Pacientes**, botão **+ Novo paciente**. Ao salvar, o sistema abre a ficha do paciente criado.

Informe pelo menos o nome completo e o telefone. Os outros dados são opcionais:

- Nome social, data de nascimento e sexo.
- CPF (precisa ser válido e não pode ser de outro paciente da clínica).
- Telefone alternativo e e-mail.
- Endereço: CEP, rua, número, complemento, bairro, cidade e estado (duas letras).
- Responsável: nome, CPF, telefone e parentesco.
- Observações (até 2.000 caracteres).

Os telefones devem ter de 8 a 15 números. Você pode digitá-los com parênteses ou traços: o sistema guarda só os números.

### Alterar a ficha

**Onde:** abra o paciente (menu **Pacientes**) e entre na aba **Cadastro**. Clique em **Editar**, no cartão **Dados do paciente**.

- Altere só o que precisa. Os outros dados continuam como estavam.
- Para apagar um dado opcional (por exemplo, o e-mail), deixe o campo vazio e salve.
- Nome completo e telefone não podem ficar vazios.
- Para tirar um paciente das buscas comuns, marque-o como inativo. A ficha continua guardada. Para voltar, marque-o como ativo. *Tela em construção: a tela de edição ainda não tem a opção Ativo.*
- Ao salvar, o sistema registra quais dados foram alterados, mas não guarda os valores antigos nem os novos.

### Ver e registrar consentimentos

**Onde:** abra o paciente (menu **Pacientes**), entre na aba **Cadastro** e veja o cartão **Consentimentos (LGPD)**.

As finalidades são três:
- **Tratamento de dados:** uso dos dados pessoais e de saúde para o atendimento.
- **Comunicação:** lembretes e contato por WhatsApp ou e-mail.
- **Uso de imagem:** fotos para divulgação.

**Ver:** a tela mostra a situação atual de cada finalidade: *Dado* (com a data e quem deu), *Revogado* ou *Nunca registrado*. *Tela em construção: o histórico completo de cada finalidade ainda não aparece na tela.*

**Registrar:** em cada finalidade, clique em **Registrar** para dar o consentimento, ou em **Revogar** para retirá-lo. A tela preenche sozinha quem deu o consentimento: o responsável, se o paciente tem responsável cadastrado; caso contrário, o próprio paciente.

*Tela em construção: a escolha da versão do termo e a observação ainda não aparecem na tela.*

Cada registro é um novo evento no histórico. Um registro não pode ser apagado pelo sistema.

Para paciente menor de 18 anos, o consentimento é dado pelo responsável, que precisa estar cadastrado.

## Bom saber

- **Menor de 18 anos:** a ficha precisa de um responsável com nome. Sem isso, o sistema não salva o cadastro, nem a troca da data de nascimento que deixa o paciente menor.
- **CPF do responsável:** não pode ser igual ao CPF do próprio paciente.
- **CPF repetido:** cada clínica tem os próprios pacientes, e não existem dois pacientes com o mesmo CPF na mesma clínica.
- **Data de nascimento:** não pode estar no futuro nem ser anterior a 1900.
- **Quando o sistema recusa um dado,** ele mostra o motivo, por exemplo: "Já existe paciente com este CPF na clínica."
- **Registro de ações (LGPD):** abrir uma ficha, fazer uma busca, consultar consentimentos, cadastrar, alterar ou registrar um consentimento deixa registro em Histórico de ações, com quem fez e quando. Na busca, fica só a quantidade de resultados. O que foi digitado não é guardado, porque pode ser um CPF ou um telefone.
- **Privacidade entre clínicas:** a ficha de um paciente de outra clínica aparece como "Paciente não encontrado.". Cada clínica vê só os próprios pacientes.

## Perguntas frequentes

**Posso apagar um paciente cadastrado por engano?**
Não pelo sistema. A ficha fica guardada. Para tirar o paciente das buscas, marque-o como inativo (a tela de edição ainda não tem essa opção).

**Por que a busca não encontra um paciente?**
Confira se ele não está inativo. Para CPF, digite os 11 números. Para telefone, digite pelo menos 4 números.

**Registrei um consentimento errado. Como corrijo?**
Não é possível apagar o registro. Registre um novo evento com a situação correta, clicando em **Revogar** ou **Registrar**. O histórico mostra os dois, e a situação atual é a do registro mais recente.
