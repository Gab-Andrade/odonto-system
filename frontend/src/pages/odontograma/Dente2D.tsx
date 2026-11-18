import type { Schemas } from "../../api/client";
import { LADO as T, ladoDireito, superior } from "./geometria";

export type DenteVis = Schemas["ToothViewOut"];

const M = 13; // margem interna (face oclusal no centro)


/**
 * Posição de cada face no quadrado, vista de frente para o paciente:
 * vestibular para fora da boca (em cima nos superiores, embaixo nos inferiores) e mesial
 * voltada para a linha média.
 */
function posicao(fdi: number, face: string): "cima" | "baixo" | "esq" | "dir" | "centro" {
  if (face === "O") return "centro";
  if (face === "V") return superior(fdi) ? "cima" : "baixo";
  if (face === "L") return superior(fdi) ? "baixo" : "cima";
  const mesialDireita = ladoDireito(fdi); // à esquerda do observador, a linha média fica à direita
  if (face === "M") return mesialDireita ? "dir" : "esq";
  return mesialDireita ? "esq" : "dir";
}

const POLIGONO: Record<string, string> = {
  cima: `0,0 ${T},0 ${T - M},${M} ${M},${M}`,
  baixo: `0,${T} ${T},${T} ${T - M},${T - M} ${M},${T - M}`,
  esq: `0,0 ${M},${M} ${M},${T - M} 0,${T}`,
  dir: `${T},0 ${T},${T} ${T - M},${T - M} ${T - M},${M}`,
  centro: `${M},${M} ${T - M},${M} ${T - M},${T - M} ${M},${T - M}`,
};

export default function Dente2D({
  dente,
  x,
  y,
  selecionado,
  aoTocarFace,
  aoTocarDente,
}: {
  dente: DenteVis;
  x: number;
  y: number;
  selecionado: boolean;
  aoTocarFace: (face: string) => void;
  aoTocarDente: () => void;
}) {
  const ausente = dente.hidden;
  const numeroEmCima = superior(dente.tooth);
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={T / 2}
        y={numeroEmCima ? -6 : T + 16}
        textAnchor="middle"
        className="cursor-pointer fill-current text-[11px] font-semibold select-none"
        onClick={aoTocarDente}
      >
        {dente.tooth}
      </text>
      <g opacity={dente.in_arch ? 1 : 0.4}>
        {Object.values(dente.faces).map((f) => (
          <polygon
            key={f.face}
            points={POLIGONO[posicao(dente.tooth, f.face)]}
            fill={f.color ?? "var(--color-painel)"}
            stroke="var(--color-texto-suave)"
            strokeWidth={1}
            className="cursor-pointer hover:opacity-80"
            onClick={() => aoTocarFace(f.face)}
          >
            <title>
              {dente.tooth} · {f.face}
              {f.marks.length ? `: ${f.marks.map((m) => m.name).join(", ")}` : ""}
            </title>
          </polygon>
        ))}
        {/* Marcação do dente inteiro: contorno grosso na cor do item. */}
        {dente.color && !ausente && (
          <rect x={-3} y={-3} width={T + 6} height={T + 6} rx={6} fill="none" stroke={dente.color} strokeWidth={4} pointerEvents="none" />
        )}
        {ausente && (
          <g stroke={dente.color ?? "#616161"} strokeWidth={4} pointerEvents="none">
            <line x1={2} y1={2} x2={T - 2} y2={T - 2} />
            <line x1={T - 2} y1={2} x2={2} y2={T - 2} />
          </g>
        )}
        {selecionado && (
          <rect x={-5} y={-5} width={T + 10} height={T + 10} rx={8} fill="none" stroke="var(--color-marca)" strokeDasharray="4 3" strokeWidth={2} pointerEvents="none" />
        )}
      </g>
    </g>
  );
}
