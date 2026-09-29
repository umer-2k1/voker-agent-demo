import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, Eyebrow, Kicker, SceneBase} from './Primitives';

const signals = [
  ['01', 'TRANSCRIPT', COLORS.mint], ['02', 'TOOL CALL', COLORS.cyan], ['03', 'LLM TRACE', COLORS.yellow],
  ['04', 'LATENCY', COLORS.coral], ['05', 'HANDOFF', COLORS.green], ['06', 'ERROR', '#ff6f91'],
];

export const CaptureScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return (
    <SceneBase exitFrom={106} accent={COLORS.cyan}>
      <Eyebrow color={COLORS.cyan}>WHAT VOKER CAPTURES</Eyebrow>
      <div style={{position: 'absolute', left: 108, top: 198, fontSize: 102, fontWeight: 800, letterSpacing: -6, lineHeight: 0.92}}>EVERY<br /><span style={{color: COLORS.cyan}}>SIGNAL.</span></div>
      <Kicker y={916}>The conversation, the execution, the experience.</Kicker>
      <div style={{position: 'absolute', right: 112, top: 178, width: 1010, height: 700}}>
        {signals.map(([index, label, color], i) => {
          const progress = spring({frame: frame - 10 - i * 8, fps, config: {damping: 18, stiffness: 140}});
          const x = (i % 2) * 480;
          const y = Math.floor(i / 2) * 190;
          const jitter = Math.sin(frame / 7 + i) * 7;
          return <div key={label} style={{position: 'absolute', left: x, top: y, width: 438, height: 148, padding: '24px 28px', border: `1px solid ${color}88`, background: '#10261fbe', boxShadow: `0 0 48px ${color}18`, opacity: progress, translate: `${(1 - progress) * 100}px ${(1 - progress) * (i % 2 ? 45 : -45)}px`, rotate: `${(1 - progress) * (i % 2 ? 5 : -5)}deg`}}>
            <div style={{display: 'flex', justifyContent: 'space-between', color, fontSize: 18, fontWeight: 700, letterSpacing: 2}}><span>{index}</span><span>LIVE</span></div>
            <div style={{marginTop: 18, color: COLORS.cream, fontSize: 38, letterSpacing: -1.5, fontWeight: 700}}>{label}</div>
            <div style={{position: 'absolute', left: 28, bottom: 18, width: 270 + jitter * 5, height: 3, background: color, opacity: 0.75}} />
          </div>;
        })}
      </div>
      <div style={{position: 'absolute', left: 108, top: 544, width: 430, height: 430, borderRadius: '50%', border: `1px solid ${COLORS.cyan}88`, opacity: 0.5, scale: 0.75 + interpolate(frame, [0, 100], [0, 0.25], {extrapolateRight: 'clamp'})}} />
    </SceneBase>
  );
};
