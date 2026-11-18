import type { DenteVis } from "./Dente2D";

/**
 * Boca vista de cima (só leitura): arcada superior em cima, inferior embaixo, cada dente
 * como uma pecinha numerada pintada com a cor da marcação mais importante. Lado direito do
 * paciente à esquerda de quem olha (numeração FDI).
 */

const CX = 150;
const SUP = { cy: 192, rx: 112, ry: 165 };
const INF = { cy: 232, rx: 104, ry: 158 };

// Largura relativa de cada posição (1 = incisivo central ... 8 = terceiro molar).
const LARG_SUP = [17, 13, 15, 14, 13, 20, 19, 17];
const LARG_INF = [12, 12, 14, 14, 14, 21, 20, 18];
// Profundidade (vestibular→lingual) relativa à largura.
const PROF = [0.9, 0.95, 1.05, 1.1, 1.1, 1.12, 1.12, 1.08];

type Arco = typeof SUP;

/** Ponto e tangente no quarto de elipse, t de 0 (linha média) a 1 (fundo). */
function ponto(arco: Arco, t: number, superior: boolean, direito: boolean) {
  const a = Math.PI / 2 + t * (Math.PI / 2);
  const sx = direito ? 1 : -1; // direito do paciente = esquerda da tela (x menor)
  const sy = superior ? -1 : 1;
  const x = CX + sx * arco.rx * Math.cos(a);
  const y = arco.cy + sy * arco.ry * Math.sin(a);
  const dx = sx * -arco.rx * Math.sin(a);
  const dy = sy * arco.ry * Math.cos(a);
  return { x, y, angulo: (Math.atan2(dy, dx) * 180) / Math.PI };
}

/** Tabela comprimento-de-arco → t, para espaçar os dentes pelo tamanho e não pelo ângulo. */
function tabela(arco: Arco) {
  const N = 200;
  const acum = [0];
  let ant = ponto(arco, 0, true, true);
  for (let i = 1; i <= N; i++) {
    const p = ponto(arco, i / N, true, true);
    acum.push(acum[i - 1] + Math.hypot(p.x - ant.x, p.y - ant.y));
    ant = p;
  }
  return {
    total: acum[N],
    t(s: number) {
      const i = acum.findIndex((v) => v >= s);
      if (i <= 0) return 0;
      const f = (s - acum[i - 1]) / (acum[i] - acum[i - 1]);
      return (i - 1 + f) / N;
    },
  };
}
const TAB_SUP = tabela(SUP);
const TAB_INF = tabela(INF);

const QUADRANTES = [
  { perm: 1, dec: 5, superior: true, direito: true },
  { perm: 2, dec: 6, superior: true, direito: false },
  { perm: 4, dec: 8, superior: false, direito: true },
  { perm: 3, dec: 7, superior: false, direito: false },
];

interface Peca {
  dente: DenteVis;
  x: number;
  y: number;
  angulo: number;
  w: number;
  h: number;
}

/** Posiciona os dentes presentes; as posições vazias no fundo encolhem a arcada. */
function montar(dentes: DenteVis[]): Peca[] {
  const porNumero = new Map(dentes.map((d) => [d.tooth, d]));
  const pecas: Peca[] = [];
  for (const sup of [true, false]) {
    const quads = QUADRANTES.filter((q) => q.superior === sup);
    // Última posição ocupada (em qualquer lado): criança com só decíduos usa 1..5.
    let ultima = 0;
    for (const q of quads)
      for (let p = 1; p <= 8; p++)
        if (porNumero.has(q.perm * 10 + p) || (p <= 5 && porNumero.has(q.dec * 10 + p))) ultima = Math.max(ultima, p);
    if (!ultima) continue;
    const larg = (sup ? LARG_SUP : LARG_INF).slice(0, ultima);
    const tab = sup ? TAB_SUP : TAB_INF;
    const arco = sup ? SUP : INF;
    const soma = larg.reduce((a, b) => a + b, 0);
    // Com poucos dentes, não deixa as pecinhas ficarem enormes.
    const escala = Math.min((tab.total - 4) / soma, 2.3);
    for (const q of quads) {
      let s = 2;
      for (let p = 1; p <= ultima; p++) {
        const w = larg[p - 1] * escala;
        const meio = s + w / 2;
        s += w;
        const { x, y, angulo } = ponto(arco, tab.t(meio), sup, q.direito);
        const perm = porNumero.get(q.perm * 10 + p);
        const dec = p <= 5 ? porNumero.get(q.dec * 10 + p) : undefined;
        const h = w * PROF[p - 1];
        if (perm) pecas.push({ dente: perm, x, y, angulo, w: w * 1.02, h });
        if (dec) {
          // Dentição mista com os dois na mesma posição: o decíduo vai um pouco para dentro.
          const dentro = perm ? 0.62 : 0;
          const nx = (CX - x) * dentro * (w / Math.hypot(CX - x, arco.cy - y));
          const ny = (arco.cy - y) * dentro * (w / Math.hypot(CX - x, arco.cy - y));
          const f = perm ? 0.7 : 1.02;
          pecas.push({ dente: dec, x: x + nx, y: y + ny, angulo, w: w * f, h: h * f });
        }
      }
    }
  }
  return pecas;
}

