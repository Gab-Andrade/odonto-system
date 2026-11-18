import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, ok, type Schemas } from "../../api/client";
import { CLINICOS, temPapel, useSessao } from "../../auth/sessao";
import { Abas, Aviso, Carregando, ErroCarga, Etiqueta } from "../../components/ui";
import { dataBR, idade } from "../../lib/datas";
import { formatarResposta } from "../../lib/texto";
import Cadastro from "./Cadastro";
import ConsultasPaciente from "./ConsultasPaciente";

// Abas clínicas carregadas sob demanda (o 3D puxa o three.js).
const Anamnese = lazy(() => import("../prontuario/Anamnese"));
const Atendimentos = lazy(() => import("../prontuario/Atendimentos"));
const Odontograma = lazy(() => import("../odontograma/Odontograma"));
const Planos = lazy(() => import("../tratamento/Planos"));
const Exames = lazy(() => import("../prontuario/Exames"));
const Financeiro = lazy(() => import("../financeiro/FinanceiroPaciente"));

type Aba =
  | "cadastro"
  | "agenda"
  | "atendimentos"
  | "odontograma"
  | "planos"
  | "exames"
  | "financeiro";

type Secao = "evolucao" | "anamnese";

/** Aba Atendimentos: evolução clínica e anamnese, lado a lado num seletor. */
function ProntuarioClinico({
  paciente,
  secao,
  aoMudar,
}: {
  paciente: Schemas["PatientOut"];
  secao: Secao;
  aoMudar: (s: Secao) => void;
}) {
  const opcoes: { id: Secao; rotulo: string }[] = [
    { id: "evolucao", rotulo: "Evolução" },
    { id: "anamnese", rotulo: "Anamnese" },
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="nao-imprimir flex w-fit rounded-lg border border-borda p-1">
        {opcoes.map((o) => (
          <button
            key={o.id}
            type="button"
            onClick={() => aoMudar(o.id)}
            aria-pressed={secao === o.id}
            className={`min-h-10 rounded-md px-4 text-sm font-semibold ${secao === o.id ? "bg-marca text-white dark:text-slate-900" : ""}`}
          >
            {o.rotulo}
          </button>
        ))}
      </div>
      {secao === "anamnese" ? <Anamnese pacienteId={paciente.id} /> : <Atendimentos paciente={paciente} />}
    </div>
  );
}

export default function Paciente() {
  const { id = "" } = useParams();
  const { papel } = useSessao();
  const [params, setParams] = useSearchParams();
  const clinico = temPapel(papel, ...CLINICOS);
  // Dentista vê o extrato só se o admin/gestor liberar (Gestão → Configurações).
  const config = useQuery({
    enabled: papel === "dentista",
    queryKey: ["financeiro", "configuracao"],
    queryFn: async () => ok(await api.GET("/financeiro/configuracao")),
  });
  const caixa =
    temPapel(papel, "admin", "gestor", "recepcao") ||
    (papel === "dentista" && config.data?.dentist_can_view === true);
  const planos = temPapel(papel, "admin", "gestor", "dentista", "asb", "recepcao");

  const abas: { id: Aba; rotulo: string }[] = [
    ...(clinico ? [{ id: "odontograma" as Aba, rotulo: "Odontograma" }] : []),
    ...(clinico ? [{ id: "atendimentos" as Aba, rotulo: "Atendimentos" }] : []),
    ...(planos ? [{ id: "planos" as Aba, rotulo: "Planos e orçamentos" }] : []),
    ...(clinico ? [{ id: "exames" as Aba, rotulo: "Raio-X" }] : []),
    ...(caixa ? [{ id: "financeiro" as Aba, rotulo: "Financeiro" }] : []),
    { id: "agenda", rotulo: "Agenda" },
    { id: "cadastro", rotulo: "Cadastro" },
  ];
  // Nomes antigos das abas continuam valendo em links salvos.
  const bruta = params.get("aba");
  const pedida = (bruta === "consultas" ? "agenda" : bruta === "anamnese" ? "atendimentos" : bruta) as Aba | null;
  const aba: Aba = abas.some((a) => a.id === pedida) ? (pedida as Aba) : abas[0].id;
  const secao: Secao = params.get("secao") === "anamnese" || bruta === "anamnese" ? "anamnese" : "evolucao";

  const paciente = useQuery({
    queryKey: ["paciente", id],
    queryFn: async () =>
      ok(await api.GET("/pacientes/{patient_id}", { params: { path: { patient_id: id } } })),
  });

  // Alertas da anamnese (alergias etc.) no cabeçalho: só para quem vê o clínico.
  const alertas = useQuery({
    enabled: clinico,
    queryKey: ["paciente", id, "alertas-anamnese"],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/alertas", {
          params: { path: { patient_id: id } },
        }),
      ),
  });

  if (paciente.isLoading) return <Carregando />;
  if (paciente.error) return <ErroCarga erro={paciente.error} />;
  const p = paciente.data!;
  const anos = idade(p.birth_date);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/pacientes" className="nao-imprimir text-sm text-marca">
            ← Pacientes
          </Link>
          <h1 className="text-xl font-bold">
            {p.social_name ?? p.full_name}
            {!p.active && (
              <span className="ml-2 align-middle">
                <Etiqueta tom="alerta">Inativo</Etiqueta>
              </span>
            )}
          </h1>
          <p className="text-sm text-texto-suave">
            {anos !== null ? `${anos} anos (${dataBR(p.birth_date)})` : "Sem data de nascimento"} ·{" "}
            {p.phone}
            {p.guardian_name && ` · Responsável: ${p.guardian_name}`}
          </p>
        </div>
      </div>

      {alertas.data && alertas.data.length > 0 && (
        <div className="mb-4">
          <Aviso tom="perigo">
            <strong>Atenção (anamnese):</strong>{" "}
            {alertas.data.map((a) => `${a.text}: ${formatarResposta(a.answer)}`).join(" · ")}
          </Aviso>
        </div>
      )}

      <Abas
        abas={abas}
        atual={aba}
        aoMudar={(nova) => setParams({ aba: nova }, { replace: true })}
      />

      <Suspense fallback={<Carregando />}>
        {aba === "cadastro" && <Cadastro paciente={p} />}
        {aba === "agenda" && <ConsultasPaciente pacienteId={p.id} />}
        {aba === "atendimentos" && (
          <ProntuarioClinico paciente={p} secao={secao} aoMudar={(s) => setParams({ aba: "atendimentos", secao: s }, { replace: true })} />
        )}
        {aba === "odontograma" && <Odontograma paciente={p} />}
        {aba === "planos" && <Planos paciente={p} />}
        {aba === "exames" && <Exames pacienteId={p.id} />}
        {aba === "financeiro" && <Financeiro pacienteId={p.id} />}
      </Suspense>
    </div>
  );
}
