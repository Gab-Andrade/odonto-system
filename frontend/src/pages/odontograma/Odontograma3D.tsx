import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { baixar, type Schemas } from "../../api/client";
import { Cartao, Carregando, ErroCarga } from "../../components/ui";
import type { DenteVis } from "./Dente2D";
import { superior } from "./geometria";

const COR_NATURAL = "#f1ece1";
const COR_RAIZ = "#e6d9bf";
const COR_GENGIVA = "#e0959b";
const COR_SELECAO = new THREE.Color("#14b8a6");
const ABERTURA = 0.2; // radianos de cada arcada com a boca aberta (~11°)

type Arcadas = "ambas" | "superior" | "inferior";
const ROTULO: Record<Arcadas, string> = { ambas: "Ambas as arcadas", superior: "Arcada superior", inferior: "Arcada inferior" };

/** O GLB da arcada não tem dado de paciente: pode ficar em cache entre pacientes. */
async function carregarArcada(url: string): Promise<THREE.Group> {
  const blob = await baixar(url);
  const gltf = await new GLTFLoader().parseAsync(await blob.arrayBuffer(), "");
  return gltf.scene;
}

/** Nó "16_O" → dente 16, face O; "16_raiz" → dente 16, sem face; "dente_16" → dente 16. */
function lerNo(nome: string): { dente: number; face: string | null } | null {
  let m = /^dente_(\d{2})$/.exec(nome);
  if (m) return { dente: Number(m[1]), face: null };
  m = /^(\d{2})_([MDOVL]|raiz)$/.exec(nome);
  if (m) return { dente: Number(m[1]), face: m[2] === "raiz" ? null : m[2] };
  return null;
}

/**
 * Gengiva: um tubo de seção elíptica que corre pelos colos dos dentes, deslocado para o lado
 * das raízes (cobre as raízes e a borda do colo). Os colos vêm do posicionamento da arcada
 * (`placement.translation`, em mm; a arcada é uma parábola, então ordenar por x segue a curva).
 */
function gengiva(colos: THREE.Vector3[], sup: boolean): THREE.Mesh | null {
  const ord = [...colos].sort((a, b) => a.x - b.x);
  // Dentição mista: decíduo e permanente na mesma vaga viram um ponto só.
  const pts: THREE.Vector3[] = [];
  for (const p of ord) {
    const u = pts[pts.length - 1];
    if (u && u.distanceTo(p) < 3) u.lerp(p, 0.5);
    else pts.push(p.clone());
  }
  if (pts.length < 2) return null;
  // Passa um pouco do último dente de cada lado, para fechar arredondado atrás dele.
  const ponta = (a: THREE.Vector3, b: THREE.Vector3) => a.clone().add(a.clone().sub(b).setY(0).normalize().multiplyScalar(4));
  pts.unshift(ponta(pts[0], pts[1]));
  pts.push(ponta(pts[pts.length - 1], pts[pts.length - 2]));

  const curva = new THREE.CatmullRomCurve3(pts, false, "centripetal");
  // Posição (0–1 ao longo da curva) de cada dente, para recortar a borda entre eles.
  const acum = [0];
  for (let i = 1; i < pts.length; i++) acum.push(acum[i - 1] + pts[i].distanceTo(pts[i - 1]));
  const centros = acum.slice(1, -1).map((s) => s / acum[acum.length - 1]);
  const xMax = Math.max(...pts.map((p) => Math.abs(p.x)), 1);

  const N = 360;
  const R = 28;
  const ALT = 7; // meia altura da faixa
  const DESLOC = 6; // centro da faixa, a partir do colo, para o lado da raiz (borda ~1 mm na coroa)
  const PAPILA = 3; // quanto a gengiva sobe entre um dente e outro
  const lado = sup ? 1 : -1;
  // Seção "quadrada de cantos redondos" (superelipse): abraça o dente em vez de virar um tubo.
  const sq = (v: number) => Math.sign(v) * Math.abs(v) ** 0.45;
  const pos: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const c = curva.getPointAt(t);
    const tg = curva.getTangentAt(t);
    const n = new THREE.Vector3(tg.z, 0, -tg.x).normalize();
    const f = Math.min(1, Math.min(t, 1 - t) / 0.03) ** 0.5; // pontas arredondadas
    // Mais fina nos anteriores, mais grossa nos molares.
    const larg = 3.8 + 2 * Math.min(1, Math.abs(c.x) / xMax);
    // Distância ao centro do dente mais próximo: 0 no centro, 1 no meio do caminho (papila).
    let psi = 0;
    const k = centros.findIndex((ct, j) => j < centros.length - 1 && t >= ct && t <= centros[j + 1]);
    if (k >= 0) psi = 1 - Math.abs(1 - (2 * (t - centros[k])) / (centros[k + 1] - centros[k]));
    const papila = PAPILA * (1 - Math.sqrt(Math.max(0, 1 - psi * psi)));
    for (let j = 0; j < R; j++) {
      const a = (2 * Math.PI * j) / R;
      const u = larg * f * sq(Math.cos(a));
      let v = ALT * f * sq(Math.sin(a)); // + para a raiz, − para a coroa
      if (v < 0) v -= papila * (-v / ALT) ** 2;
      pos.push(c.x + n.x * u, c.y + lado * (DESLOC + v), c.z + n.z * u);
      if (i < N) {
        const p0 = i * R + j;
        const p1 = i * R + ((j + 1) % R);
        idx.push(p0, p0 + R, p1, p1, p0 + R, p1 + R);
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  const malha = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: COR_GENGIVA, roughness: 0.6, side: THREE.DoubleSide }));
  malha.name = "gengiva";
  malha.raycast = () => {}; // o toque atravessa a gengiva e pega o dente
  return malha;
}

