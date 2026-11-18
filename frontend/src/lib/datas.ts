/** Datas e valores no formato brasileiro. A API trabalha em ISO com fuso. */

const FUSO = "America/Sao_Paulo";

export function hojeISO(): string {
  return dataLocalISO(new Date());
}

/** AAAA-MM-DD no fuso da clínica. */
export function dataLocalISO(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FUSO }).format(d);
}

export function somarDias(iso: string, dias: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const data = new Date(Date.UTC(a, m - 1, d + dias, 12));
  return data.toISOString().slice(0, 10);
}

/** Início do dia (00:00 no fuso local do navegador) em ISO com fuso. */
export function inicioDoDia(iso: string): string {
  return new Date(`${iso}T00:00:00`).toISOString();
}

export function dataBR(valor?: string | null): string {
  if (!valor) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(valor)) {
    const [a, m, d] = valor.split("-");
    return `${d}/${m}/${a}`;
  }
  return new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO }).format(new Date(valor));
}

export function horaBR(valor: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    timeZone: FUSO,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(valor));
}

export function dataHoraBR(valor?: string | null): string {
  if (!valor) return "—";
  return `${dataBR(valor)} ${horaBR(valor)}`;
}

export function dinheiro(valor?: string | number | null): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(
    Number(valor),
  );
}

export function idade(nascimento?: string | null): number | null {
  if (!nascimento) return null;
  const [a, m, d] = nascimento.split("-").map(Number);
  const hoje = new Date();
  let anos = hoje.getFullYear() - a;
  if (hoje.getMonth() + 1 < m || (hoje.getMonth() + 1 === m && hoje.getDate() < d)) anos -= 1;
  return anos;
}

export function mesAtual(): string {
  return hojeISO().slice(0, 7);
}

/** Data (AAAA-MM-DD) + hora (HH:MM) locais → ISO com fuso, como a API exige. */
export function instante(data: string, hora: string): string {
  return new Date(`${data}T${hora}:00`).toISOString();
}
