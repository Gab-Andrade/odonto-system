// Confere um .glb da arcada com o mesmo GLTFLoader do app: lista os dentes e confirma que
// cada um tem as cinco faces e a raiz como malhas com os nomes esperados.
//   node scripts/conferir-glb.mjs arcada.glb
import { readFileSync } from "node:fs";

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

const arquivo = process.argv[2];
if (!arquivo) {
  console.error("uso: node scripts/conferir-glb.mjs <arquivo.glb>");
  process.exit(2);
}
const dados = readFileSync(arquivo);
const buffer = dados.buffer.slice(dados.byteOffset, dados.byteOffset + dados.byteLength);
const gltf = await new GLTFLoader().parseAsync(buffer, "");

const dentes = new Map();
gltf.scene.traverse((obj) => {
  let m = /^dente_(\d{2})$/.exec(obj.name);
  if (m) dentes.set(m[1], dentes.get(m[1]) ?? new Set());
  m = /^(\d{2})_([MDOVL]|raiz)$/.exec(obj.name);
  if (m && obj instanceof THREE.Mesh) {
    dentes.set(m[1], (dentes.get(m[1]) ?? new Set()).add(m[2]));
  }
});
let falhas = 0;
for (const [dente, partes] of [...dentes].sort()) {
  const faltam = ["M", "D", "O", "V", "L", "raiz"].filter((p) => !partes.has(p));
  if (faltam.length) {
    falhas += 1;
    console.log(`dente ${dente}: faltam ${faltam.join(", ")}`);
  }
}
console.log(`${dentes.size} dentes; ${falhas ? `${falhas} com problema` : "todos com 5 faces e raiz"}`);
process.exit(falhas ? 1 : 0);
