import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, Eyebrow, SceneBase} from './Primitives';

export const FinaleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const mark = spring({frame: frame - 8, fps, config: {damping: 16, stiffness: 100}});
  const lines = interpolate(frame, [12, 48], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <SceneBase exitFrom={1000} accent={COLORS.green}>
      <Eyebrow>VOICE AGENT ANALYTICS</Eyebrow>
      <div style={{position: 'absolute', left: 108, top: 282, fontSize: 270, fontWeight: 800, letterSpacing: -18, lineHeight: 0.8, opacity: mark, translate: `${(1 - mark) * -160}px 0px`, scale: 0.8 + mark * 0.2}}>Voker<span style={{color: COLORS.green}}>.</span></div>
      <div style={{position: 'absolute', left: 118, top: 566, width: 1050, height: 4, background: COLORS.green, transformOrigin: 'left', scale: `${lines} 1`}} />
      <div style={{position: 'absolute', left: 118, top: 626, color: COLORS.cream, fontSize: 62, fontWeight: 650, letterSpacing: -3, opacity: lines}}>Make every conversation measurable.</div>
      <div style={{position: 'absolute', right: 130, bottom: 120, width: 420, height: 420, borderRadius: '50%', border: `2px solid ${COLORS.green}`, opacity: 0.22 + Math.sin(frame / 8) * 0.06, scale: 0.9 + mark * 0.22}} />
      <div style={{position: 'absolute', right: 268, bottom: 258, width: 146, height: 146, borderRadius: '50%', background: COLORS.green, opacity: 0.7, boxShadow: `0 0 90px ${COLORS.green}`}} />
    </SceneBase>
  );
};
