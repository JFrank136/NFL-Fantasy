-- in-season/supabase/migrations/0001_in_season_foundation.sql
create table if not exists in_season_rankings (
  id bigserial primary key,
  season int not null,
  week int not null,
  source text not null,
  scoring text not null,
  pulled_at timestamptz not null,
  source_player_id text not null,
  player_name text not null,
  canonical_name text not null,
  team text,
  position text not null,
  rank int,
  projection double precision,
  floor_proj double precision,
  ceiling_proj double precision,
  tier int,
  bye int,
  opponent text,
  created_at timestamptz not null default now()
);

create index if not exists in_season_rankings_lookup_idx
  on in_season_rankings (season, week, source, scoring, canonical_name);

create table if not exists in_season_trade_values (
  id bigserial primary key,
  season int not null,
  week int not null,
  source text not null,
  position text not null,
  pulled_at timestamptz not null,
  source_url text not null,
  rank int,
  player_name text not null,
  canonical_name text not null,
  team text,
  value_col1_label text not null,
  value_col1 double precision,
  value_col2_label text not null,
  value_col2 double precision,
  created_at timestamptz not null default now()
);

create index if not exists in_season_trade_values_lookup_idx
  on in_season_trade_values (season, week, source, position, canonical_name);

create table if not exists in_season_pull_status (
  dataset text primary key,
  last_success_at timestamptz,
  last_attempt_at timestamptz not null,
  status text not null,
  message text,
  row_count int
);

create or replace view in_season_rankings_latest as
select distinct on (season, week, source, scoring, canonical_name) *
from in_season_rankings
order by season, week, source, scoring, canonical_name, pulled_at desc;

create or replace view in_season_trade_values_latest as
select distinct on (season, week, source, position, canonical_name) *
from in_season_trade_values
order by season, week, source, position, canonical_name, pulled_at desc;
