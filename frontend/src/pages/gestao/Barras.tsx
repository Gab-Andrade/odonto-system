import { useState } from "react";

/**
 * Barras mês a mês de UMA série (small multiples: um gráfico por indicador, sem eixo
 * duplo). Barras finas, ponta de 4px arredondada só no topo, 2px de folga, grade discreta,
 * rótulo só no último mês e tooltip ao tocar/passar.
 */
export default function Barras({
  titulo,
  pontos,
  formatar,
}: {
  titulo: string;
  pontos: { rotulo: string; valor: number }[];
  formatar: (v: number) => string;
}) {
  const [foco, setFoco] = useState<number | null>(null);
  const L = 300;
  const A = 120;
  const topo = 18;
  const base = A - 20;
  const max = Math.max(...pontos.map((p) => p.valor), 1);
  const passo = L / Math.max(pontos.length, 1);
  const largura = Math.min(28, passo - 2);
  const ultimo = pontos.length - 1;

  return (
    <figure className="flex flex-col gap-1">
      <figcaption className="text-sm font-semibold">{titulo}</figcaption>
      <svg viewBox={`0 0 ${L} ${A}`} className="h-auto w-full" role="img" aria-label={titulo}>
        <line x1={0} x2={L} y1={base} y2={base} stroke="var(--color-borda)" strokeWidth={1} />
        {pontos.map((p, i) => {
          const h = ((base - topo) * p.valor) / max;
          const x = i * passo + (passo - largura) / 2;
          const y = base - h;
          const r = Math.min(4, h / 2, largura / 2);
          const caminho =
            h <= 0
              ? ""
              : `M${x},${base} V${y + r} Q${x},${y} ${x + r},${y} H${x + largura - r} Q${x + largura},${y} ${x + largura},${y + r} V${base} Z`;
          const ativo = foco === i || (foco === null && i === ultimo);
          return (
            <g key={p.rotulo} onMouseEnter={() => setFoco(i)} onMouseLeave={() => setFoco(null)} onClick={() => setFoco(i)}>
              {/* Área de toque maior que a barra. */}
              <rect x={i * passo} y={0} width={passo} height={A} fill="transparent" />
              {caminho && (
                <path d={caminho} fill="var(--color-marca)" opacity={ativo ? 1 : 0.55}>
                  <title>
                    {p.rotulo}: {formatar(p.valor)}
                  </title>
                </path>
              )}
              <text x={i * passo + passo / 2} y={A - 5} textAnchor="middle" className="fill-[var(--color-texto-suave)] text-[10px]">
                {p.rotulo}
              </text>
              {ativo && (
                <text x={i * passo + passo / 2} y={Math.max(y - 4, 11)} textAnchor="middle" className="fill-[var(--color-texto)] text-[10px] font-semibold">
                  {formatar(p.valor)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
