import type { Schemas } from "../../api/client";

export type StatusAgenda = Schemas["AppointmentStatus"];

export const NOME_STATUS: Record<StatusAgenda, string> = {
  agendado: "Agendado",
  confirmado: "Confirmado",
  atendido: "Atendido",
  falta: "Falta",
  cancelado: "Cancelado",
};

export const TOM_STATUS: Record<StatusAgenda, "info" | "alerta" | "perigo" | "sucesso"> = {
  agendado: "info",
  confirmado: "sucesso",
  atendido: "sucesso",
  falta: "perigo",
  cancelado: "alerta",
};

/** Transições permitidas (espelha agenda/regras.py; a API é quem valida). */
export const PROXIMOS: Record<StatusAgenda, StatusAgenda[]> = {
  agendado: ["confirmado", "atendido", "falta", "cancelado"],
  confirmado: ["atendido", "falta", "cancelado"],
  atendido: [],
  falta: [],
  cancelado: [],
};
