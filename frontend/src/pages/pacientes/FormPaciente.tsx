import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, ok, type Schemas } from "../../api/client";
import Modal from "../../components/Modal";
import { AreaTexto, Aviso, Botao, Campo, Selecao } from "../../components/ui";
import { idade } from "../../lib/datas";

type Paciente = Schemas["PatientOut"];

const CAMPOS = [
  "full_name",
  "social_name",
  "birth_date",
  "sex",
  "cpf",
  "phone",
  "phone_alt",
  "email",
  "zip_code",
  "street",
  "number",
  "complement",
  "district",
  "city",
  "state",
  "guardian_name",
  "guardian_cpf",
  "guardian_phone",
  "guardian_relationship",
  "notes",
] as const;
type Chave = (typeof CAMPOS)[number];
type Valores = Record<Chave, string>;

function inicial(p?: Paciente): Valores {
  const v = {} as Valores;
  for (const c of CAMPOS) v[c] = ((p?.[c] as string | null | undefined) ?? "").toString();
  return v;
}

/** Cadastro e edição do paciente. Na edição, só os campos alterados vão para a API. */
export default function FormPaciente({
  aberto,
  aoFechar,
  aoSalvar,
  paciente,
}: {
  aberto: boolean;
  aoFechar: () => void;
  aoSalvar?: (id: string) => void;
  paciente?: Paciente;
}) {
  const cliente = useQueryClient();
  const [v, setV] = useState<Valores>(() => inicial(paciente));
  const [erro, setErro] = useState<string | null>(null);
  const menor = (idade(v.birth_date || null) ?? 99) < 18;

  const salvar = useMutation({
    mutationFn: async () => {
      if (!paciente) {
        const corpo = Object.fromEntries(
          CAMPOS.filter((c) => v[c].trim() !== "").map((c) => [c, v[c].trim()]),
        );
        return ok(await api.POST("/pacientes", { body: corpo as Schemas["PatientCreate"] }));
      }
      const original = inicial(paciente);
      const mudancas = Object.fromEntries(
        CAMPOS.filter((c) => v[c] !== original[c]).map((c) => [c, v[c].trim() || null]),
      );
      return ok(
        await api.PATCH("/pacientes/{patient_id}", {
          params: { path: { patient_id: paciente.id } },
          body: mudancas as Schemas["PatientUpdate"],
        }),
      );
    },
    onSuccess: (p) => {
      cliente.invalidateQueries({ queryKey: ["pacientes"] });
      cliente.setQueryData(["paciente", p.id], p);
      aoFechar();
      aoSalvar?.(p.id);
    },
    onError: (e) => setErro(e.message),
  });

  function campo(c: Chave) {
    return { value: v[c], onChange: (e: { target: { value: string } }) => setV({ ...v, [c]: e.target.value }) };
  }

  function enviar(ev: FormEvent) {
    ev.preventDefault();
    setErro(null);
    salvar.mutate();
  }

  return (
    <Modal titulo={paciente ? "Editar cadastro" : "Novo paciente"} aberto={aberto} aoFechar={aoFechar} largura="max-w-2xl">
      <form onSubmit={enviar} className="flex flex-col gap-4">
        {erro && <Aviso tom="perigo">{erro}</Aviso>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Nome completo *" required {...campo("full_name")} />
          <Campo rotulo="Nome social" {...campo("social_name")} />
          <Campo rotulo="Telefone *" required inputMode="tel" placeholder="(11) 98765-4321" {...campo("phone")} />
          <Campo rotulo="Data de nascimento" type="date" {...campo("birth_date")} />
          <Selecao rotulo="Sexo" {...campo("sex")}>
            <option value="">—</option>
            <option value="feminino">Feminino</option>
            <option value="masculino">Masculino</option>
            <option value="intersexo">Intersexo</option>
          </Selecao>
          <Campo rotulo="CPF" inputMode="numeric" {...campo("cpf")} />
          <Campo rotulo="E-mail" type="email" {...campo("email")} />
          <Campo rotulo="Outro telefone" inputMode="tel" {...campo("phone_alt")} />
        </div>

        <fieldset className={`grid gap-3 rounded-lg border p-3 sm:grid-cols-2 ${menor ? "border-alerta" : "border-borda"}`}>
          <legend className="px-1 text-sm font-semibold">
            Responsável {menor && <span className="text-alerta">(obrigatório para menor de 18)</span>}
          </legend>
          <Campo rotulo="Nome do responsável" required={menor} {...campo("guardian_name")} />
          <Campo rotulo="Parentesco" placeholder="mãe, pai…" {...campo("guardian_relationship")} />
          <Campo rotulo="Telefone do responsável" inputMode="tel" {...campo("guardian_phone")} />
          <Campo rotulo="CPF do responsável" inputMode="numeric" {...campo("guardian_cpf")} />
        </fieldset>

        <details className="rounded-lg border border-borda p-3">
          <summary className="min-h-8 cursor-pointer text-sm font-semibold">Endereço</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <Campo rotulo="CEP" inputMode="numeric" {...campo("zip_code")} />
            <Campo rotulo="Rua" className="sm:col-span-2" {...campo("street")} />
            <Campo rotulo="Número" {...campo("number")} />
            <Campo rotulo="Complemento" {...campo("complement")} />
            <Campo rotulo="Bairro" {...campo("district")} />
            <Campo rotulo="Cidade" className="sm:col-span-2" {...campo("city")} />
            <Campo rotulo="UF" maxLength={2} {...campo("state")} />
          </div>
        </details>

        <AreaTexto rotulo="Observações" {...campo("notes")} />

        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao type="submit" carregando={salvar.isPending}>
            Salvar
          </Botao>
        </div>
      </form>
    </Modal>
  );
}
