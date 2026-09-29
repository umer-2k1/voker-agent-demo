import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, Eyebrow, Kicker, SceneBase, Word} from './Primitives';

const stages = [
  ['TRACE + METRICS', 'raw evidence', COLORS.cyan],
  ['DETERMINISTIC', 'rules + thresholds', COLORS.yellow],
  ['SEMANTIC', 'intent + outcome', COLORS.mint],
  ['FINDINGS', 'certainty + severity', COLORS.green],
];

export const AnalysisScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scan = interpolate(frame, [4, 106], [0, 960], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <SceneBase exitFrom={106} accent={COLORS.yellow}>
      <Eyebrow color={COLORS.yellow}>VOKER SYSTEM ANALYSIS</Eyebrow>
      <Word from={4} x={106} y={220} size={112}>RAW SIGNALS</Word>
      <Word from={16} x={108} y={326} size={112} color={COLORS.yellow}>BECOME</Word>
      <Word from={28} x={106} y={432} size={112} outline color={COLORS.cream}>CLARITY.</Word>
      <Kicker y={912}>The insight is useful because the evidence is attached.</Kicker>
      <div style={{position: 'absolute', left: 820, top: 246, width: 1010, height: 530}}>
        <div style={{position: 'absolute', left: 8, right: 8, top: 230, height: 2, background: '#f1f5e955'}} />
        <div style={{position: 'absolute', left: scan, top: 212, width: 38, height: 38, background: COLORS.green, borderRadius: '50%', boxShadow: `0 0 38px ${COLORS.green}`}} />
        {stages.map(([title, detail, color], i) => {
          const progress = spring({frame: frame - 13 - i * 12, fps, config: {damping: 16, stiffness: 125}});
          const x = i * 248;
          return <div key={title} style={{position: 'absolute', left: x, top: 126, width: 220, height: 214, padding: 22, border: `1px solid ${color}99`, background: '#0e261ddf', opacity: progress, translate: `0px ${(1 - progress) * (i % 2 ? 90 : -90)}px`}}>
            <div style={{width: 16, height: 16, borderRadius: '50%', background: color, boxShadow: `0 0 22px ${color}`, marginBottom: 36}} />
            <div style={{fontSize: 25, lineHeight: 1, fontWeight: 800, color: COLORS.cream}}>{title}</div>
            <div style={{fontSize: 18, marginTop: 13, color}}>{detail}</div>
          </div>;
        })}
      </div>
    </SceneBase>
  );
};
