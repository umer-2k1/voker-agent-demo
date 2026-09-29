import {Audio} from '@remotion/media';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const C = {
  night: '#070b16',
  panel: '#0e1427',
  white: '#f6f8ff',
  muted: '#99a3ba',
  blue: '#78a9ff',
  cyan: '#72e8ff',
  lime: '#c7ff76',
  coral: '#ff8370',
  amber: '#ffd37a',
};

const ease = (frame: number, start: number, end: number, from = 0, to = 1) =>
  interpolate(frame, [start, end], [from, to], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

const SoundDesign: React.FC = () => (
  <>
    {[0, 88, 178, 268, 358].map((from) => (
      <Sequence key={from} from={from} durationInFrames={28}>
        <Audio src="https://remotion.media/whoosh.wav" volume={0.045} />
      </Sequence>
    ))}
    <Sequence from={130} durationInFrames={20}><Audio src="https://remotion.media/mouse-click.wav" volume={0.055} /></Sequence>
    <Sequence from={247} durationInFrames={20}><Audio src="https://remotion.media/mouse-click.wav" volume={0.05} /></Sequence>
    <Sequence from={401} durationInFrames={30}><Audio src="https://remotion.media/ding.wav" volume={0.07} /></Sequence>
  </>
);

const Canvas: React.FC<{children: React.ReactNode; exitAt: number; accent: string}> = ({children, exitAt, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 200, stiffness: 100}});
  const exit = ease(frame, exitAt, exitAt + 15, 1, 0);
  const orbit = Math.sin(frame / 18) * 20;
  return (
    <AbsoluteFill style={{background: C.night, color: C.white, overflow: 'hidden', opacity: enter * exit, fontFamily: 'Arial, Helvetica, sans-serif'}}>
      <div style={{position: 'absolute', inset: -140, backgroundImage: `radial-gradient(circle at 72% 18%, ${accent}50 0, transparent 22%), radial-gradient(circle at 22% 80%, #3453b555 0, transparent 30%)`, filter: 'blur(18px)', translate: `${orbit}px ${-orbit}px`}} />
      <div style={{position: 'absolute', inset: 0, opacity: 0.18, backgroundImage: 'linear-gradient(#ffffff14 1px, transparent 1px), linear-gradient(90deg, #ffffff14 1px, transparent 1px)', backgroundSize: '64px 64px', maskImage: 'linear-gradient(to bottom, transparent, black 20%, black 80%, transparent)'}} />
      <div style={{position: 'absolute', inset: 56, border: '1px solid #ffffff28'}} />
      {children}
    </AbsoluteFill>
  );
};

const Label: React.FC<{children: React.ReactNode; color?: string}> = ({children, color = C.cyan}) => (
  <div style={{position: 'absolute', top: 94, left: 110, color, fontSize: 21, fontWeight: 800, letterSpacing: 3, display: 'flex', gap: 16, alignItems: 'center'}}><span style={{width: 42, height: 2, background: color}} />{children}</div>
);

const Big: React.FC<{children: React.ReactNode; from: number; x: number; y: number; color?: string; size?: number}> = ({children, from, x, y, color = C.white, size = 118}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - from, fps, config: {damping: 18, stiffness: 125}});
  return <div style={{position: 'absolute', left: x, top: y, fontSize: size, lineHeight: 0.86, fontWeight: 800, letterSpacing: -6, color, opacity: p, translate: `${(1 - p) * -130}px ${(1 - p) * 35}px`, scale: 0.88 + p * 0.12, filter: `blur(${(1 - p) * 13}px)`}}>{children}</div>;
};

const Caption: React.FC<{children: React.ReactNode; y?: number}> = ({children, y = 908}) => <div style={{position: 'absolute', left: 112, top: y, color: C.muted, fontSize: 28, lineHeight: 1.2, letterSpacing: -0.3}}>{children}</div>;

const MiniWave: React.FC<{x: number; y: number; width?: number; color?: string; from?: number}> = ({x, y, width = 340, color = C.cyan, from = 0}) => {
  const frame = useCurrentFrame() - from;
  const bars = Array.from({length: 28}, (_, i) => 10 + Math.abs(Math.sin(frame / 5 + i * 0.65)) * (28 + (i % 3) * 9));
  return <div style={{position: 'absolute', left: x, top: y, width, height: 80, display: 'flex', gap: 6, alignItems: 'center'}}>{bars.map((height, i) => <div key={i} style={{height, width: 5, borderRadius: 8, background: i % 5 === 0 ? C.lime : color, opacity: 0.65}} />)}</div>;
};

