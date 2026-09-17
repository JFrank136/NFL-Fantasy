-- in-season/supabase/migrations/0002_ros_rankings.sql
create table if not exists in_season_ros_rankings (
  id bigserial primary key,
  season int not null,
  source text not null,
  scoring text not null,
  pulled_at timestamptz not null,
  as_of_week int not null,
  source_player_id text not null,
  player_name text not null,
  canonical_name text not null,
  team text,
  position text not null,
  rank int,
  tier_overall int,
  tier_positional int,
  projection double precision,
  floor_proj double precision,
  ceiling_proj double precision,
  ds_value double precision,
  strength_of_schedule text,
  games_played int,
  injury_risk text,
  bye int,
  created_at timestamptz not null default now()
);

create index if not exists in_season_ros_rankings_lookup_idx
  on in_season_ros_rankings (season, source, scoring, canonical_name);

create or replace view in_season_ros_rankings_latest as
select distinct on (season, source, scoring, canonical_name) *
from in_season_ros_rankings
order by season, source, scoring, canonical_name, pulled_at desc;
