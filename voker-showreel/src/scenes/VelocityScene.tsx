import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, Eyebrow, Kicker, Pulse, SceneBase} from './Primitives';

const outputs = [
  ['INTENT', 'What did they need?', COLORS.mint],
  ['RESOLUTION', 'Did we solve it?', COLORS.green],
  ['CORRECTION', 'Where did it break?', COLORS.coral],
  ['PERFORMANCE', 'What ships next?', COLORS.cyan],
];

export const VelocityScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const tracker = interpolate(frame, [12, 84], [120, 1750], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <SceneBase exitFrom={86} accent={COLORS.mint}>
      <Eyebrow>FROM CALL → CLARITY</Eyebrow>
      <div style={{position: 'absolute', left: 108, top: 190, color: COLORS.cream, fontSize: 90, fontWeight: 800, letterSpacing: -5, lineHeight: 0.95}}>SEE WHAT<br /><span style={{color: COLORS.green}}>TO FIX.</span></div>
      <Kicker y={904}>Measure the outcome. Trace the cause. Improve with confidence.</Kicker>
      <div style={{position: 'absolute', left: 110, top: 702, right: 110, height: 4, background: '#f1f5e944'}} />
      <div style={{position: 'absolute', left: tracker, top: 685, width: 36, height: 36, borderRadius: '50%', background: COLORS.green, boxShadow: `0 0 50px ${COLORS.green}`}} />
      {outputs.map(([title, detail, color], i) => {
        const progress = spring({frame: frame - 10 - i * 10, fps, config: {damping: 18, stiffness: 110}});
        const x = 100 + i * 445;
        return <div key={title} style={{position: 'absolute', left: x, top: 410 + (i % 2) * 60, width: 350, height: 180, padding: 25, background: '#10271eec', borderLeft: `7px solid ${color}`, opacity: progress, translate: `0px ${(1 - progress) * 80}px`, scale: 0.88 + progress * 0.12}}>
          <div style={{color, fontSize: 21, fontWeight: 800, letterSpacing: 2}}>{String(i + 1).padStart(2, '0')}</div>
          <div style={{marginTop: 14, fontSize: 34, fontWeight: 800, letterSpacing: -1}}>{title}</div>
          <div style={{marginTop: 9, fontSize: 19, color: COLORS.muted}}>{detail}</div>
        </div>;
      })}
      <Pulse x={1510} y={106} color={COLORS.mint} size={220} from={14} />
    </SceneBase>
  );
};
