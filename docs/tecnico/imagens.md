---
modulo: imagens
atualizado_em: 1ee64af
---
# Imagens (exames de raio-X)

> Anexa arquivos DICOM ao paciente, guarda o arquivo como veio, extrai os metadados do cabeçalho e permite classificar (tipo, dentes, data) e invalidar, sem nunca apagar.

## Responsabilidades

- Recebe o upload de um arquivo DICOM por paciente, valida, calcula o SHA-256, grava no armazenamento (`app/core/storage.py`) e cria o registro.
- Lê só o cabeçalho com pydicom (`dicom.py:read`, `stop_before_pixels=True`) e guarda tags selecionadas em JSONB.
- Lista, detalha e devolve o arquivo original; classifica (PATCH) e invalida com motivo.
- **Fora do módulo:** visualizador de imagem, Orthanc/PACS e S3 (não existem; `models.py` e `storage.py` citam a Fase 5.3 e o PLANO). Cadastro do paciente fica em `pacientes`; atendimento em `prontuario`. A validação de dente FDI reaproveita `odontograma.regras:is_valid_tooth`.

## Modelo de dados

| Tabela | Tenant (RLS) | Papel |
|---|---|---|
| `imaging_exams` | sim | um exame (arquivo DICOM + metadados + classificação clínica) |

- FK composta `(patient_id, clinic_id)` para `patients` e `(encounter_id, patient_id, clinic_id)` para `encounters`: o atendimento precisa ser do mesmo paciente e da mesma clínica, garantido pelo banco.
- Unicidade `(clinic_id, patient_id, sha256)`: o mesmo arquivo não entra duas vezes no mesmo paciente (pode entrar em outro).
- CHECKs: `teeth` só aceita números FDI válidos (permanentes e decíduos), sem dimensão extra; `invalidated_at` e `invalidation_reason` são ambos nulos ou ambos preenchidos; `dicom_metadata` é objeto JSON; `sha256` é hex minúsculo de 64 caracteres.
- Gatilho `imaging_exam_guard` (migração `0021`): exame invalidado não sofre nenhum UPDATE; e, em exame válido, arquivo, paciente, atendimento, UIDs, `study_date`, nome DICOM, metadados e `uploaded_by` não mudam. Só podem mudar `kind`, `teeth`, `exam_date`, `notes` e os campos de invalidação.
- `odonto_app` perde DELETE e TRUNCATE na tabela (prontuário). As FKs para `users` usam `RESTRICT` porque o gatilho barraria um `SET NULL`.

## API

| Método | Rota | Papéis | O que faz |
|---|---|---|---|
| POST | `/imagens/pacientes/{patient_id}/exames` | admin, dentista, asb | upload multipart (`arquivo` + campos opcionais em português) |
| GET | `/imagens/pacientes/{patient_id}/exames` | admin, gestor, dentista, asb | lista; `incluir_invalidados=true` mostra os invalidados |
| GET | `/imagens/exames/{exam_id}` | admin, gestor, dentista, asb | detalhe com UIDs e `dicom_metadata` |
| GET | `/imagens/exames/{exam_id}/arquivo` | admin, gestor, dentista, asb | bytes originais (`application/dicom`, `Cache-Control: no-store`) |
| PATCH | `/imagens/exames/{exam_id}` | admin, dentista, asb | muda tipo, dentes, data e observação |
| POST | `/imagens/exames/{exam_id}/invalidar` | admin, dentista | invalida com motivo (3 a 300 caracteres) |

Recepção não acessa nada. Respostas fora do padrão: 413 (arquivo acima de `max_dicom_bytes`, tanto pelo middleware quanto por `router.py:_read_limited`), 422 para toda violação de regra (`service.RuleViolation`), 404 para `NotFound`.

## Regras de negócio e invariantes

