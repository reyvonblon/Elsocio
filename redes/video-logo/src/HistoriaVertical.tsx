import React from "react";
import { z } from "zod";
import { AbsoluteFill } from "remotion";
import { PALETA, type TemaVisual } from "./EscenasIsometricas";
import { elegirIndicePalabraClave } from "./ReelVertical";

export const historiaVerticalSchema = z.object({
  gancho: z.string(),
  subtexto: z.string().optional(),
  cierre: z.string().optional(),
  badge: z.string().optional(),
  tema: z.enum(["oscuro", "crema"]).optional(),
});

type Props = z.infer<typeof historiaVerticalSchema>;

const FUENTE =
  "-apple-system,BlinkMacSystemFont,'SF Pro Display','SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif";

export const HistoriaVertical: React.FC<Props> = ({
  gancho,
  subtexto = "",
  cierre = "Responde esta historia con tu caso",
  badge = "HISTORIA",
  tema = "oscuro",
}) => {
  const esCrema = (tema as TemaVisual) === "crema";
  const colorFondo = esCrema ? PALETA.crema : PALETA.tinta;
  const colorTexto = esCrema ? PALETA.tinta : PALETA.blanco;
  const colorSub = esCrema ? "#2c2823" : "#d5d5dc";
  const grilla = esCrema
    ? `linear-gradient(to right, rgba(10,10,10,0.055) 1px, transparent 1px),
       linear-gradient(to bottom, rgba(10,10,10,0.055) 1px, transparent 1px)`
    : `radial-gradient(rgba(255,255,255,0.13) 1.6px, transparent 1.6px)`;

  const palabras = (gancho || "").trim().split(/\s+/).filter(Boolean);
  const idxClave = elegirIndicePalabraClave(palabras);
  const fontSize = gancho.length <= 36 ? 76 : gancho.length <= 58 ? 66 : 56;
  const badgeLimpio = (badge || "HISTORIA").replace(/[0-9$%]/g, "").trim().toUpperCase() || "HISTORIA";

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colorFondo,
        backgroundImage: grilla,
        backgroundSize: esCrema ? "54px 54px" : "44px 44px",
        padding: "240px 88px 310px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        fontFamily: FUENTE,
        color: colorTexto,
      }}
    >
      {/* Cabecera dentro de zona segura de Instagram Stories */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 22px",
            borderRadius: 999,
            backgroundColor: esCrema ? "rgba(10,10,10,0.07)" : "rgba(255,255,255,0.08)",
            border: `1.5px solid ${esCrema ? "rgba(10,10,10,0.16)" : "rgba(255,255,255,0.16)"}`,
          }}
        >
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: PALETA.vino,
              display: "inline-block",
            }}
          />
          <span
            style={{
              fontSize: 22,
              fontWeight: 800,
              letterSpacing: "0.12em",
            }}
          >
            {badgeLimpio}
          </span>
        </div>

        <span
          style={{
            fontSize: 21,
            fontWeight: 800,
            letterSpacing: "0.12em",
            opacity: 0.72,
          }}
        >
          EL SOCIO
        </span>
      </div>

      {/* Cuerpo editorial central */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 36,
        }}
      >
        <div
          style={{
            fontSize: 21,
            fontWeight: 800,
            letterSpacing: "0.16em",
            color: PALETA.vino,
          }}
        >
          VERDAD DE NEGOCIO
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            columnGap: 16,
            rowGap: 12,
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
                  color: esClave ? PALETA.blanco : colorTexto,
                  backgroundColor: esClave ? PALETA.vino : "transparent",
                  padding: esClave ? "3px 18px 7px" : "3px 0",
                  borderRadius: esClave ? 12 : 0,
                }}
              >
                {pal}
              </span>
            );
          })}
        </div>

        <div
          style={{
            width: 112,
            height: 6,
            borderRadius: 999,
            backgroundColor: PALETA.vino,
          }}
        />

        {subtexto.trim() ? (
          <div
            style={{
              fontSize: 38,
              fontWeight: 600,
              lineHeight: 1.34,
              letterSpacing: "-0.01em",
              color: colorSub,
              maxWidth: 860,
            }}
          >
            {subtexto.trim()}
          </div>
        ) : null}
      </div>

      {/* Pie con CTA y emblema de El Socio */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          gap: 34,
          width: "100%",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "22px 34px",
            borderRadius: 16,
            backgroundColor: PALETA.vino,
            color: PALETA.blanco,
            fontSize: 29,
            fontWeight: 800,
            letterSpacing: "-0.01em",
          }}
        >
          {cierre.trim() || "Responde esta historia con tu caso"}
        </div>

        <div
          style={{
            width: "100%",
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
            <svg width={44} height={34} viewBox="0 0 68 52" fill="none">
              <rect x={20} y={4} width={28} height={20} rx={2} fill={colorTexto} />
              <rect x={20} y={19} width={28} height={4} fill={PALETA.vino} />
              <ellipse cx={34} cy={25} rx={24} ry={3.5} fill={colorTexto} />
              <circle cx={24} cy={38} r={6.5} stroke={colorTexto} strokeWidth={2.6} />
              <circle cx={44} cy={38} r={6.5} stroke={colorTexto} strokeWidth={2.6} />
              <path d="M 30.5 38 Q 34 34.5 37.5 38" stroke={colorTexto} strokeWidth={2.4} />
            </svg>
            <span
              style={{
                fontFamily: "Georgia, 'Times New Roman', serif",
                fontWeight: 800,
                fontSize: 34,
                color: colorTexto,
              }}
            >
              El Socio
            </span>
          </div>

          <span
            style={{
              fontSize: 20,
              fontWeight: 800,
              letterSpacing: "0.08em",
              opacity: 0.65,
            }}
          >
            SOLUCIONES REALES
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
