import {AbsoluteFill, Composition, Sequence} from 'remotion';
import {AnalysisScene} from './scenes/AnalysisScene';
import {CaptureScene} from './scenes/CaptureScene';
import {FinaleScene} from './scenes/FinaleScene';
import {IntroScene} from './scenes/IntroScene';
import {VelocityScene} from './scenes/VelocityScene';

export const VokerShowreel: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: '#07120f', overflow: 'hidden'}}>
      <Sequence durationInFrames={110} name="01 — Voice is not text">
        <IntroScene />
      </Sequence>
      <Sequence from={85} durationInFrames={125} name="02 — Capture every signal">
        <CaptureScene />
      </Sequence>
      <Sequence from={190} durationInFrames={125} name="03 — System analysis">
        <AnalysisScene />
      </Sequence>
      <Sequence from={295} durationInFrames={105} name="04 — From call to clarity">
        <VelocityScene />
      </Sequence>
      <Sequence from={380} durationInFrames={70} name="05 — Voker lockup">
        <FinaleScene />
      </Sequence>
    </AbsoluteFill>
  );
};

export const MyComposition: React.FC = () => {
  return (
    <Composition
      id="VokerShowreel"
      component={VokerShowreel}
      durationInFrames={450}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