interface Montagem {
  raiz: THREE.Object3D;
  sup: THREE.Group;
  inf: THREE.Group;
  gengivas: THREE.Mesh[];
  /** Meio da boca (entre os incisivos e os últimos molares): centro de giro da câmera. */
  centro: THREE.Vector3;
}

/**
 * Copia o modelo (as cores são do paciente) e separa as arcadas em dois grupos com a
 * dobradiça atrás dos últimos dentes, para abrir a boca girando cada uma.
 */
function montar(modelo: THREE.Group, dentes: DenteVis[]): Montagem {
  const raiz = modelo.clone(true);
  const naArcada = dentes.filter((d) => d.in_arch);
  const colo = (d: DenteVis) => new THREE.Vector3(...(d.placement.translation as [number, number, number]));
  const zFundo = Math.min(...naArcada.map((d) => d.placement.translation[2]), 0);
  const dobradica = new THREE.Vector3(0, 0, zFundo - 8);

  const sup = new THREE.Group();
  const inf = new THREE.Group();
  for (const g of [sup, inf]) {
    g.position.copy(dobradica);
    raiz.add(g);
  }
  raiz.updateMatrixWorld(true);
  const nos: THREE.Object3D[] = [];
  raiz.traverse((o) => {
    if (/^dente_\d{2}$/.test(o.name)) nos.push(o);
  });
  for (const no of nos) (superior(Number(no.name.slice(6))) ? sup : inf).attach(no);

  const gengivas: THREE.Mesh[] = [];
  for (const [grupo, ehSup] of [[sup, true], [inf, false]] as const) {
    const g = gengiva(naArcada.filter((d) => superior(d.tooth) === ehSup).map(colo), ehSup);
    if (!g) continue;
    g.position.copy(dobradica).negate(); // geometria em coordenadas da arcada
    grupo.add(g);
    gengivas.push(g);
  }
  const zs = naArcada.map((d) => d.placement.translation[2]);
  // Um pouco atrás do meio exato (−4 mm): os molares giram mais perto da tela.
  const centro = new THREE.Vector3(0, 0, (zs.length ? (Math.min(...zs) + Math.max(...zs)) / 2 : 0) - 4);
  return { raiz, sup, inf, gengivas, centro };
}

/** Um passo da animação: aproxima cada arcada do ângulo-alvo. */
function girar(m: Montagem, aberta: boolean, dt: number) {
  const k = Math.min(1, dt * 6);
  const alvo = aberta ? ABERTURA : 0;
  // A frente fica em +Z: girar negativo em X sobe a superior, positivo desce a inferior.
  m.sup.rotation.x += (-alvo - m.sup.rotation.x) * k;
  m.inf.rotation.x += (alvo - m.inf.rotation.x) * k;
}

function Abertura({ montagem, aberta }: { montagem: Montagem; aberta: boolean }) {
  useFrame((_, dt) => girar(montagem, aberta, dt));
  return null;
}

/** Visibilidade e cores conforme as opções e as marcações do paciente. */
function pintar(
  m: Montagem,
  porDente: Map<number, DenteVis>,
  op: { selecionado: number | null; raizes: boolean; comGengiva: boolean; arcadas: Arcadas },
) {
  m.sup.visible = op.arcadas !== "inferior";
  m.inf.visible = op.arcadas !== "superior";
  for (const g of m.gengivas) {
    g.visible = op.comGengiva;
    const mat = g.material as THREE.MeshStandardMaterial;
    // Com raízes à mostra, a gengiva fica translúcida para deixá-las aparecer.
    mat.transparent = op.raizes;
    mat.opacity = op.raizes ? 0.4 : 1;
    mat.depthWrite = !op.raizes;
    mat.needsUpdate = true;
  }
  m.raiz.traverse((obj) => {
    const info = lerNo(obj.name);
    if (!info) return;
    const d = porDente.get(info.dente);
    if (obj.name.startsWith("dente_")) {
      obj.visible = !(d?.hidden ?? false);
      return;
    }
    if (!(obj instanceof THREE.Mesh)) return;
    const raiz = obj.name.endsWith("_raiz");
    if (raiz) obj.visible = op.raizes;
    const face = info.face ? Object.values(d?.faces ?? {}).find((f) => f.face === info.face) : null;
    const cor = raiz ? COR_RAIZ : (face?.color ?? d?.color ?? COR_NATURAL);
    const material = new THREE.MeshStandardMaterial({ color: cor, roughness: 0.45, metalness: 0.05 });
    if (info.dente === op.selecionado) {
      material.emissive = COR_SELECAO;
      material.emissiveIntensity = 0.25;
    }
    (obj.material as THREE.Material | undefined)?.dispose?.();
    obj.material = material;
  });
}

