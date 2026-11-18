/** Resposta de anamnese em texto (sim/não, listas). */
export function formatarResposta(valor: unknown): string {
  if (valor === true) return "sim";
  if (valor === false) return "não";
  if (Array.isArray(valor)) return valor.join(", ");
  if (valor === null || valor === undefined) return "—";
  return String(valor);
}
