import React from "react";
import { spring } from "remotion";
import { MUNDO } from "./base";
import type { NombreNicho } from "./interiores";

/**
 * Tarjetas de interfaz que flotan sobre la escena (como el "Qué hacer hoy" de la referencia).
 * Muestran el resultado concreto sin una sola cifra: correo respondido, reunión agendada,
 * ficha completa, catálogo armado, render antes/después, o el caos de audios sueltos.
 */

export const TIPOS_TARJETA = ["correo", "agenda", "ficha", "catalogo", "render", "chat", "ninguna"] as const;
export type TipoTarjeta = (typeof TIPOS_TARJETA)[number];

const FUENTE = "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text',Helvetica,Arial,sans-serif";

const Fila: React.FC<{ activa?: boolean; titulo: string; sub: string; check?: boolean; aparece: number }> = ({ activa, titulo, sub, check, aparece }) => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: 16,
      padding: "14px 18px",
      borderRadius: 14,
      backgroundColor: activa ? "#f8e9ec" : "#f6f3ee",
      border: activa ? `2px solid ${MUNDO.vino}` : "2px solid transparent",
      opacity: aparece,
      transform: `translateX(${((1 - aparece) * 30).toFixed(1)}px)`,
    }}
  >
    <div style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: activa ? MUNDO.vino : "#c9c3b7", flex: "0 0 auto" }} />
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 26, fontWeight: 850, color: MUNDO.tinta }}>{titulo}</div>
      <div style={{ fontSize: 21, fontWeight: 600, color: "#7a746a" }}>{sub}</div>
    </div>
    {check ? <div style={{ fontSize: 30, fontWeight: 900, color: MUNDO.vino }}>✓</div> : null}
  </div>
);

const Encabezado: React.FC<{ titulo: string; etiqueta: string }> = ({ titulo, etiqueta }) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
    <div style={{ fontSize: 30, fontWeight: 900, color: MUNDO.tinta, letterSpacing: "-0.01em" }}>{titulo}</div>
    <div style={{ fontSize: 18, fontWeight: 900, letterSpacing: "0.12em", color: "#fff", backgroundColor: MUNDO.vino, padding: "6px 14px", borderRadius: 999 }}>{etiqueta}</div>
  </div>
);

