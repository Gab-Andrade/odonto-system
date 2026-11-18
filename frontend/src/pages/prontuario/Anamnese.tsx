import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, ok } from "../../api/client";
import { temPapel, useSessao } from "../../auth/sessao";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Vazio } from "../../components/ui";
import { dataHoraBR } from "../../lib/datas";
import { formatarResposta } from "../../lib/texto";

export interface Pergunta {
  id: string;
  text: string;
  type: "texto" | "sim_nao" | "escolha_unica" | "multipla" | "numero" | "data";
  section?: string;
  help?: string;
  required?: boolean;
  alert?: boolean;
  options?: string[];
  alert_options?: string[];
}

export default function Anamnese({ pacienteId }: { pacienteId: string }) {
  const { papel } = useSessao();
  const podePreencher = temPapel(papel, "admin", "dentista", "asb");
  const [preenchendo, setPreenchendo] = useState<{ modelo: string; versao: string } | null>(null);
  const [vendo, setVendo] = useState<string | null>(null);

  const modelos = useQuery({
    queryKey: ["anamnese", "modelos"],
    queryFn: async () => ok(await api.GET("/prontuario/anamnese/modelos")),
  });
  const respostas = useQuery({
    queryKey: ["anamnese", "respostas", pacienteId],
    queryFn: async () =>
      ok(
        await api.GET("/prontuario/pacientes/{patient_id}/anamneses", {
          params: { path: { patient_id: pacienteId } },
        }),
      ),
  });
  const publicados = (modelos.data ?? []).filter((m) => m.published && m.active);

  if (preenchendo) {
    return <Formulario pacienteId={pacienteId} {...preenchendo} aoFechar={() => setPreenchendo(null)} />;
  }

  return (
    <div className="flex flex-col gap-4">
      {(modelos.isLoading || respostas.isLoading) && <Carregando />}
      {modelos.error && <ErroCarga erro={modelos.error} />}
      {modelos.data && publicados.length === 0 && (
        <Aviso>
          Nenhum modelo de anamnese publicado. O admin ou gestor monta e publica o modelo (API
          /prontuario/anamnese/modelos; o comando demo cria um exemplo).
        </Aviso>
      )}
      {publicados.map((m) => {
        const atual = respostas.data?.find((r) => r.template_id === m.id && r.current);
        return (
          <Cartao
            key={m.id}
            titulo={m.name}
            acoes={
              podePreencher && (
                <Botao variante={atual ? "secundario" : "primario"} onClick={() => setPreenchendo({ modelo: m.id, versao: m.published!.id })}>
                  {atual ? "Atualizar" : "Preencher"}
                </Botao>
              )
            }
          >
            {atual ? (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-texto-suave">
                  Respondida em {dataHoraBR(atual.created_at)} (versão {atual.version_number})
                </p>
                {atual.alerts.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {atual.alerts.map((a) => (
                      <Etiqueta key={a.question_id} tom="perigo">
                        {a.text}: {formatarResposta(a.answer)}
                      </Etiqueta>
                    ))}
                  </div>
                )}
                <Botao variante="fantasma" className="self-start" onClick={() => setVendo(vendo === atual.id ? null : atual.id)}>
                  {vendo === atual.id ? "Esconder respostas" : "Ver respostas"}
                </Botao>
                {vendo === atual.id && <Respostas id={atual.id} />}
              </div>
            ) : (
              <Vazio>Ainda não respondida.</Vazio>
            )}
          </Cartao>
        );
      })}
      {respostas.data && respostas.data.some((r) => !r.current) && (
        <Cartao titulo="Respostas anteriores">
          <ul className="divide-y divide-borda">
            {respostas.data
              .filter((r) => !r.current)
              .map((r) => (
                <li key={r.id} className="py-2">
                  <button type="button" className="min-h-9 text-sm text-marca" onClick={() => setVendo(vendo === r.id ? null : r.id)}>
                    {r.template_name} · {dataHoraBR(r.created_at)}
                  </button>
                  {vendo === r.id && <Respostas id={r.id} />}
                </li>
              ))}
          </ul>
        </Cartao>
      )}
    </div>
  );
}

function Respostas({ id }: { id: string }) {
  const r = useQuery({
    queryKey: ["anamnese", "resposta", id],
    queryFn: async () =>
      ok(await api.GET("/prontuario/anamneses/{response_id}", { params: { path: { response_id: id } } })),
  });
  if (r.isLoading) return <Carregando />;
  if (r.error) return <ErroCarga erro={r.error} />;
  const perguntas = (r.data?.questions ?? []) as unknown as Pergunta[];
  return (
    <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
      {perguntas.map((p) => (
        <div key={p.id}>
          <dt className="text-xs text-texto-suave">{p.text}</dt>
          <dd className="text-sm">{formatarResposta(r.data?.answers[p.id])}</dd>
        </div>
      ))}
    </dl>
  );
}

