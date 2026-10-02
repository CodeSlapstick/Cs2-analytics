import type { ReactNode } from 'react';
import { ExplosionIcon } from './explosion-icon';
import { FlagIcon } from './flag-icon';
import { EliminationIcon } from './elimination-icon';
import { ClockIcon } from './clock-icon';
import { DefuserIcon } from './weapons/defuser-icon';

export type RoundEndReason =
  | 'target_bombed' | 'bomb_defused' | 'ct_killed' | 't_killed'
  | 'target_saved' | 'ct_surrender' | 't_surrender' | string;

function getRoundEndReasonIcon(roundEndReason: RoundEndReason): ReactNode {
  switch (roundEndReason) {
    case 'target_bombed':
      return <ExplosionIcon />;
    case 'bomb_defused':
      return <DefuserIcon />;
    case 'ct_killed':
    case 't_killed':
      return <EliminationIcon />;
    case 'target_saved':
      return <ClockIcon />;
    case 'ct_surrender':
    case 't_surrender':
      return <FlagIcon />;
    default:
      return null;
  }
}

type Props = {
  round: { endReason: RoundEndReason; winnerSide: 'ct' | 't' | null };
};

export function RoundEndReasonIcon({ round }: Props) {
  const icon = getRoundEndReasonIcon(round.endReason);

  return (
    <div
      className="w-20"
      style={{
        color: round.winnerSide === 'ct' ? 'var(--ct)' : round.winnerSide === 't' ? 'var(--t)' : 'currentColor',
      }}
    >
      {icon}
    </div>
  );
}
