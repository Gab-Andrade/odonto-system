import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ok, type Schemas } from "../api/client";
import { GESTAO, temPapel, useSessao } from "../auth/sessao";
import Modal from "../components/Modal";
import { Aviso, Botao, Campo, Cartao, Carregando, ErroCarga, Etiqueta, Selecao, Titulo, Vazio } from "../components/ui";
import { dataBR } from "../lib/datas";

type Alerta = Schemas["app__modules__inteligencia__schemas__AlertOut"];
type Regra = Schemas["app__modules__inteligencia__schemas__RuleOut"];

const TOM = { alta: "perigo", media: "alerta", baixa: "info" } as const;

export default function Alertas() {
  const { papel, usuario } = useSessao();
  const cliente = useQueryClient();
  const [regra, setRegra] = useState("");
  const [meus, setMeus] = useState(false);
  const [dispensados, setDispensados] = useState(false);
  const [dispensar, setDispensar] = useState<Alerta | null>(null);
  const [configurar, setConfigurar] = useState(false);

  const regras = useQuery({
    queryKey: ["alertas", "regras"],
    queryFn: async () => ok(await api.GET("/inteligencia/regras")),
  });
  const alertas = useQuery({
    queryKey: ["alertas", "lista", regra, meus, dispensados],
    queryFn: async () =>
      ok(
        await api.GET("/inteligencia/alertas", {
          params: {
            query: {
              regra: regra ? [regra] : undefined,
              dentista_id: meus && usuario ? usuario.id : undefined,
              incluir_dispensados: dispensados,
            },
          },
        }),
      ),
  });

  const reativar = useMutation({
    mutationFn: async (a: Alerta) =>
      ok(await api.POST("/inteligencia/alertas/reativar", { body: { code: a.code, key: a.key } })),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["alertas"] }),
  });

  return (
    <div>
      <Titulo
        acoes={
          temPapel(papel, ...GESTAO) && (
            <Botao variante="secundario" onClick={() => setConfigurar(true)}>
              Configurar regras
            </Botao>
          )
        }
      >
        Alertas
      </Titulo>
      <Cartao className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <Selecao rotulo="Regra" value={regra} onChange={(e) => setRegra(e.target.value)}>
            <option value="">Todas</option>
            {regras.data?.map((r) => (
              <option key={r.code} value={r.code}>
                {r.title}
              </option>
            ))}
          </Selecao>
          {temPapel(papel, "dentista", "admin") && (
            <label className="flex min-h-11 items-center gap-2 text-sm">
              <input type="checkbox" className="size-5" checked={meus} onChange={(e) => setMeus(e.target.checked)} />
              Só meus pacientes
            </label>
          )}
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-5" checked={dispensados} onChange={(e) => setDispensados(e.target.checked)} />
            Mostrar dispensados
          </label>
        </div>
      </Cartao>

      {alertas.isLoading && <Carregando />}
      {alertas.error && <ErroCarga erro={alertas.error} />}
      {alertas.data && alertas.data.length === 0 && (
        <Cartao>
          <Vazio>Nenhum alerta. Tudo em dia!</Vazio>
        </Cartao>
      )}
      <ul className="flex flex-col gap-2">
        {alertas.data?.map((a) => (
          <li key={`${a.code}:${a.key}`} className="rounded-xl border border-borda bg-painel p-3">
            <div className="flex flex-wrap items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Etiqueta tom={TOM[a.severity as keyof typeof TOM] ?? "info"}>{a.title}</Etiqueta>
                  {a.dismissed_until && <Etiqueta>Dispensado até {dataBR(a.dismissed_until)}</Etiqueta>}
                </div>
                {a.patient_id && (
                  <Link to={`/pacientes/${a.patient_id}`} className="mt-1 block font-semibold text-marca hover:underline">
                    {a.patient_name}
                  </Link>
                )}
                <p className="text-sm">{a.detail}</p>
                {a.patient_phone && <p className="text-xs text-texto-suave">Telefone: {a.patient_phone}</p>}
              </div>
              {a.dismissed_until ? (
                <Botao variante="secundario" onClick={() => reativar.mutate(a)}>
                  Voltar a mostrar
                </Botao>
              ) : (
                <Botao variante="secundario" onClick={() => setDispensar(a)}>
                  Dispensar
                </Botao>
              )}
            </div>
          </li>
        ))}
      </ul>

      {dispensar && <Dispensar alerta={dispensar} aoFechar={() => setDispensar(null)} />}
      {configurar && regras.data && <ConfigurarRegras regras={regras.data} aoFechar={() => setConfigurar(false)} />}
    </div>
  );
}

