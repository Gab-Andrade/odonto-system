export const NOME_PLANO: Record<string, string> = {
  rascunho: "Rascunho",
  emitido: "Orçamento emitido",
  aprovado: "Aprovado",
  recusado: "Recusado",
  concluido: "Concluído",
  cancelado: "Cancelado",
};
export const TOM_PLANO: Record<string, "info" | "alerta" | "perigo" | "sucesso"> = {
  rascunho: "info",
  emitido: "alerta",
  aprovado: "sucesso",
  recusado: "perigo",
  concluido: "sucesso",
  cancelado: "perigo",
};

export const NOME_ITEM: Record<string, string> = {
  proposto: "Proposto",
  aprovado: "Aprovado",
  recusado: "Recusado",
  realizado: "Realizado",
  cancelado: "Cancelado",
};
export const TOM_ITEM: Record<string, "info" | "alerta" | "perigo" | "sucesso"> = {
  proposto: "info",
  aprovado: "alerta",
  recusado: "perigo",
  realizado: "sucesso",
  cancelado: "perigo",
};