/** Texto escuro em fundo claro e vice-versa. */
function contraste(cor: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(cor);
  if (!m) return "#1f2937";
  const n = parseInt(m[1], 16);
  const lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
  return lum > 0.6 ? "#1f2937" : "#ffffff";
}

const COR_BASE = "#e5e7eb";

export default function Boca2D({
  dentes,
  selecionado,
  anotados,
  aoTocar,
}: {
  dentes: DenteVis[];
  selecionado: number | null;
  /** Dentes com anotação: ganham um marcador no canto. */
  anotados?: Set<number>;
  aoTocar: (d: DenteVis) => void;
}) {
  const pecas = montar(dentes);
  return (
    <svg viewBox="0 0 300 424" className="mx-auto h-auto w-full max-w-sm" role="img" aria-label="Boca do paciente, vista de cima">
      {pecas.map(({ dente: d, x, y, angulo, w, h }) => {
        const ausente = d.hidden;
        const fundo = ausente ? "none" : (d.color ?? COR_BASE);
        const coresFaces = [...new Set(Object.values(d.faces).map((f) => f.color).filter((c): c is string => !!c))];
        const sel = d.tooth === selecionado;
        const r = Math.min(w, h) * 0.4;
        const titulo = [
          ...d.whole.map((m) => m.name),
          ...Object.values(d.faces).flatMap((f) => f.marks.map((m) => `${m.name} (${f.face})`)),
        ];
        return (
          <g
            key={d.tooth}
            className="cursor-pointer"
            opacity={d.in_arch ? 1 : 0.45}
            onClick={() => aoTocar(d)}
          >
            <title>{`Dente ${d.tooth}${titulo.length ? `: ${titulo.join(", ")}` : ""}`}</title>
            <rect
              x={-w / 2}
              y={-h / 2}
              width={w}
              height={h}
              rx={r}
              transform={`translate(${x},${y}) rotate(${angulo})`}
              fill={fundo}
              stroke={sel ? "var(--color-marca)" : "#374151"}
              strokeWidth={sel ? 3 : 1.6}
              strokeDasharray={ausente ? "4 3" : undefined}
              className="transition-opacity hover:opacity-80"
            />
            <text
              x={x}
              y={y + (coresFaces.length ? -1 : 3.5)}
              textAnchor="middle"
              fontSize={Math.min(11, w * 0.42)}
              fontWeight={600}
              fill={ausente ? "var(--color-texto-suave)" : contraste(fundo)}
              className="select-none"
              pointerEvents="none"
            >
              {d.tooth}
            </text>
            {/* Faces marcadas: bolinhas com as cores, abaixo do número. */}
            {coresFaces.slice(0, 3).map((c, i, arr) => (
              <circle
                key={c}
                cx={x + (i - (arr.length - 1) / 2) * 6}
                cy={y + 7}
                r={2.6}
                fill={c}
                stroke="#ffffff"
                strokeWidth={0.8}
                pointerEvents="none"
              />
            ))}
            {anotados?.has(d.tooth) && (
              <g pointerEvents="none">
                <circle cx={x + w * 0.38} cy={y - h * 0.38} r={6.5} fill="var(--color-marca)" stroke="#ffffff" strokeWidth={1.2} />
                <text x={x + w * 0.38} y={y - h * 0.38 + 3.3} textAnchor="middle" fontSize={9} fontWeight={700} fill="#ffffff">
                  ✎
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}
