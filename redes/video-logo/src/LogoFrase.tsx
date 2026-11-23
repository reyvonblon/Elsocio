import { z } from "zod";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export const logoFraseSchema = z.object({
  frase: z.string(),
});

type Props = z.infer<typeof logoFraseSchema>;

const Frase: React.FC<{ frase: string }> = ({ frase }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0.5 * fps, 1.3 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const translateY = interpolate(frame, [0.5 * fps, 1.3 * fps], [16, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <div
      style={{
        fontFamily:
          "-apple-system,BlinkMacSystemFont,'SF Pro Text','Segoe UI',Helvetica,Arial,sans-serif",
        fontWeight: 700,
        fontSize: 64,
        lineHeight: 1.25,
        color: "#ffffff",
        textAlign: "center",
        letterSpacing: "-0.01em",
        maxWidth: 900,
        opacity,
        translate: `0px ${translateY}px`,
      }}
    >
      {frase}
    </div>
  );
};

const Logo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = interpolate(frame, [0, 0.6 * fps], [0.85, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.spring({ damping: 200 }),
    output: "perceptual-scale",
  });
  const opacity = interpolate(frame, [0, 0.5 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const mustacheDraw = interpolate(frame, [0.2 * fps, 1 * fps], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <svg
      viewBox="0 0 680 344"
      width={340}
      height={172}
      style={{ scale, opacity, marginTop: 90 }}
    >
      <defs>
        <linearGradient id="mustacheLine" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#a8a8ae" />
          <stop offset="16%" stopColor="#e8e8ed" />
          <stop offset="38%" stopColor="#ffffff" />
          <stop offset="50%" stopColor="#d8d8de" />
          <stop offset="62%" stopColor="#ffffff" />
          <stop offset="84%" stopColor="#e8e8ed" />
          <stop offset="100%" stopColor="#a8a8ae" />
        </linearGradient>
        <linearGradient id="hatSilk" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#19191b" />
          <stop offset="28%" stopColor="#2a2a2d" />
          <stop offset="60%" stopColor="#0d0d0e" />
          <stop offset="100%" stopColor="#151517" />
        </linearGradient>
        <linearGradient id="hatRim" x1="0" y1="0" x2="1" y2="0.4">
          <stop offset="0%" stopColor="#ffffff" stopOpacity={0.88} />
          <stop offset="55%" stopColor="#d2d2d7" stopOpacity={0.62} />
          <stop offset="100%" stopColor="#ffffff" stopOpacity={0.72} />
        </linearGradient>
        <linearGradient id="tieRed" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#b22337" />
          <stop offset="50%" stopColor="#9c1c2e" />
          <stop offset="100%" stopColor="#721220" />
        </linearGradient>
      </defs>

      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        <g
          stroke="url(#mustacheLine)"
          strokeWidth={8}
          fill="none"
          strokeDasharray={1}
          pathLength={1}
          style={{
            strokeDashoffset: interpolate(mustacheDraw, [0, 1], [1, 0]),
          }}
        >
          <path d="M 340 224 C 375 234, 430 240, 470 232 C 495 227, 512 218, 522 206" />
          <path d="M 340 224 C 305 234, 250 240, 210 232 C 185 227, 168 218, 158 206" />
        </g>
      </g>

      <g>
        <path
          d="M 220.8 205 L 236.2 205 L 232.8 219.5 L 238.5 284 L 228.5 302 L 218.5 284 L 224.2 219.5 Z"
          fill="#0a0a0a"
          stroke="#0a0a0a"
          strokeWidth={5.5}
          strokeLinejoin="round"
        />
        <path
          d="M 224.3 219.5 L 232.7 219.5 L 238 283.5 L 228.5 301.5 L 219 283.5 Z"
          fill="url(#tieRed)"
        />
      </g>

      <text
        y={198}
        fontFamily="'Playfair Display', Georgia, serif"
        fontWeight={800}
        fontSize={140}
        fill="#ffffff"
      >
        <tspan x={73}>El</tspan>
        <tspan x={249}>Socio</tspan>
      </text>

      <g>
        <g stroke="#0a0a0a" strokeLinecap="round" fill="none">
          <circle cx={272} cy={143} r={14.8} strokeWidth={4.4} />
          <circle cx={311} cy={143} r={14.8} strokeWidth={4.4} />
          <path d="M 286.6 142 Q 291.5 136.5, 296.4 142" strokeWidth={4} />
          <line x1={257} y1={141.5} x2={252} y2={139} strokeWidth={4} />
          <line x1={326} y1={141.5} x2={331} y2={139} strokeWidth={4} />
        </g>
        <g stroke="#ffffff" fill="none" strokeLinecap="round">
          <circle cx={272} cy={143} r={14.8} strokeWidth={2.2} />
          <circle cx={311} cy={143} r={14.8} strokeWidth={2.2} />
          <path d="M 286.8 142 Q 291.5 136.8, 296.2 142" strokeWidth={1.9} />
          <line x1={257.2} y1={141.5} x2={252.2} y2={139} strokeWidth={1.9} />
          <line x1={325.8} y1={141.5} x2={330.8} y2={139} strokeWidth={1.9} />
        </g>
      </g>

      <g>
        <path
          d="M 522 104 C 522 99.5, 543 96.5, 567.5 96.5 C 592 96.5, 613 99.5, 613 104 C 613 108.5, 592 111.5, 567.5 111.5 C 543 111.5, 522 108.5, 522 104 Z"
          fill="#ffffff"
        />
        <path
          d="M 549 49 L 586 49 L 586 100 L 549 100 Z"
          fill="url(#hatSilk)"
          stroke="url(#hatRim)"
          strokeWidth={2}
          strokeLinejoin="round"
        />
        <rect x={549} y={88} width={37} height={8} fill="#ffffff" />
        <rect
          x={549}
          y={88}
          width={37}
          height={8}
          fill="none"
          stroke="#0a0a0a"
          strokeWidth={1.4}
        />
      </g>
    </svg>
  );
};

export const LogoFrase: React.FC<Props> = ({ frase }) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a0a",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 90px",
      }}
    >
      <Frase frase={frase} />
      <Logo />
    </AbsoluteFill>
  );
};