const Node: React.FC<{x: number; y: number; title: string; detail: string; color: string; from: number}> = ({x, y, title, detail, color, from}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - from, fps, config: {damping: 18, stiffness: 120}});
  return <div style={{position: 'absolute', left: x, top: y, width: 262, height: 150, padding: 22, background: '#101a31de', border: `1px solid ${color}a8`, opacity: p, translate: `${(1 - p) * 65}px ${(1 - p) * 35}px`, boxShadow: `0 0 36px ${color}1c`}}><div style={{width: 14, height: 14, borderRadius: '50%', background: color, boxShadow: `0 0 18px ${color}`}} /><div style={{marginTop: 20, fontWeight: 800, fontSize: 28, letterSpacing: -1}}>{title}</div><div style={{marginTop: 8, fontSize: 17, color}}>{detail}</div></div>;
};

const CallScene: React.FC = () => {
  const frame = useCurrentFrame();
  const route = ease(frame, 12, 76, 0, 1);
  return <Canvas exitAt={94} accent={C.cyan}>
    <Label>VOICE AGENTS ARE SYSTEMS</Label>
    <Big from={4} x={110} y={230}>A CALL IS<br /><span style={{color: C.cyan}}>MORE THAN AUDIO.</span></Big>
    <Caption>Every turn crosses speech, models, tools, and the customer experience.</Caption>
    <div style={{position: 'absolute', left: 1040, top: 250, width: 620, height: 510}}>
      <div style={{position: 'absolute', left: 38, right: 38, top: 258, height: 3, background: '#ffffff35'}} />
      <div style={{position: 'absolute', left: 38, top: 258, width: 544 * route, height: 3, background: C.cyan, boxShadow: `0 0 20px ${C.cyan}`}} />
      {['CALLER', 'STT', 'LLM', 'TOOLS', 'TTS'].map((item, i) => {
        const x = i * 132;
        const y = i % 2 === 0 ? 150 : 330;
        const pulse = 0.75 + Math.sin(frame / 8 + i) * 0.12;
        return <div key={item} style={{position: 'absolute', left: x, top: y, width: 116, textAlign: 'center', opacity: route > i / 5 ? 1 : 0.18}}><div style={{margin: 'auto', width: 54, height: 54, borderRadius: '50%', background: i === 2 ? C.lime : '#18264a', border: `2px solid ${i === 2 ? C.lime : C.cyan}`, boxShadow: `0 0 26px ${i === 2 ? C.lime : C.cyan}66`, scale: pulse}} /><div style={{marginTop: 18, fontSize: 16, fontWeight: 800, letterSpacing: 1.2}}>{item}</div></div>;
      })}
      <MiniWave x={142} y={228} width={270} from={12} />
    </div>
  </Canvas>;
};

const CaptureScene: React.FC = () => {
  const items = [
    ['TRANSCRIPTS', 'conversation turns', C.cyan], ['TOOL RESULTS', 'execution evidence', C.lime], ['LLM CALLS', 'inputs + outputs', C.amber],
    ['LATENCY', 'STT · LLM · TTS', C.coral], ['HANDOFFS', 'interruptions + talk-over', C.blue], ['ERRORS + COST', 'timeouts · tokens · spend', '#fb77b7'],
  ];
  return <Canvas exitAt={110} accent={C.blue}>
    <Label color={C.blue}>INSTRUMENT THE ENTIRE EXPERIENCE</Label>
    <Big from={4} x={110} y={190} size={106}>CAPTURE<br /><span style={{color: C.blue}}>WITHOUT BLIND SPOTS.</span></Big>
    <Caption y={900}>The raw call becomes a searchable, comparable record.</Caption>
    <div style={{position: 'absolute', left: 830, top: 182, width: 980, height: 700}}>
      {items.map(([title, detail, color], i) => <Node key={title} x={(i % 2) * 466} y={Math.floor(i / 2) * 190} title={title} detail={detail} color={color} from={8 + i * 8} />)}
    </div>
  </Canvas>;
};

const DurableScene: React.FC = () => {
  const frame = useCurrentFrame();
  const stages = [
    ['RAW INBOX', 'commit events first', C.cyan], ['WORKER', 'project the evidence', C.amber], ['CANONICAL DATA', 'sessions · turns · spans', C.lime], ['FINDINGS', 'evidence-linked analysis', C.coral],
  ];
  return <Canvas exitAt={110} accent={C.amber}>
    <Label color={C.amber}>BUILT FOR INVESTIGATION</Label>
    <Big from={4} x={110} y={220}>NO EVIDENCE<br /><span style={{color: C.amber}}>LEFT BEHIND.</span></Big>
    <Caption>Capture is durable. Analysis is asynchronous. The trace stays useful either way.</Caption>
    <div style={{position: 'absolute', left: 740, top: 254, width: 1080, height: 500}}>
      <div style={{position: 'absolute', left: 35, right: 20, top: 245, height: 2, background: '#ffffff3b'}} />
      <div style={{position: 'absolute', left: 20, top: 230, width: Math.min(980, Math.max(0, (frame - 10) * 12)), height: 32, borderRadius: 20, background: `${C.lime}33`, filter: 'blur(10px)'}} />
      {stages.map(([title, detail, color], i) => <Node key={title} x={i * 260} y={i % 2 ? 275 : 95} title={title} detail={detail} color={color} from={10 + i * 12} />)}
    </div>
  </Canvas>;
};

const InsightScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - 28, fps, config: {damping: 18, stiffness: 120}});
  return <Canvas exitAt={110} accent={C.lime}>
    <Label>ANALYZE WHAT HAPPENED</Label>
    <Big from={4} x={110} y={200}>FROM TRACE<br /><span style={{color: C.lime}}>TO DECISION.</span></Big>
    <Caption>Intent, resolution, corrections, voice quality, and agent performance—backed by evidence.</Caption>
    <div style={{position: 'absolute', left: 800, top: 170, width: 1000, height: 710}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: 1000, height: 192, padding: 28, background: '#101a31f2', border: `1px solid ${C.lime}9a`, opacity: p, translate: `0px ${(1 - p) * -70}px`}}>
        <div style={{color: C.lime, fontSize: 18, fontWeight: 800, letterSpacing: 2}}>AGENT V1.4 → V1.5</div>
        <div style={{display: 'flex', gap: 76, marginTop: 23}}><div><b style={{fontSize: 48}}>+12.4%</b><span style={{marginLeft: 12, color: C.muted, fontSize: 20}}>resolution rate</span></div><div><b style={{fontSize: 48, color: C.coral}}>−31%</b><span style={{marginLeft: 12, color: C.muted, fontSize: 20}}>tool failures</span></div></div>
      </div>
      <Node x={0} y={250} title="INTENT" detail="refund request · 92% confidence" color={C.cyan} from={10} />
      <Node x={324} y={250} title="OUTCOME" detail="resolved · observed evidence" color={C.lime} from={18} />
      <Node x={648} y={250} title="VOICE QUALITY" detail="talk-over detected · medium" color={C.coral} from={26} />
      <div style={{position: 'absolute', left: 0, top: 465, width: 910, padding: '20px 25px', borderLeft: `5px solid ${C.amber}`, background: '#151b2ee8', opacity: ease(frame, 42, 62)}}><span style={{color: C.amber, fontSize: 18, fontWeight: 800, letterSpacing: 2}}>EVIDENCE-BACKED FINDING</span><span style={{marginLeft: 22, fontSize: 22}}>Slow tool response preceded interruption; inspect span <b>tool.lookup_order</b>.</span></div>
    </div>
  </Canvas>;
};

const McpScene: React.FC = () => {
  const frame = useCurrentFrame();
  const line = ease(frame, 10, 40);
  return <Canvas exitAt={1000} accent={C.cyan}>
    <Label color={C.cyan}>EVIDENCE IN THE WORKFLOW</Label>
    <Big from={4} x={110} y={188}>ASK.<br /><span style={{color: C.cyan}}>TRACE.</span><br />IMPROVE.</Big>
    <Caption y={890}>Read-only MCP connects the evidence to Codex, Claude, and Cursor.</Caption>
    <div style={{position: 'absolute', left: 900, top: 240, width: 820, height: 450}}>
      <div style={{position: 'absolute', left: 0, top: 122, width: 720 * line, height: 3, background: C.cyan, boxShadow: `0 0 24px ${C.cyan}`}} />
      <Node x={0} y={50} title="AI CLIENT" detail="ask in your workflow" color={C.cyan} from={8} />
      <Node x={285} y={50} title="VOKER MCP" detail="read-only tools + evidence" color={C.lime} from={14} />
      <Node x={570} y={50} title="PROJECT DATA" detail="scoped to environment" color={C.amber} from={20} />
      <div style={{position: 'absolute', left: 24, top: 285, display: 'flex', gap: 16, opacity: ease(frame, 24, 36)}}>{['READ-ONLY', 'ENVIRONMENT-SCOPED', 'REDACTED'].map((badge) => <span key={badge} style={{border: `1px solid ${C.cyan}77`, color: C.cyan, padding: '11px 15px', fontSize: 15, fontWeight: 800, letterSpacing: 1.2}}>{badge}</span>)}</div>
      <div style={{position: 'absolute', left: 24, top: 360, fontSize: 74, fontWeight: 800, letterSpacing: -5, opacity: ease(frame, 30, 42)}}>Voker<span style={{color: C.lime}}>.</span></div>
    </div>
  </Canvas>;
};

export const VokerShowreelV2: React.FC = () => (
  <AbsoluteFill>
    <SoundDesign />
    <Sequence durationInFrames={104}><CallScene /></Sequence>
    <Sequence from={86} durationInFrames={124}><CaptureScene /></Sequence>
    <Sequence from={188} durationInFrames={124}><DurableScene /></Sequence>
    <Sequence from={290} durationInFrames={124}><InsightScene /></Sequence>
    <Sequence from={392} durationInFrames={58}><McpScene /></Sequence>
  </AbsoluteFill>
);
