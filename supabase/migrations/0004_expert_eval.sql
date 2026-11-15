-- Expert accuracy evaluation + shadow weighting (src/expert_eval/).
-- Additive only: new tables, no changes to existing in_season_* tables.
-- All natural keys are upsert targets, so weekly reruns are idempotent.
-- Raw ranking history (in_season_rankings) is never touched; snapshots here
-- are a frozen copy of the pre-kickoff row chosen for each player.

create table public.expert_eval_config (
  version text primary key,
  spec jsonb not null,
  created_at timestamptz not null default now()
);

-- Actual results (facts; may be corrected by nflverse -> data_as_of tracks it).
create table public.expert_eval_results (
  season int not null,
  week int not null,
  canonical_name text not null,
  position text not null,
  team text,
  played boolean not null,
  inactive boolean not null default false,   -- confirmed Out on the final injury report
  pts_std double precision,
  pts_half double precision,
  pts_ppr double precision,
  data_as_of timestamptz not null default now(),
  primary key (season, week, canonical_name, position)
);

-- Frozen evaluation input: the last ranking each source published for a
-- player before that player's own kickoff.
create table public.expert_eval_snapshots (
  season int not null,
  week int not null,
  source text not null,
  scoring text not null,                      -- 'half-ppr' | 'ppr'
  canonical_name text not null,
  position text not null,
  raw_rank int,                               -- as published
  scaled_rank double precision not null,      -- on the QB / FLEX (RB,WR,TE) scale the site blends on
  pulled_at timestamptz,                      -- null for archive backfills with no pull time
  kickoff_at timestamptz,
  provenance text not null default 'pipeline',
  primary key (season, week, source, scoring, canonical_name, position)
);

-- Frozen roster pool per week/format (so a source added later is scored on
-- the identical player pool and scenarios).
create table public.expert_eval_pool (
  season int not null,
  week int not null,
  scoring text not null,
  canonical_name text not null,
  position text not null,
  consensus_rank double precision not null,
  config_version text not null,
  primary key (season, week, scoring, canonical_name, position)
);

-- Tall metric store. position/tier are 'ALL' for overall rows so position-
-- and tier-specific weighting can be added later without a schema change.
create table public.expert_eval_scores (
  season int not null,
  week int not null,
  source text not null,
  scoring text not null,
  config_version text not null,
  position text not null default 'ALL',
  tier text not null default 'ALL',
  metric text not null,
  value double precision,
  n double precision,
  calc_at timestamptz not null default now(),
  primary key (season, week, source, scoring, config_version, position, tier, metric)
);

-- Shadow weights. week = the week these weights would apply to (computed
-- only from weeks before it).
create table public.expert_eval_weights (
  season int not null,
  week int not null,
  scoring text not null,
  weight_set text not null,                   -- 'six' | 'three'
  source text not null,
  position text not null default 'ALL',
  tier text not null default 'ALL',
  config_version text not null,
  weight double precision not null,
  equal_weight double precision not null,
  skill_mean double precision,
  skill_sd double precision,
  p_better double precision,
  weeks_n int,
  raw_mean double precision,
  reason text,
  calc_at timestamptz not null default now(),
  primary key (season, week, scoring, weight_set, source, position, tier, config_version)
);

create table public.expert_eval_backtests (
  run_id text primary key,
  config_version text not null,
  scoring text not null,
  summary jsonb not null,
  weekly jsonb,
  created_at timestamptz not null default now()
);

create table public.expert_eval_runs (
  run_id text primary key,
  started_at timestamptz not null default now(),
  season int,
  week int,
  kind text not null,
  config_version text,
  inputs_hash text,
  notes text
);

alter table public.expert_eval_config enable row level security;
alter table public.expert_eval_results enable row level security;
alter table public.expert_eval_snapshots enable row level security;
alter table public.expert_eval_pool enable row level security;
alter table public.expert_eval_scores enable row level security;
alter table public.expert_eval_weights enable row level security;
alter table public.expert_eval_backtests enable row level security;
alter table public.expert_eval_runs enable row level security;

create policy "expert_eval_config public read" on public.expert_eval_config for select using (true);
create policy "expert_eval_scores public read" on public.expert_eval_scores for select using (true);
create policy "expert_eval_weights public read" on public.expert_eval_weights for select using (true);
create policy "expert_eval_backtests public read" on public.expert_eval_backtests for select using (true);
create policy "expert_eval_runs public read" on public.expert_eval_runs for select using (true);
-- results / snapshots / pool: read via service role only (not needed by the site).