export default function Odontograma3D({
  vis,
  selecionado,
  aoTocar,
  compacto = false,
}: {
  vis: Schemas["VisualizationOut"];
  selecionado: number | null;
  aoTocar: (d: DenteVis, face: string | null) => void;
  /** Ao lado da boca 2D, só para ver: mais baixo. */
  compacto?: boolean;
}) {
  const [raizes, setRaizes] = useState(false);
  const [comGengiva, setComGengiva] = useState(true);
  const [aberta, setAberta] = useState(false);
  const [arcadas, setArcadas] = useState<Arcadas>("ambas");
  const modelo = useQuery({
    queryKey: ["glb", vis.arch_model_url],
    queryFn: () => carregarArcada(vis.arch_model_url),
    staleTime: Infinity,
  });

  // Remonta só quando muda a arcada (posições), não a cada marcação.
  const chavePosicoes = vis.teeth
    .filter((d) => d.in_arch)
    .map((d) => `${d.tooth}:${d.placement.translation.join(",")}`)
    .join(";");
  const montagem = useMemo(
    () => (modelo.data ? montar(modelo.data, vis.teeth) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [modelo.data, chavePosicoes],
  );
  const porDente = useMemo(() => new Map(vis.teeth.map((d) => [d.tooth, d])), [vis.teeth]);

  useEffect(() => {
    if (montagem) pintar(montagem, porDente, { selecionado, raizes, comGengiva, arcadas });
  }, [montagem, porDente, selecionado, raizes, comGengiva, arcadas]);

  function clique(ev: ThreeEvent<MouseEvent>) {
    ev.stopPropagation();
    const info = lerNo(ev.object.name);
    const d = info && porDente.get(info.dente);
    if (d) aoTocar(d, info.face);
  }

  return (
    <Cartao className={compacto ? "h-full" : ""}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <select
          value={arcadas}
          onChange={(e) => setArcadas(e.target.value as Arcadas)}
          aria-label="Arcadas visíveis"
          className="min-h-10 rounded-lg border border-borda bg-painel px-3 font-semibold"
        >
          {(Object.keys(ROTULO) as Arcadas[]).map((a) => (
            <option key={a} value={a}>
              {ROTULO[a]}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setAberta((a) => !a)}
          aria-pressed={aberta}
          className={`flex min-h-10 items-center gap-2 rounded-lg border border-marca/30 px-3 font-semibold text-marca ${aberta ? "bg-marca/20" : "bg-marca-suave"} hover:bg-marca/20`}
        >
          {aberta ? "Fechar a boca" : "Abrir a boca"}
        </button>
        <label className="flex min-h-10 items-center gap-2 px-1">
          <input type="checkbox" className="size-5" checked={comGengiva} onChange={(e) => setComGengiva(e.target.checked)} />
          Gengiva
        </label>
        <label className="flex min-h-10 items-center gap-2 px-1">
          <input type="checkbox" className="size-5" checked={raizes} onChange={(e) => setRaizes(e.target.checked)} />
          Raízes
        </label>
      </div>
      <p className="mb-2 text-xs text-texto-suave">
        Arraste para girar, pinça/roda para aproximar, {compacto ? "toque num dente para ver." : "toque numa face para marcar."}
      </p>
      {modelo.isLoading && <Carregando texto="Carregando o modelo 3D…" />}
      {modelo.error && <ErroCarga erro={modelo.error} />}
      {montagem && (
        <div
          className={`${compacto ? "h-[26rem]" : "h-[60vh] min-h-80"} w-full touch-none overflow-hidden rounded-lg bg-gradient-to-b from-slate-100 to-slate-300 dark:from-slate-800 dark:to-slate-950`}
        >
          <Canvas
            camera={{ position: [0, 8, montagem.centro.z + 122], fov: 35, near: 1, far: 1000 }}
            dpr={[1, 2]}
          >
            <ambientLight intensity={0.6} />
            <directionalLight position={[30, 60, 80]} intensity={1.6} />
            <directionalLight position={[-40, -30, 40]} intensity={0.5} />
            <primitive object={montagem.raiz} onClick={clique} />
            <Abertura montagem={montagem} aberta={aberta} />
            {/* Gira em torno do meio da boca, para os dentes de trás chegarem perto da tela. */}
            <OrbitControls
              makeDefault
              target={montagem.centro.toArray()}
              enablePan={false}
              minDistance={25}
              maxDistance={220}
            />
          </Canvas>
        </div>
      )}
    </Cartao>
  );
}
