import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export const COLORS = {
  ink: '#07120f',
  cream: '#f1f5e9',
  muted: '#9aafa5',
  green: '#b6ff67',
  mint: '#6df4c5',
  cyan: '#86dbff',
  coral: '#ff8768',
  yellow: '#ffd56a',
};

export const eased = (frame: number, input: [number, number], output: [number, number]) =>
  interpolate(frame, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

export const SceneBase: React.FC<{
  children: React.ReactNode;
  exitFrom: number;
  accent?: string;
}> = ({children, exitFrom, accent = COLORS.green}) => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 200, stiffness: 120}});
  const exit = interpolate(frame, [exitFrom, exitFrom + 16], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.6, 0, 1, 0.4),
  });
  const drift = Math.sin(frame / 24) * 24;

  return (
    <AbsoluteFill
      style={{
        opacity: enter * exit,
        backgroundColor: COLORS.ink,
        color: COLORS.cream,
        fontFamily: 'SystemDisplay, Arial, sans-serif',
        overflow: 'hidden',
      }}
    >
      <div style={{position: 'absolute', inset: -180, opacity: 0.38, backgroundImage: `radial-gradient(circle at 18% 22%, ${accent}50 0, transparent 23%), radial-gradient(circle at 78% 68%, #2b8b7552 0, transparent 26%), linear-gradient(115deg, transparent 0%, #15392d88 50%, transparent 100%)`, translate: `${drift}px ${-drift}px`, filter: 'blur(18px)'}} />
      <div style={{position: 'absolute', inset: 0, opacity: 0.16, backgroundImage: 'linear-gradient(#8bf8c322 1px, transparent 1px), linear-gradient(90deg, #8bf8c322 1px, transparent 1px)', backgroundSize: '72px 72px', maskImage: 'linear-gradient(to bottom, transparent, black 18%, black 80%, transparent)'}} />
      <div style={{position: 'absolute', top: 52, left: 72, width: width - 144, height: height - 104, border: '1px solid #b6ff6733'}} />
      {children}
    </AbsoluteFill>
  );
};

export const Eyebrow: React.FC<{children: React.ReactNode; color?: string}> = ({children, color = COLORS.green}) => (
  <div style={{position: 'absolute', top: 96, left: 108, display: 'flex', alignItems: 'center', gap: 16, fontSize: 22, fontWeight: 700, letterSpacing: 3, color}}>
    <span style={{width: 44, height: 2, background: color}} />
    {children}
  </div>
);

export const Word: React.FC<{
  children: string;
  from: number;
  x: number;
  y: number;
  size?: number;
  color?: string;
  delayExit?: number;
  outline?: boolean;
}> = ({children, from, x, y, size = 156, color = COLORS.cream, delayExit = 1000, outline = false}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const progress = spring({frame: frame - from, fps, config: {damping: 18, stiffness: 120, mass: 0.8}});
  const exit = delayExit < 1000 ? eased(frame, [delayExit, delayExit + 12], [1, 0]) : 1;
  return (
    <div style={{position: 'absolute', left: x, top: y, fontSize: size, fontWeight: 800, letterSpacing: size > 110 ? -8 : -2, lineHeight: 0.86, color: outline ? 'transparent' : color, WebkitTextStroke: outline ? `2px ${color}` : undefined, opacity: progress * exit, translate: `${eased(progress, [0, 1], [-130, 0])}px ${eased(progress, [0, 1], [42, 0])}px`, scale: 0.86 + progress * 0.14, filter: `blur(${(1 - progress) * 14}px)`}}>
      {children}
    </div>
  );
};

export const Kicker: React.FC<{children: React.ReactNode; x?: number; y?: number; color?: string}> = ({children, x = 108, y = 920, color = COLORS.muted}) => (
  <div style={{position: 'absolute', left: x, top: y, color, fontSize: 30, lineHeight: 1.15, letterSpacing: -0.5, fontWeight: 500}}>{children}</div>
);

export const Pulse: React.FC<{x: number; y: number; color?: string; size?: number; from?: number}> = ({x, y, color = COLORS.green, size = 160, from = 0}) => {
  const frame = useCurrentFrame() - from;
  const halo = interpolate(frame % 34, [0, 33], [0.18, 0], {extrapolateRight: 'clamp'});
  const scale = interpolate(frame % 34, [0, 33], [0.6, 1.8], {extrapolateRight: 'clamp'});
  return <div style={{position: 'absolute', left: x, top: y, width: size, height: size, borderRadius: '50%', border: `2px solid ${color}`, opacity: halo, scale}} />;
};