export const Tarjeta: React.FC<{ tipo: TipoTarjeta; frameLocal: number; fps: number; nicho: NombreNicho }> = ({ tipo, frameLocal, fps }) => {
  if (frameLocal < 0 || tipo === "ninguna") return null;
  const k = spring({ frame: frameLocal, fps, config: { damping: 15, mass: 0.7, stiffness: 180 } });
  const fila = (i: number) => spring({ frame: Math.max(0, frameLocal - 6 - i * 4), fps, config: { damping: 16, stiffness: 200 } });

  let cuerpo: React.ReactNode = null;
  if (tipo === "correo") {
    cuerpo = (
      <>
        <Encabezado titulo="Bandeja de entrada" etiqueta="AL DÍA" />
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <Fila activa titulo="Cliente nuevo" sub="Quiere agendar una llamada" check aparece={fila(0)} />
          <Fila titulo="Seguimiento enviado" sub="Respondido sin que lo toques" check aparece={fila(1)} />
          <Fila titulo="Consulta de precios" sub="Pasada al dueño" aparece={fila(2)} />
        </div>
      </>
    );
  } else if (tipo === "agenda") {
    const horas = ["Mañana", "Mediodía", "Tarde"];
    cuerpo = (
      <>
        <Encabezado titulo="Tu agenda" etiqueta="AGENDADO" />
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {horas.map((h, i) => (
            <div key={h} style={{ display: "flex", gap: 14, alignItems: "center", opacity: fila(i) }}>
              <div style={{ width: 130, fontSize: 21, fontWeight: 700, color: "#7a746a" }}>{h}</div>
              <div
                style={{
                  flex: 1,
                  height: 56,
                  borderRadius: 12,
                  backgroundColor: i === 1 ? MUNDO.vino : "#f1ede6",
                  color: "#fff",
                  fontSize: 24,
                  fontWeight: 850,
                  display: "flex",
                  alignItems: "center",
                  padding: "0 18px",
                  transform: `scaleX(${i === 1 ? Math.min(1, fila(i)).toFixed(3) : 1})`,
                  transformOrigin: "left",
                }}
              >
                {i === 1 ? "Reunión con cliente nuevo ✓" : ""}
              </div>
            </div>
          ))}
        </div>
      </>
    );
  } else if (tipo === "ficha") {
    cuerpo = (
      <>
        <Encabezado titulo="Ficha técnica" etiqueta="LISTA PARA CORTE" />
        <div style={{ display: "flex", gap: 20 }}>
          <svg width={210} height={200} viewBox="0 0 210 200">
            <rect x={0} y={0} width={210} height={200} rx={14} fill="#f6f3ee" />
            <path d="M 50 40 L 80 30 Q 105 48 130 30 L 160 40 L 185 75 L 160 88 L 152 75 L 152 175 L 58 175 L 58 75 L 50 88 L 25 75 Z" fill="#fff" stroke={MUNDO.tinta} strokeWidth={3} />
            <line x1={58} y1={188} x2={152} y2={188} stroke={MUNDO.vino} strokeWidth={3} />
            <line x1={170} y1={88} x2={170} y2={175} stroke={MUNDO.vino} strokeWidth={3} />
            <line x1={80} y1={20} x2={130} y2={20} stroke={MUNDO.vino} strokeWidth={3} />
          </svg>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
            {["Medidas por talla", "Tela y forro", "Costuras y acabados", "Etiquetas"].map((t, i) => (
              <div key={t} style={{ display: "flex", justifyContent: "space-between", fontSize: 23, fontWeight: 800, color: MUNDO.tinta, padding: "10px 14px", borderRadius: 10, backgroundColor: "#f6f3ee", opacity: fila(i) }}>
                {t}
                <span style={{ color: MUNDO.vino }}>✓</span>
              </div>
            ))}
          </div>
        </div>
      </>
    );
  } else if (tipo === "catalogo") {
    const colores = [MUNDO.vino, "#d9a441", "#6c5a7d", "#3f5163", "#5f7a5c", "#c58c63"];
    cuerpo = (
      <>
        <Encabezado titulo="Catálogo" etiqueta="PUBLICADO" />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
          {colores.map((c, i) => (
            <div key={i} style={{ height: 118, borderRadius: 14, backgroundColor: "#f6f3ee", display: "flex", alignItems: "center", justifyContent: "center", transform: `scale(${Math.min(1, fila(i)).toFixed(3)})` }}>
              <div style={{ width: 54, height: 64, borderRadius: 10, backgroundColor: c, boxShadow: "0 8px 14px rgba(0,0,0,0.18)" }} />
            </div>
          ))}
        </div>
      </>
    );
  } else if (tipo === "render") {
    cuerpo = (
      <>
        <Encabezado titulo="Así va a quedar" etiqueta="ANTES DE OBRA" />
        <div style={{ display: "flex", gap: 12 }}>
          {["Hoy", "Render"].map((t, i) => (
            <div key={t} style={{ flex: 1, height: 220, borderRadius: 14, overflow: "hidden", position: "relative", backgroundColor: i === 0 ? "#cfc8ba" : "#efe5d2", opacity: fila(i) }}>
              <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 80, backgroundColor: i === 0 ? "#bdb6a8" : MUNDO.madera }} />
              {i === 1 ? (
                <>
                  <div style={{ position: "absolute", left: 40, bottom: 70, width: 160, height: 56, borderRadius: 10, backgroundColor: "#6f7f8f" }} />
                  <div style={{ position: "absolute", left: 70, top: 30, width: 70, height: 56, border: "4px solid #3d3a35", backgroundColor: "#fff" }} />
                  <div style={{ position: "absolute", right: 30, bottom: 70, width: 30, height: 70, borderRadius: 15, backgroundColor: "#6f8a5e" }} />
                </>
              ) : (
                <div style={{ position: "absolute", left: 30, top: 40, width: 80, height: 60, backgroundColor: "#b5765a", opacity: 0.8 }} />
              )}
              <div style={{ position: "absolute", left: 12, top: 12, fontSize: 18, fontWeight: 900, letterSpacing: "0.1em", color: "#fff", backgroundColor: i === 0 ? "#2f2f35" : MUNDO.vino, padding: "4px 12px", borderRadius: 999 }}>
                {t.toUpperCase()}
              </div>
            </div>
          ))}
        </div>
      </>
    );
  } else if (tipo === "chat") {
    cuerpo = (
      <>
        <Encabezado titulo="Así llega el pedido" etiqueta="A CIEGAS" />
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ alignSelf: i === 1 ? "flex-end" : "flex-start", display: "flex", alignItems: "center", gap: 12, padding: "14px 20px", borderRadius: 22, backgroundColor: i === 1 ? "#f8e9ec" : "#f1ede6", opacity: fila(i) }}>
              <div style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: MUNDO.vino }} />
              <svg width={170} height={34}>
                {Array.from({ length: 20 }).map((_, k) => {
                  const h = 6 + ((k * 7 + i * 5) % 22);
                  return <rect key={k} x={k * 8.5} y={17 - h / 2} width={4} height={h} rx={2} fill="#7a746a" />;
                })}
              </svg>
            </div>
          ))}
          <div style={{ alignSelf: "flex-start", fontSize: 24, fontWeight: 800, color: MUNDO.tinta, padding: "12px 20px", borderRadius: 22, backgroundColor: "#f1ede6", opacity: fila(3) }}>
            ¿Así o más ajustado?
          </div>
        </div>
      </>
    );
  }

  return (
    <div
      style={{
        position: "absolute",
        left: 150,
        width: 640,
        bottom: 410,
        padding: 26,
        borderRadius: 28,
        backgroundColor: "#ffffff",
        boxShadow: "0 30px 60px rgba(10,10,10,0.28)",
        fontFamily: FUENTE,
        opacity: Math.min(1, k * 1.5),
        transform: `translateY(${((1 - k) * 80).toFixed(1)}px) scale(${(0.9 + 0.1 * k).toFixed(3)})`,
      }}
    >
      {cuerpo}
    </div>
  );
};
