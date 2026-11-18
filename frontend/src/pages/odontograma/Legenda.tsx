import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ok, type Schemas } from "../../api/client";

type Item = Schemas["StatusOut"];

const CHAVE = "odontograma.legenda.aberta";

/** "clinica": muda para todos; "pessoal": só para quem está usando; null: só ver. */
export type Modo = "clinica" | "pessoal" | null;

function lerAberta(): boolean {
  try {
    return localStorage.getItem(CHAVE) !== "0";
  } catch {
    return true;
  }
}

/**
 * Legenda compacta e recolhível, com a cor de cada item editável. Admin e gestor mudam a cor
 * da clínica toda; dentista e ASB escolhem uma cor só para si (ex.: cárie preta), que pode voltar
 * para a da clínica.
 */
export default function Legenda({
  itens,
  emUso,
  modo,
}: {
  itens: Item[];
  emUso: Set<string>;
  modo: Modo;
}) {
  const [aberta, setAberta] = useState(lerAberta);
  const [erro, setErro] = useState<string | null>(null);

  function alternar() {
    setAberta((a) => {
      try {
        localStorage.setItem(CHAVE, a ? "0" : "1");
      } catch {
        // sem armazenamento: só não lembra
      }
      return !a;
    });
  }

  return (
    <section className="rounded-xl border border-borda bg-painel p-3 shadow-sm">
      <button
        type="button"
        onClick={alternar}
        aria-expanded={aberta}
        className="flex min-h-9 w-full items-center justify-between gap-2 text-sm font-semibold"
      >
        Legenda
        <span aria-hidden className={`text-texto-suave transition-transform ${aberta ? "rotate-180" : ""}`}>
          ▾
        </span>
      </button>
      {aberta && (
        <>
          <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 lg:grid-cols-1">
            {itens.map((l) => (
              <LinhaLegenda key={l.id} item={l} emUso={emUso.has(l.id)} modo={modo} aoErrar={setErro} />
            ))}
          </ul>
          {erro && <p className="mt-2 text-xs text-perigo">{erro}</p>}
          {modo && (
            <p className="mt-2 text-xs text-texto-suave">
              Toque na cor para trocar {modo === "clinica" ? "(vale para a clínica toda)." : "(só para você)."}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function LinhaLegenda({
  item,
  emUso,
  modo,
  aoErrar,
}: {
  item: Item;
  emUso: boolean;
  modo: Modo;
  aoErrar: (msg: string | null) => void;
}) {
  const cliente = useQueryClient();
  // Cor escolhida e ainda não gravada; null = mostra a do servidor.
  const [rascunho, setRascunho] = useState<string | null>(null);
  // Na edição da clínica, parte da cor da clínica; na pessoal, da que a pessoa vê.
  const base = modo === "clinica" ? (item.clinic_color ?? item.color) : item.color;
  const cor = rascunho ?? base;
  const caminho = { params: { path: { status_id: item.id } } };

  const aoSalvar = {
    onSuccess: async () => {
      aoErrar(null);
      await cliente.invalidateQueries({ queryKey: ["odontograma"] });
      setRascunho(null);
    },
    onError: (e: Error) => {
      aoErrar(e.message);
      setRascunho(null);
    },
  };
  const salvar = useMutation({
    mutationFn: async (color: string) =>
      modo === "clinica"
        ? ok(await api.PATCH("/odontograma/legenda/{status_id}", { ...caminho, body: { color } }))
        : ok(await api.PUT("/odontograma/legenda/{status_id}/minha-cor", { ...caminho, body: { color } })),
    ...aoSalvar,
  });
  const restaurar = useMutation({
    mutationFn: async () => ok(await api.DELETE("/odontograma/legenda/{status_id}/minha-cor", caminho)),
    ...aoSalvar,
  });
  const { mutate } = salvar;

  // O seletor de cor dispara a cada arrasto: grava só quando a pessoa para de mexer.
  useEffect(() => {
    if (!rascunho || rascunho === base.toUpperCase()) return;
    const t = setTimeout(() => mutate(rascunho), 600);
    return () => clearTimeout(t);
  }, [rascunho, base, mutate]);

  const amostra = "size-4 shrink-0 rounded-sm border border-black/20";
  return (
    <li className={`flex min-w-0 items-center gap-2 text-xs ${emUso ? "font-semibold" : "text-texto-suave"}`}>
      {modo ? (
        <label className={`${amostra} relative cursor-pointer overflow-hidden`} style={{ background: cor }} title={`Trocar a cor de "${item.name}"`}>
          <input
            type="color"
            value={cor.toLowerCase()}
            onChange={(e) => setRascunho(e.target.value.toUpperCase())}
            className="absolute inset-0 cursor-pointer opacity-0"
            aria-label={`Cor de ${item.name}`}
          />
        </label>
      ) : (
        <span className={amostra} style={{ background: cor }} />
      )}
      <span className="truncate">{item.name}</span>
      {modo === "pessoal" && item.personal && (
        <button
          type="button"
          onClick={() => restaurar.mutate()}
          disabled={restaurar.isPending}
          className="ml-auto shrink-0 rounded px-1 text-sm text-texto-suave hover:text-marca"
          title={`Voltar para a cor da clínica`}
          aria-label={`Voltar ${item.name} para a cor da clínica`}
        >
          ↺
        </button>
      )}
    </li>
  );
}
