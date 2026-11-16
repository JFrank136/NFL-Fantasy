-- Availability detail for evaluation (methodology v1.1): why a player did not score.
-- Additive columns on the new expert_eval_results table, and the frozen pool is now
-- versioned by config_version so a methodology change keeps the old pool intact.
alter table public.expert_eval_results add column if not exists status text;
alter table public.expert_eval_results add column if not exists roster_status text;
alter table public.expert_eval_results add column if not exists report_status text;
alter table public.expert_eval_pool drop constraint expert_eval_pool_pkey;
alter table public.expert_eval_pool add primary key (season, week, scoring, canonical_name, position, config_version);
