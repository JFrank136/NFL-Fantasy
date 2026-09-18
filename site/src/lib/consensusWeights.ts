// src/lib/consensusWeights.ts
//
// Mirrors Draft/config/settings.yaml's `consensus.weights`, which is the
// already-tuned source-weighting used by the Draft tool's live draft board.
// Reused here (rather than inventing a new weighting) for the Weekly tab's
// "Aggregate weekly rank" column.
//
// NOTE: the Draft tool's yaml key is "smyth"; this pipeline's `source`
// column value for the same analyst is "smythe" -- SourceWeights below
// uses this project's spelling, mapped explicitly at the yaml boundary
// (there is no live yaml read here, this is a hand-copied snapshot -- if
// Draft/config/settings.yaml is retuned, update this file to match).

export interface SourceWeights {
  draftsharks: number
  boone: number
  smythe: number
}

export const CONSENSUS_WEIGHTS: Record<string, SourceWeights> = {
  default: { draftsharks: 0.50, boone: 0.30, smythe: 0.20 },
  QB: { draftsharks: 0.40, boone: 0.40, smythe: 0.20 },
}

export function weightsForPosition(position: string): SourceWeights {
  return CONSENSUS_WEIGHTS[position] ?? CONSENSUS_WEIGHTS.default
}