function Dispensar({ alerta, aoFechar }: { alerta: Alerta; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [ate, setAte] = useState("");
  const [motivo, setMotivo] = useState("");
  const salvar = useMutation({
    mutationFn: async () =>
      ok(
        await api.POST("/inteligencia/alertas/dispensar", {
          body: { code: alerta.code, key: alerta.key, until: ate || null, reason: motivo || null },
        }),
      ),
    onSuccess: () => {
      cliente.invalidateQueries({ queryKey: ["alertas"] });
      aoFechar();
    },
  });
  return (
    <Modal titulo="Dispensar alerta" aberto aoFechar={aoFechar}>
      <div className="flex flex-col gap-3">
        {salvar.error && <Aviso tom="perigo">{salvar.error.message}</Aviso>}
        <p className="text-sm">
          {alerta.title} · {alerta.patient_name}
        </p>
        <Campo rotulo="Voltar a mostrar em" type="date" dica="Vazio: daqui a 30 dias." value={ate} onChange={(e) => setAte(e.target.value)} />
        <Campo rotulo="Motivo" placeholder="Ex.: liguei, vai marcar" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Botao variante="secundario" onClick={aoFechar}>
            Cancelar
          </Botao>
          <Botao onClick={() => salvar.mutate()} carregando={salvar.isPending}>
            Dispensar
          </Botao>
        </div>
      </div>
    </Modal>
  );
}

function ConfigurarRegras({ regras, aoFechar }: { regras: Regra[]; aoFechar: () => void }) {
  const cliente = useQueryClient();
  const [erro, setErro] = useState<string | null>(null);
  const salvar = useMutation({
    mutationFn: async (r: { code: string; enabled: boolean; params: Record<string, unknown> }) =>
      ok(
        await api.PUT("/inteligencia/regras/{code}", {
          params: { path: { code: r.code } },
          body: { enabled: r.enabled, params: r.params },
        }),
      ),
    onSuccess: () => cliente.invalidateQueries({ queryKey: ["alertas"] }),
    onError: (e) => setErro(e.message),
  });

  return (
    <Modal titulo="Regras de alerta" aberto aoFechar={aoFechar} largura="max-w-2xl">
      {erro && <Aviso tom="perigo">{erro}</Aviso>}
      <ul className="flex flex-col gap-3">
        {regras.map((r) => (
          <RegraLinha key={r.code} regra={r} aoSalvar={(enabled, params) => salvar.mutate({ code: r.code, enabled, params })} />
        ))}
      </ul>
    </Modal>
  );
}

function RegraLinha({
  regra,
  aoSalvar,
}: {
  regra: Regra;
  aoSalvar: (ativa: boolean, params: Record<string, unknown>) => void;
}) {
  const [ativa, setAtiva] = useState(regra.enabled);
  const [params, setParams] = useState<Record<string, unknown>>(regra.params);
  return (
    <li className="rounded-lg border border-borda p-3">
      <label className="flex min-h-11 items-center gap-2 font-semibold">
        <input type="checkbox" className="size-5" checked={ativa} onChange={(e) => setAtiva(e.target.checked)} />
        {regra.title}
      </label>
      <p className="mb-2 text-xs text-texto-suave">{regra.description}</p>
      <div className="flex flex-wrap items-end gap-3">
        {regra.param_spec.map((p) =>
          p.type === "inteiro" ? (
            <Campo
              key={p.name}
              rotulo={p.label}
              type="number"
              min={p.minimum ?? undefined}
              max={p.maximum ?? undefined}
              className="w-40"
              value={String(params[p.name] ?? "")}
              onChange={(e) => setParams({ ...params, [p.name]: Number(e.target.value) })}
            />
          ) : (
            <Campo
              key={p.name}
              rotulo={`${p.label} (separados por vírgula)`}
              className="min-w-60 flex-1"
              value={((params[p.name] as string[]) ?? []).join(", ")}
              onChange={(e) =>
                setParams({ ...params, [p.name]: e.target.value.split(",").map((t) => t.trim()).filter(Boolean) })
              }
            />
          ),
        )}
        <Botao variante="secundario" onClick={() => aoSalvar(ativa, params)}>
          Salvar
        </Botao>
      </div>
    </li>
  );
}