- Só aceita DICOM válido: exige o preâmbulo `DICM` e `SOPInstanceUID` preenchido (`dicom.py:read`), porque o pydicom lê arquivos truncados só com avisos.
- Paciente inativo não recebe exame (`service.py:upload`).
- Duplicata é conferida por SHA-256 no serviço (422) além da unicidade no banco.
- Atendimento informado precisa ser do mesmo paciente (`service.py:upload`; reforçado pela FK composta).
- Tipo padrão vem da modalidade (`dicom.py:MODALITY_KIND`: PX panorâmica, IO periapical, CT tomografia, resto `outro`); a data padrão é a `StudyDate` do DICOM. O usuário pode sobrescrever.
- Dentes: FDI válido, sem repetição, gravados ordenados (`service.py:check_teeth`). Lista vazia vira `NULL`.
- Exame invalidado não é alterado nem reinvalidado (`service.py:_ensure_valid` e o gatilho).
- Nome do arquivo enviado é só rótulo: o `storage_key` é `<clinic_id>/<uuid>.dcm`, gerado no servidor (`storage.py:make_key`); `_clean_name` remove diretórios.
- `service.py:read_file` confere que a chave começa com o `clinic_id` do exame, e `storage.py:_path` valida o formato da chave por regex e que o caminho resolvido está dentro da raiz.

## Tenancy e auditoria

- Sempre `get_tenant_db`. Exame de outra clínica aparece como 404, pelo RLS.
- Auditoria com `entity_type="paciente"` e `entity_id` = paciente: `imagens.exame_anexado`, `imagens.exames_listados`, `imagens.exame_lido`, `imagens.exame_baixado`, `imagens.exame_alterado` (com os campos alterados), `imagens.exame_invalidado`. Leitura também é auditada. O commit é do router.

## Decisões

| Decisão | Motivo |
|---|---|
| Armazenamento atrás de `put/get/delete` em `core/storage.py`, em disco local (`STORAGE_DIR`, padrão `var/arquivos`) | trocar por S3 depois sem mexer no módulo; acesso sempre pela API, que confere papel e RLS |
| Gravação atômica (arquivo temporário + `fsync` + rename) | nunca deixar arquivo parcial sob a chave final |
| Não há exclusão; só invalidação com motivo | guarda do prontuário; envio errado some da listagem padrão mas continua guardado |
| Arquivo e metadados imutáveis no banco (gatilho) | a regra vale mesmo para código novo que esqueça de respeitá-la |
| Só o cabeçalho é lido, sem pixels | não há visualizador; o arquivo é devolvido íntegro para um visualizador externo |
| Limite de corpo maior só para o POST de exame (`limits.py:BodySizeLimitMiddleware`, `overrides` registrado em `main.py`) | o upload multipart seria recusado pelo limite global; o limite é `max_dicom_bytes` + 64 KB de envelope |

## Como estender

- **Novo tipo de exame:** acrescente em `models.py:ImageKind`, na tupla `KINDS` de `dicom.py` e, em nova migração, recrie o CHECK `kind_valid` (a `0021` tem a lista fixa).
- **Nova tag guardada:** inclua em `dicom.py:KEPT_TAGS`. Só vale para uploads novos, já que os metadados são imutáveis.
- **Trocar para S3:** implemente `put/get/delete` com a mesma assinatura em `core/storage.py`, mantendo o formato de chave. Se a chave mudar, ajuste `_KEY` e a checagem de prefixo em `service.py:read_file`.
- **Nova rota de upload com corpo grande:** registre o caminho em `overrides` no `main.py`; o override vale só para POST.

## Armadilhas

- A unicidade `(clinic, paciente, sha256)` não é tratada como erro de negócio na corrida. Dois uploads simultâneos do mesmo arquivo passam pela checagem do serviço e o segundo falha no banco com `IntegrityError`, que o handler global de `app/main.py` transforma em 409 (não 422). O arquivo ainda não foi gravado nesse ponto (o `flush` vem antes do `storage.put`).
- `dicom_patient_name` é guardado só para conferência visual: nada compara com o nome do paciente.
- O arquivo é gravado em `service.py:upload` depois do `flush` e antes do commit. Se o commit falhar, `router.py:upload_exam` apaga o arquivo. Se o processo cair entre os dois passos, sobra arquivo órfão sem limpeza automática.
- Exame invalidado continua baixável e detalhável (`read_file` e `get_exam` não conferem `invalidated_at`).
- `PATCH` com `notes: null` limpa a observação, mas `kind: null` é recusado (422). `ExamUpdate` não impede enviar `exam_date: null`, que limpa a data.
- O upload lê o arquivo inteiro em memória (até `max_dicom_bytes`, 30 MB por padrão); o Starlette também o grava em disco temporário antes da rota.
- Sem proxy reverso limitando o corpo, só o middleware protege o disco (aviso em `limits.py`).
