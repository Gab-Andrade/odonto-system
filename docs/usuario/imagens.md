---
modulo: imagens
atualizado_em: 3afacea
---
# Exames de imagem (raio-X)

> Guarda os raios-X e outros exames de imagem no prontuário de cada paciente, com o dente, a data e o tipo de cada exame.

## Quem usa

| Perfil | O que pode fazer |
|---|---|
| Administrador | Enviar, classificar, ver, baixar e invalidar exames |
| Dentista | Enviar, classificar, ver, baixar e invalidar exames |
| ASB (auxiliar de saúde bucal) | Enviar, classificar, ver e baixar exames. Não pode invalidar |
| Gestor | Ver e baixar exames. Não envia, não altera e não invalida |
| Recepção | Não tem acesso aos exames |

## O que dá para fazer

### Enviar um exame para o paciente
1. Abra o paciente e vá para a aba **Raio-X**.
2. Escolha o arquivo DICOM (.dcm) de uma imagem. Cada envio traz um exame.
3. Se quiser, escolha o tipo e informe os dentes. Se não escolher o tipo, o sistema sugere um.
4. Clique em **Enviar**. O sistema guarda o arquivo e registra quem enviou.

O sistema sugere o tipo pelo aparelho que gerou a imagem: panorâmica, tomografia ou periapical. Se o aparelho não for reconhecido, o tipo fica como "Outro". A data do exame vem do próprio arquivo. Você também pode:

- Informar os dentes pelo número FDI, separados por vírgula (ex.: 36,37).
- Ligar o exame a um atendimento do mesmo paciente.
- Escrever uma observação de até 1000 caracteres.

**Onde:** aba **Raio-X** da ficha do paciente. O envio aparece só para Administrador, Dentista e ASB; o Gestor vê os exames, mas não envia. Pela tela atual, a data vem do arquivo e não dá para ligar o exame a um atendimento.

### Classificar ou corrigir um exame
1. Escolha o exame.
2. Altere o tipo, os dentes, a data ou a observação.
3. Salve.

A classificação pode ser corrigida quantas vezes for preciso. O arquivo em si não muda. Um exame invalidado não pode mais ser alterado.

*Tela em construção.*

### Ver a lista de exames do paciente
A lista mostra os exames mais recentes primeiro. Cada exame mostra o tipo, os dentes, a data, a modalidade, a descrição do estudo, o tamanho e o nome do paciente gravado no arquivo. Esse nome ajuda a conferir se o exame é mesmo daquele paciente.

Os exames invalidados ficam escondidos, a menos que você peça para incluí-los. Marque **Mostrar invalidados** para vê-los na lista.

**Onde:** aba **Raio-X** da ficha do paciente, na lista de exames.

### Baixar o arquivo original
Você pode baixar o arquivo DICOM como foi enviado, para abri-lo em um visualizador de imagens no computador. Cada download fica registrado no histórico.

**Onde:** na lista de exames, botão **Baixar .dcm** de cada exame. Quem vê os exames também pode baixar. Ver a imagem dentro do sistema: *Tela em construção.*

### Invalidar um exame enviado por engano
Quem pode fazer isso são o Administrador e o Dentista.

1. Escolha o exame.
2. Escreva o motivo, entre 3 e 300 caracteres (ex.: "exame de outro paciente").
3. Confirme.

O exame sai da lista padrão e não pode mais ser alterado, mas continua guardado. Hoje o sistema não tem opção para apagar um exame nem para desfazer a invalidação.

**Onde:** na lista de exames, botão **Invalidar**. Ele aparece só para Administrador e Dentista, e só nos exames que ainda não foram invalidados. Uma caixa pede o motivo.

## Bom saber

- Hoje só entram arquivos DICOM (.dcm). Fotos JPEG e PNG de sensores estão previstas.
- O sistema lê só os dados do cabeçalho do arquivo e guarda a imagem como foi enviada. Ainda não é possível ver a imagem dentro do sistema. O visualizador de imagens está previsto.
- Cada envio é um arquivo. Tomografia com várias fatias num só exame está prevista.
- O sistema recusa o arquivo se ele não for DICOM, se estiver danificado ou vazio, se o tamanho passar do limite (a mensagem informa o limite), se trouxer dente fora da numeração FDI ou repetido, ou se o mesmo arquivo já foi enviado para este paciente.
- Não é possível enviar exames de um paciente inativo. Reative o cadastro antes.
- Se o armazenamento dos arquivos estiver fora do ar, o sistema mostra uma mensagem. Nesse caso o envio não é gravado, e o download não acontece. Tente de novo mais tarde.
- O sistema mostra o nome gravado no arquivo, mas não impede o envio se ele for diferente do nome do paciente. Confira antes de enviar.
- Os exames de uma clínica não aparecem para outra clínica.
- Toda consulta, envio, alteração, download e invalidação de exame fica registrada no Histórico de ações.

## Perguntas frequentes

**Posso enviar uma foto de sensor em JPG?**
Hoje não. Só entram arquivos DICOM (.dcm). Os formatos JPEG e PNG estão previstos.

**Enviei o exame do paciente errado. E agora?**
Peça a um Administrador ou a um Dentista para invalidar o exame, com o motivo. Depois envie o exame ao paciente certo. O exame errado sai da lista, mas continua guardado.

**Por que o sistema recusou o arquivo?**
Pode ser porque o arquivo não é DICOM, está danificado ou vazio, tem um dente fora da numeração FDI, passou do tamanho permitido, ou já foi enviado para este paciente. Se o paciente estiver inativo, reative o cadastro antes.

**Posso apagar um exame?**
Não. Você só pode invalidar o exame, e ele continua guardado.

**Por que não consigo enviar exames?**
Enviar exames é permitido ao Administrador, ao Dentista e ao ASB. O Gestor pode ver os exames, mas não enviar. A Recepção não tem acesso aos exames.
