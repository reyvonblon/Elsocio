import React from "react";
import { z } from "zod";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { PALETA, type TemaVisual } from "./EscenasIsometricas";
import { elegirIndicePalabraClave } from "./ReelVertical";

// Carrusel de Instagram 1080x1350: cada FRAME es una lámina.
// generar_carrusel.sh renderiza todos los frames con --sequence y los nombra content_XXXX_01.png, _02...
// Lámina 1 = portada (gancho), las del medio = una idea cada una, la última = cierre de venta.
export const carruselLaminasSchema = z.object({
  laminas: z.array(z.string()),
  badge: z.string().optional(),
  tema: z.enum(["oscuro", "crema"]).optional(),
});

type Props = z.infer<typeof carruselLaminasSchema>;

const FUENTE =
  "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

export const duracionCarrusel = (props: Partial<Props>): number =>
  Math.max(1, props.laminas?.length ?? 1);

const limpiar = (t: string) => (t || "").replace(/[0-9$%]/g, "").replace(/\s+/g, " ").trim();

const Emblema: React.FC<{ color: string; acento: string }> = ({ color, acento }) => (
  <div style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
    <svg width={44} height={34} viewBox="0 0 68 52" fill="none">
      <rect x={20} y={4} width={28} height={20} rx={2} fill={color} />
      <rect x={20} y={19} width={28} height={4} fill={acento} />
      <ellipse cx={34} cy={25} rx={24} ry={3.5} fill={color} />
      <circle cx={24} cy={38} r={6.5} stroke={color} strokeWidth={2.6} />
      <circle cx={44} cy={38} r={6.5} stroke={color} strokeWidth={2.6} />
      <path d="M 30.5 38 Q 34 34.5 37.5 38" stroke={color} strokeWidth={2.4} />
    </svg>
    <span
      style={{
        fontFamily: "Georgia, 'Times New Roman', serif",
        fontWeight: 800,
        fontSize: 34,
        color,
      }}
    >
      El Socio
    </span>
  </div>
);

const Puntos: React.FC<{ total: number; actual: number; color: string; acento: string }> = ({
  total,
  actual,
  color,
  acento,
}) => (
  <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
    {new Array(total).fill(0).map((_, i) => (
      <span
        key={i}
        style={{
          width: i === actual ? 34 : 12,
          height: 12,
          borderRadius: 999,
          backgroundColor: i === actual ? acento : color,
          opacity: i === actual ? 1 : 0.28,
          display: "inline-block",
        }}
      />
    ))}
  </div>
);

const TextoConClave: React.FC<{ texto: string; fontSize: number; color: string }> = ({
  texto,
  fontSize,
  color,
}) => {
  const palabras = texto.split(/\s+/).filter(Boolean);
  const idxClave = elegirIndicePalabraClave(palabras);
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        columnGap: Math.round(fontSize * 0.24),
        rowGap: Math.round(fontSize * 0.16),
        fontSize,
        fontWeight: 900,
        lineHeight: 1.1,
        letterSpacing: "-0.03em",
      }}
    >
      {palabras.map((pal, idx) => {
        const esClave = idx === idxClave;
        return (
          <span
            key={`${idx}-${pal}`}
            style={{
              display: "inline-block",
              color: esClave ? PALETA.blanco : color,
              backgroundColor: esClave ? PALETA.vino : "transparent",
              padding: esClave ? "2px 16px 6px" : "2px 0",
              borderRadius: esClave ? 12 : 0,
            }}
          >
            {pal}
          </span>
        );
      })}
    </div>
  );
};

