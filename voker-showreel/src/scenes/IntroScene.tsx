import {interpolate, useCurrentFrame} from 'remotion';
import {COLORS, Eyebrow, Kicker, Pulse, SceneBase, Word} from './Primitives';

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const lineScale = interpolate(frame, [18, 72], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const waveform = Array.from({length: 19}, (_, i) => 36 + Math.abs(Math.sin(frame / 6 + i * 0.72)) * 138);
  return (
    <SceneBase exitFrom={92} accent={COLORS.green}>
      <Eyebrow>VOKER / VOICE OBSERVABILITY</Eyebrow>
      <Word from={4} x={106} y={262}>VOICE</Word>
      <Word from={16} x={426} y={425} color={COLORS.green}>IS NOT</Word>
      <Word from={28} x={108} y={590} outline delayExit={90}>TEXT.</Word>
      <Kicker>Real conversations are messy.<br />Your observability should see all of it.</Kicker>
      <div style={{position: 'absolute', right: 182, top: 206, width: 390, height: 390, borderRadius: '50%', border: `2px solid ${COLORS.green}`, opacity: 0.55, scale: 0.94 + Math.sin(frame / 14) * 0.04}} />
      <Pulse x={1210} y={275} size={250} from={8} />
      <div style={{position: 'absolute', right: 262, top: 322, display: 'flex', alignItems: 'center', gap: 10, height: 160}}>
        {waveform.map((h, index) => <div key={index} style={{width: 10, height: h, borderRadius: 8, background: index % 3 === 0 ? COLORS.mint : COLORS.green, opacity: 0.55 + index / 50}} />)}
      </div>
      <div style={{position: 'absolute', left: 108, top: 834, width: 900, height: 4, background: COLORS.green, transformOrigin: 'left', scale: `${lineScale} 1`}} />
    </SceneBase>
  );
};
