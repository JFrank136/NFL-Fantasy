-- Headshot lookup for the site: (canonical_name, position) -> ESPN athlete id.
-- Filled by scripts/build_player_images.py (ESPN rosters + data/player_image_overrides.csv).
-- Defenses (position DST) store "team:<espn abbr>" and the site draws the team logo.
-- Applied to the live project 2026-11-12 via the Supabase MCP.
create table public.player_images (
  canonical_name text not null,
  position text not null,
  espn_id text not null,
  updated_at timestamptz not null default now(),
  primary key (canonical_name, position)
);
alter table public.player_images enable row level security;
create policy "player_images public read" on public.player_images for select using (true);
