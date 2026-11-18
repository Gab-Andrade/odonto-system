import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

/** Componentes básicos, pensados para toque: altura mínima de 44px. */

type Variante = "primario" | "secundario" | "perigo" | "fantasma";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-marca text-white hover:bg-marca-forte dark:text-slate-900",
  secundario: "border border-borda bg-painel text-texto hover:bg-fundo",
  perigo: "bg-perigo text-white hover:opacity-90",
  fantasma: "text-marca hover:bg-marca-suave",
};

export function Botao({
  variante = "primario",
  className = "",
  carregando = false,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; carregando?: boolean }) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || carregando}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTES[variante]} ${className}`}
    >
      {carregando && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}

export function Campo({
  rotulo,
  dica,
  erro,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { rotulo: string; dica?: string; erro?: string }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="font-medium text-texto-suave">{rotulo}</span>
      <input
        {...props}
        className="min-h-11 rounded-lg border border-borda bg-painel px-3 text-base text-texto outline-none focus:border-marca focus:ring-2 focus:ring-marca/30"
      />
      {dica && !erro && <span className="text-xs text-texto-suave">{dica}</span>}
      {erro && <span className="text-xs text-perigo">{erro}</span>}
    </label>
  );
}

export function Selecao({
  rotulo,
  children,
  className = "",
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { rotulo: string; children: ReactNode }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="font-medium text-texto-suave">{rotulo}</span>
      <select
        {...props}
        className="min-h-11 rounded-lg border border-borda bg-painel px-3 text-base text-texto outline-none focus:border-marca"
      >
        {children}
      </select>
    </label>
  );
}

export function AreaTexto({
  rotulo,
  className = "",
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { rotulo: string }) {
  return (
    <label className={`flex flex-col gap-1 text-sm ${className}`}>
      <span className="font-medium text-texto-suave">{rotulo}</span>
      <textarea
        {...props}
        className="min-h-24 rounded-lg border border-borda bg-painel p-3 text-base text-texto outline-none focus:border-marca"
      />
    </label>
  );
}

export function Cartao({
  titulo,
  acoes,
  children,
  className = "",
}: {
  titulo?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-xl border border-borda bg-painel p-4 shadow-sm ${className}`}>
      {(titulo || acoes) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {titulo && <h2 className="text-base font-semibold">{titulo}</h2>}
          {acoes && <div className="flex flex-wrap gap-2">{acoes}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

type Tom = "info" | "alerta" | "perigo" | "sucesso";
const TONS: Record<Tom, string> = {
  info: "border-borda bg-marca-suave text-texto",
  alerta: "border-alerta/40 bg-alerta-suave text-texto",
  perigo: "border-perigo/40 bg-perigo-suave text-texto",
  sucesso: "border-sucesso/40 bg-sucesso-suave text-texto",
};

export function Aviso({ tom = "info", children }: { tom?: Tom; children: ReactNode }) {
  return (
    <div role={tom === "perigo" ? "alert" : "status"} className={`rounded-lg border p-3 text-sm ${TONS[tom]}`}>
      {children}
    </div>
  );
}

export function Etiqueta({ tom = "info", children }: { tom?: Tom; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${TONS[tom]}`}>
      {children}
    </span>
  );
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-texto-suave">
      <Spinner /> {texto}
    </div>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="p-4 text-center text-sm text-texto-suave">{children}</p>;
}

export function ErroCarga({ erro }: { erro: unknown }) {
  const msg = erro instanceof Error ? erro.message : "Erro ao carregar.";
  return <Aviso tom="perigo">{msg}</Aviso>;
}

export function Titulo({ children, acoes }: { children: ReactNode; acoes?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-bold">{children}</h1>
      {acoes && <div className="flex flex-wrap gap-2">{acoes}</div>}
    </div>
  );
}

/** Abas grandes para tablet. */
export function Abas<T extends string>({
  abas,
  atual,
  aoMudar,
}: {
  abas: { id: T; rotulo: string }[];
  atual: T;
  aoMudar: (id: T) => void;
}) {
  return (
    <div role="tablist" className="nao-imprimir mb-4 flex gap-1 overflow-x-auto border-b border-borda">
      {abas.map((a) => (
        <button
          key={a.id}
          role="tab"
          type="button"
          aria-selected={a.id === atual}
          onClick={() => aoMudar(a.id)}
          className={`min-h-11 shrink-0 border-b-2 px-4 text-sm font-semibold ${
            a.id === atual
              ? "border-marca text-marca"
              : "border-transparent text-texto-suave hover:text-texto"
          }`}
        >
          {a.rotulo}
        </button>
      ))}
    </div>
  );
}
