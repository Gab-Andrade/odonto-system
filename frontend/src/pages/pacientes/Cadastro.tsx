import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok, type Schemas } from "../../api/client";
import { Aviso, Botao, Cartao, Carregando, ErroCarga, Etiqueta } from "../../components/ui";
import { dataBR, dataHoraBR } from "../../lib/datas";
import FormPaciente from "./FormPaciente";

type Paciente = Schemas["PatientOut"];
type Finalidade = Schemas["ConsentPurpose"];

const FINALIDADES: Record<Finalidade, string> = {
  tratamento_dados: "Tratamento de dados pessoais e de saúde",
  comunicacao: "Lembretes e contato (WhatsApp/e-mail)",
  uso_imagem: "Uso de imagem (fotos para divulgação)",
};

function Linha({ rotulo, valor }: { rotulo: string; valor?: string | null }) {
  return (
    <div className="flex flex-col py-1">
      <dt className="text-xs text-texto-suave">{rotulo}</dt>
      <dd className="text-sm">{valor || "—"}</dd>
    </div>
  );
}

export default function Cadastro({ paciente: p }: { paciente: Paciente }) {
  const [editando, setEditando] = useState(false);
  const endereco = [p.street, p.number, p.complement, p.district, p.city, p.state]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Cartao titulo="Dados do paciente" acoes={<Botao variante="secundario" onClick={() => setEditando(true)}>Editar</Botao>}>
        <dl className="grid grid-cols-2 gap-x-4">
          <Linha rotulo="Nome completo" valor={p.full_name} />
          <Linha rotulo="Nome social" valor={p.social_name} />
          <Linha rotulo="Nascimento" valor={dataBR(p.birth_date)} />
          <Linha rotulo="Sexo" valor={p.sex} />
          <Linha rotulo="CPF" valor={p.cpf} />
          <Linha rotulo="E-mail" valor={p.email} />
          <Linha rotulo="Telefone" valor={p.phone} />
          <Linha rotulo="Outro telefone" valor={p.phone_alt} />
          <Linha rotulo="Responsável" valor={p.guardian_name && `${p.guardian_name} (${p.guardian_relationship ?? "—"})`} />
          <Linha rotulo="Telefone do responsável" valor={p.guardian_phone} />
          <div className="col-span-2">
            <Linha rotulo="Endereço" valor={endereco} />
            <Linha rotulo="Observações" valor={p.notes} />
          </div>
        </dl>
      </Cartao>
      <Consentimentos paciente={p} />
      {editando && (
        <FormPaciente aberto paciente={p} aoFechar={() => setEditando(false)} />
      )}
    </div>
  );
}

function Consentimentos({ paciente }: { paciente: Paciente }) {
  const cliente = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const chave = ["paciente", paciente.id, "consentimentos"];
  const consentimentos = useQuery({
    queryKey: chave,
    queryFn: async () =>
      ok(
        await api.GET("/pacientes/{patient_id}/consentimentos", {
          params: { path: { patient_id: paciente.id } },
        }),
      ),
  });
  const registrar = useMutation({
    mutationFn: async ({ finalidade, dado }: { finalidade: Finalidade; dado: boolean }) =>
      ok(
        await api.POST("/pacientes/{patient_id}/consentimentos", {
          params: { path: { patient_id: paciente.id } },
          body: {
            purpose: finalidade,
            granted: dado,
            given_by: paciente.guardian_name ? "responsavel" : "paciente",
          },
        }),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: chave }),
    onError: (e) => setErro(e.message),
  });

  return (
    <Cartao titulo="Consentimentos (LGPD)">
      {consentimentos.isLoading && <Carregando />}
      {consentimentos.error && <ErroCarga erro={consentimentos.error} />}
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      <ul className="divide-y divide-borda">
        {(Object.keys(FINALIDADES) as Finalidade[]).map((f) => {
          const atual = consentimentos.data?.atuais[f];
          return (
            <li key={f} className="flex flex-wrap items-center gap-2 py-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{FINALIDADES[f]}</p>
                <p className="text-xs text-texto-suave">
                  {atual ? `${atual.granted ? "Dado" : "Revogado"} em ${dataHoraBR(atual.created_at)} (${atual.given_by})` : "Nunca registrado"}
                </p>
              </div>
              {atual?.granted ? (
                <>
                  <Etiqueta tom="sucesso">Dado</Etiqueta>
                  <Botao variante="fantasma" onClick={() => registrar.mutate({ finalidade: f, dado: false })}>
                    Revogar
                  </Botao>
                </>
              ) : (
                <Botao variante="secundario" onClick={() => registrar.mutate({ finalidade: f, dado: true })}>
                  Registrar
                </Botao>
              )}
            </li>
          );
        })}
      </ul>
      <p className="mt-2 text-xs text-texto-suave">
        Cada registro fica no histórico (nada é apagado). Para menor de idade, o consentimento é
        dado pelo responsável.
      </p>
    </Cartao>
  );
}
