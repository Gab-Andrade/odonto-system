import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ok, type Schemas } from "../../api/client";

type Item = Schemas["StatusOut"];

const CHAVE = "odontograma.legenda.aberta";

function lerAberta(): boolean {
  try {
    return localStorage.getItem(CHAVE) !== "0";
  } catch {
    return true;
  }
}

/**
 * Legenda compacta e recolhível. Quem administra a clínica troca a cor de um item (ex.: cárie
 * preta); a cor vale para a clínica toda e repinta todos os odontogramas.
 */
export default function Legenda({
  itens,
  emUso,
  podeEditar,
}: {
  itens: Item[];
  emUso: Set<string>;
  podeEditar: boolean;
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
              <LinhaLegenda key={l.id} item={l} emUso={emUso.has(l.id)} podeEditar={podeEditar} aoErrar={setErro} />
            ))}
          </ul>
          {erro && <p className="mt-2 text-xs text-perigo">{erro}</p>}
          {podeEditar && <p className="mt-2 text-xs text-texto-suave">Toque na cor para trocar (vale para a clínica).</p>}
        </>
      )}
    </section>
  );
}

function LinhaLegenda({
  item,
  emUso,
  podeEditar,
  aoErrar,
}: {
  item: Item;
  emUso: boolean;
  podeEditar: boolean;
  aoErrar: (msg: string | null) => void;
}) {
  const cliente = useQueryClient();
  // Cor escolhida e ainda não gravada; null = mostra a do servidor.
  const [rascunho, setRascunho] = useState<string | null>(null);
  const cor = rascunho ?? item.color;

  const salvar = useMutation({
    mutationFn: async (color: string) =>
      ok(
        await api.PATCH("/odontograma/legenda/{status_id}", {
          params: { path: { status_id: item.id } },
          body: { color },
        }),
      ),
    onSuccess: async () => {
      aoErrar(null);
      await cliente.invalidateQueries({ queryKey: ["odontograma"] });
      setRascunho(null);
    },
    onError: (e) => {
      aoErrar(e.message);
      setRascunho(null);
    },
  });
  const { mutate } = salvar;

  // O seletor de cor dispara a cada arrasto: grava só quando a pessoa para de mexer.
  useEffect(() => {
    if (!rascunho || rascunho === item.color.toUpperCase()) return;
    const t = setTimeout(() => mutate(rascunho), 600);
    return () => clearTimeout(t);
  }, [rascunho, item.color, mutate]);

  const amostra = "size-4 shrink-0 rounded-sm border border-black/20";
  return (
    <li className={`flex min-w-0 items-center gap-2 text-xs ${emUso ? "font-semibold" : "text-texto-suave"}`}>
      {podeEditar ? (
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
    </li>
  );
}