function Formulario({
  pacienteId,
  modelo,
  versao,
  aoFechar,
}: {
  pacienteId: string;
  modelo: string;
  versao: string;
  aoFechar: () => void;
}) {
  const cliente = useQueryClient();
  const [respostas, setRespostas] = useState<Record<string, unknown>>({});
  const versaoQ = useQuery({
    queryKey: ["anamnese", "versao", versao],
    queryFn: async () =>
      ok(await api.GET("/prontuario/anamnese/versoes/{version_id}", { params: { path: { version_id: versao } } })),
  });
  const salvar = useMutation({
    mutationFn: async () => {
      const limpas = Object.fromEntries(
        Object.entries(respostas).filter(([, v]) => v !== "" && v !== undefined && !(Array.isArray(v) && v.length === 0)),
      );
      return ok(
        await api.POST("/prontuario/pacientes/{patient_id}/anamneses", {
          params: { path: { patient_id: pacienteId } },
          body: { template_id: modelo, version_id: versao, answers: limpas },
        }),
      );
    },
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["anamnese", "respostas", pacienteId] });
      cliente.invalidateQueries({ queryKey: ["paciente", pacienteId, "alertas-anamnese"] });
      aoFechar();
    },
  });

  if (versaoQ.isLoading) return <Carregando />;
  if (versaoQ.error) return <ErroCarga erro={versaoQ.error} />;
  const perguntas = (versaoQ.data?.questions ?? []) as unknown as Pergunta[];
  const secoes = [...new Set(perguntas.map((p) => p.section ?? ""))];
  const definir = (id: string, v: unknown) => setRespostas({ ...respostas, [id]: v });

  return (
    <Cartao titulo="Preencher anamnese">
      <div className="flex flex-col gap-5">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        {secoes.map((s) => (
          <fieldset key={s} className="flex flex-col gap-3">
            {s && <legend className="mb-1 text-sm font-bold">{s}</legend>}
            {perguntas
              .filter((p) => (p.section ?? "") === s)
              .map((p) => (
                <CampoPergunta key={p.id} pergunta={p} valor={respostas[p.id]} aoMudar={(v) => definir(p.id, v)} />
              ))}
          </fieldset>
        ))}
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            Salvar respostas
          </Botao>
        </div>
      </div>
    </Cartao>
  );
}

export function CampoPergunta({
  pergunta: p,
  valor,
  aoMudar,
}: {
  pergunta: Pergunta;
  valor: unknown;
  aoMudar: (v: unknown) => void;
}) {
  const rotulo = `${p.text}${p.required ? " *" : ""}`;
  switch (p.type) {
    case "sim_nao":
      return (
        <div className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-texto-suave">
            {rotulo} {p.alert && <span className="text-xs text-alerta">(alerta)</span>}
          </span>
          <div className="flex gap-2">
            {[
              [true, "Sim"],
              [false, "Não"],
            ].map(([v, r]) => (
              <button
                key={String(v)}
                type="button"
                onClick={() => aoMudar(v)}
                className={`min-h-11 min-w-20 rounded-lg border px-4 font-semibold ${valor === v ? "border-marca bg-marca-suave text-marca" : "border-borda"}`}
              >
                {r as string}
              </button>
            ))}
          </div>
        </div>
      );
    case "escolha_unica":
      return (
        <Selecao rotulo={rotulo} value={(valor as string) ?? ""} onChange={(e) => aoMudar(e.target.value)}>
          <option value="">—</option>
          {p.options?.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </Selecao>
      );
    case "multipla": {
      const lista = (valor as string[]) ?? [];
      return (
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="font-medium text-texto-suave">{rotulo}</legend>
          <div className="flex flex-wrap gap-3">
            {p.options?.map((o) => (
              <label key={o} className="flex min-h-11 items-center gap-2">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={lista.includes(o)}
                  onChange={(e) => aoMudar(e.target.checked ? [...lista, o] : lista.filter((x) => x !== o))}
                />
                {o}
              </label>
            ))}
          </div>
        </fieldset>
      );
    }
    case "numero":
      return (
        <Campo
          rotulo={rotulo}
          type="number"
          value={(valor as number | undefined) ?? ""}
          onChange={(e) => aoMudar(e.target.value === "" ? undefined : Number(e.target.value))}
        />
      );
    case "data":
      return <Campo rotulo={rotulo} type="date" value={(valor as string) ?? ""} onChange={(e) => aoMudar(e.target.value)} />;
    default:
      return <Campo rotulo={rotulo} dica={p.help} value={(valor as string) ?? ""} onChange={(e) => aoMudar(e.target.value)} />;
  }
}