export const CarruselLaminas: React.FC<Props> = ({ laminas, badge = "EL SOCIO", tema = "oscuro" }) => {
  const frame = useCurrentFrame();
  const total = Math.max(1, laminas.length);
  const idx = Math.min(total - 1, Math.max(0, frame));
  const texto = limpiar(laminas[idx] ?? "");
  const esPortada = idx === 0;
  const esCierre = idx === total - 1 && total > 1;

  const esCrema = (tema as TemaVisual) === "crema";
  const fondo = esCierre ? PALETA.vino : esCrema ? PALETA.crema : PALETA.tinta;
  const colorTexto = esCierre ? PALETA.blanco : esCrema ? PALETA.tinta : PALETA.blanco;
  const acento = esCierre ? PALETA.blanco : PALETA.vino;
  const grilla = esCierre
    ? "none"
    : esCrema
      ? `linear-gradient(to right, rgba(10,10,10,0.055) 1px, transparent 1px),
         linear-gradient(to bottom, rgba(10,10,10,0.055) 1px, transparent 1px)`
      : `radial-gradient(rgba(255,255,255,0.13) 1.6px, transparent 1.6px)`;
  const badgeLimpio = limpiar(badge).toUpperCase() || "EL SOCIO";

  const largo = texto.length;
  const fontSize = esPortada
    ? largo <= 40 ? 92 : largo <= 70 ? 78 : 66
    : largo <= 60 ? 70 : largo <= 100 ? 60 : largo <= 140 ? 52 : 46;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: fondo,
        backgroundImage: grilla,
        backgroundSize: esCrema ? "54px 54px" : "44px 44px",
        padding: "96px 92px 92px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        fontFamily: FUENTE,
        color: colorTexto,
      }}
    >
      {/* Cabecera */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 22px",
            borderRadius: 999,
            backgroundColor: esCierre
              ? "rgba(255,255,255,0.14)"
              : esCrema
                ? "rgba(10,10,10,0.07)"
                : "rgba(255,255,255,0.08)",
            border: `1.5px solid ${esCrema && !esCierre ? "rgba(10,10,10,0.16)" : "rgba(255,255,255,0.18)"}`,
          }}
        >
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: esCierre ? PALETA.blanco : PALETA.vino,
              display: "inline-block",
            }}
          />
          <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: "0.12em" }}>{badgeLimpio}</span>
        </div>
        <Puntos total={total} actual={idx} color={colorTexto} acento={acento} />
      </div>

      {/* Cuerpo */}
      <div style={{ display: "flex", flexDirection: "column", gap: 34 }}>
        {esPortada ? (
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "0.16em", color: PALETA.vino }}>
            VERDAD DE NEGOCIO
          </div>
        ) : null}
        {esCierre ? (
          <div
            style={{
              fontSize: fontSize + 6,
              fontWeight: 900,
              lineHeight: 1.1,
              letterSpacing: "-0.03em",
              color: PALETA.blanco,
            }}
          >
            {texto}
          </div>
        ) : (
          <TextoConClave texto={texto} fontSize={fontSize} color={colorTexto} />
        )}
        <div style={{ width: 112, height: 6, borderRadius: 999, backgroundColor: acento }} />
      </div>

      {/* Pie */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Emblema color={colorTexto} acento={esCierre ? PALETA.vinoOscuro : PALETA.vino} />
        {esPortada ? (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 14,
              padding: "18px 30px",
              borderRadius: 16,
              backgroundColor: PALETA.vino,
              color: PALETA.blanco,
              fontSize: 26,
              fontWeight: 800,
              letterSpacing: "0.04em",
            }}
          >
            DESLIZA
            <svg width={34} height={20} viewBox="0 0 34 20" fill="none">
              <path d="M2 10 H30 M22 2 L30 10 L22 18" stroke={PALETA.blanco} strokeWidth={3.4} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        ) : (
          <span style={{ fontSize: 20, fontWeight: 800, letterSpacing: "0.08em", opacity: 0.65 }}>
            {esCierre ? "ESCRÍBENOS POR MENSAJE DIRECTO" : "SOLUCIONES REALES"}
          </span>
        )}
      </div>
    </AbsoluteFill>
  );
};
