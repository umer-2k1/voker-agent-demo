import {Composition} from 'remotion';
import {VokerShowreelV2} from './VokerShowreelV2';

export const MyComposition: React.FC = () => (
  <Composition
    id="VokerShowreelV2"
    component={VokerShowreelV2}
    durationInFrames={450}
    fps={30}
    width={1920}
    height={1080}
  />
);
