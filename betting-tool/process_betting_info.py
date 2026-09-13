import pandas as pd
import re
from difflib import get_close_matches

# ============================================================
# WEIGHTING CONFIGURATION - CHANGE HERE FOR DIFFERENT WEEKS
# ============================================================
# Recommendation for Week 15: 65% Last 5 weeks / 35% Full Season
# - Last 5 weeks captures recent trends, injuries, scheme changes
# - Full season provides stability and larger sample size
# 
# Adjust based on week:
# - Early season (Weeks 1-6): Use 40/60 or 30/70 (favor full season data)
# - Mid season (Weeks 7-12): Use 50/50 or 55/45
# - Late season (Weeks 13+): Use 65/35 or 70/30 (favor recent trends)
LAST5_WEIGHT = 0.65  # Weight for recent 5-week data
CBS_WEIGHT = 0.35    # Weight for full season data

# Verify weights sum to 1.0
assert abs((LAST5_WEIGHT + CBS_WEIGHT) - 1.0) < 0.01, "Weights must sum to 1.0"
# ============================================================

# Team abbreviation to full name mapping
TEAM_NAMES = {
    'ARI': 'Cardinals', 'ATL': 'Falcons', 'BAL': 'Ravens', 'BUF': 'Bills',
    'CAR': 'Panthers', 'CHI': 'Bears', 'CIN': 'Bengals', 'CLE': 'Browns',
    'DAL': 'Cowboys', 'DEN': 'Broncos', 'DET': 'Lions', 'GB': 'Packers',
    'HOU': 'Texans', 'IND': 'Colts', 'JAX': 'Jaguars', 'KC': 'Chiefs',
    'LAC': 'Chargers', 'LAR': 'Rams', 'LV': 'Raiders', 'MIA': 'Dolphins',
    'MIN': 'Vikings', 'NE': 'Patriots', 'NO': 'Saints', 'NYG': 'Giants',
    'NYJ': 'Jets', 'PHI': 'Eagles', 'PIT': 'Steelers', 'SEA': 'Seahawks',
    'SF': '49ers', 'TB': 'Buccaneers', 'TEN': 'Titans', 'WSH': 'Commanders'
}

# Read the files
betting_info = pd.read_csv('data/betting_info.csv')
cbs_stats = pd.read_csv('data/cbs_yards.csv')  # Now has headers: Stat_Category, Team, Value, Source
last5_stats = pd.read_csv('data/last5_yds.csv')  # Has headers: Stat_Category, Team, Value, Source
roster = pd.read_csv('data/roster_latest.csv')

# Filter betting_info to only the latest week
latest_week = betting_info['Week'].max()
betting_info = betting_info[betting_info['Week'] == latest_week]

print("="*60)
print(f"PROCESSING WEEK {latest_week} BETTING INFO")
print("="*60)
print(f"Weighting: Last 5 weeks ({LAST5_WEIGHT*100:.0f}%) + Full Season CBS ({CBS_WEIGHT*100:.0f}%)")
print(f"Processing {len(betting_info)} picks from betting_info.csv")
print()

# Create a dictionary for quick player name lookup
def normalize_name(name):
    """Remove Jr., Sr., III, IV, etc. from names for matching"""
    name = str(name).strip()
    name = re.sub(r'\s+(Jr\.?|Sr\.?|III|IV|V)$', '', name, flags=re.IGNORECASE)
    return name.strip()

# Create normalized roster lookup
roster['normalized_player'] = roster['player'].apply(normalize_name)
player_to_team = dict(zip(roster['normalized_player'].str.lower(), roster['team']))
all_players = list(player_to_team.keys())
original_names = dict(zip(roster['normalized_player'].str.lower(), roster['player']))

def extract_player_name(bet_string):
    """Extract player name from various bet formats"""
    bet_string = re.sub(r'^[ou]\s+', '', bet_string, flags=re.IGNORECASE)
    
    match = re.match(r'^([A-Za-z\'\.\s-]+?)\s+[ou]?[\d\.]+\+?\s+', bet_string, flags=re.IGNORECASE)
    if match:
        return normalize_name(match.group(1))
    
    match = re.match(r'^(.+)\s+[ou](?=[A-Z])', bet_string, flags=re.IGNORECASE)
    if match:
        potential_name = match.group(1).strip()
        if re.match(r'^[A-Za-z\'\.\s-]+$', potential_name):
            return normalize_name(potential_name)
    
    words = bet_string.split()
    if len(words) >= 2:
        first_two = ' '.join(words[:2])
        if re.match(r'^[A-Za-z\'\.\s-]+$', first_two):
            return normalize_name(first_two)
    
    return normalize_name(bet_string)

def find_team_fuzzy(player_name, exact_match_dict, all_players_list, threshold=0.85):
    player_name_lower = player_name.lower()
    
    if player_name_lower in exact_match_dict:
        return exact_match_dict[player_name_lower], player_name
    
    matches = get_close_matches(player_name_lower, all_players_list, n=1, cutoff=threshold)
    if matches:
        matched_name = matches[0]
        return exact_match_dict[matched_name], matched_name
    
    return None, None

def combine_weighted_rankings():
    """
    Combine CBS and Last5 stats using weighted rankings.
    Both files have format: Stat_Category, Team, Value, Source
    """
    print("Combining CBS and Last5 rankings with weighted method...")
    
    cbs_df = cbs_stats.copy()
    last5_df = last5_stats.copy()
    
    # Parse stat categories
    cbs_df['position'] = cbs_df['Stat_Category'].str.extract(r'^(QB|RB|WR|TE)\s+', expand=False)
    cbs_df['stat_name'] = cbs_df['Stat_Category'].str.replace(r'^(QB|RB|WR|TE)\s+', '', regex=True)
    
    last5_df['position'] = last5_df['Stat_Category'].str.extract(r'^(QB|RB|WR|TE)\s+', expand=False)
    last5_df['stat_name'] = last5_df['Stat_Category'].str.replace(r'^(QB|RB|WR|TE)\s+', '', regex=True)
    
    # Remove rows where parsing failed
    cbs_df = cbs_df[cbs_df['position'].notna()].copy()
    last5_df = last5_df[last5_df['position'].notna()].copy()
    
    if cbs_df.empty or last5_df.empty:
        print("  [ERROR] Failed to parse stats!")
        return pd.DataFrame(columns=['Bet', 'Team', 'Source', 'Week'])
    
    print(f"  Parsed {len(cbs_df)} CBS stats, {len(last5_df)} Last5 stats")
    
    # Rank teams within each position/stat (higher value = better = rank 1)
    cbs_df['rank'] = cbs_df.groupby(['position', 'stat_name'])['Value'].rank(method='min', ascending=False)
    last5_df['rank'] = last5_df.groupby(['position', 'stat_name'])['Value'].rank(method='min', ascending=False)
    
    # Get unique combinations
    all_combos = set()
    for _, row in cbs_df.iterrows():
        all_combos.add((row['position'], row['stat_name']))
    for _, row in last5_df.iterrows():
        all_combos.add((row['position'], row['stat_name']))
    
    print(f"  Processing {len(all_combos)} stat categories...")
    
    weighted_results = []
    
    for pos, stat in sorted(all_combos):
        cbs_subset = cbs_df[(cbs_df['position'] == pos) & (cbs_df['stat_name'] == stat)]
        last5_subset = last5_df[(last5_df['position'] == pos) & (last5_df['stat_name'] == stat)]
        
        all_teams = set(cbs_subset['Team'].unique()) | set(last5_subset['Team'].unique())
        
        team_scores = []
        
        for team in all_teams:
            cbs_rank = None
            last5_rank = None
            
            cbs_team = cbs_subset[cbs_subset['Team'] == team]
            if not cbs_team.empty:
                cbs_rank = cbs_team.iloc[0]['rank']
            
            last5_team = last5_subset[last5_subset['Team'] == team]
            if not last5_team.empty:
                last5_rank = last5_team.iloc[0]['rank']
            
            # Calculate weighted rank
            if cbs_rank is not None and last5_rank is not None:
                weighted_rank = (CBS_WEIGHT * cbs_rank) + (LAST5_WEIGHT * last5_rank)
            elif cbs_rank is not None:
                weighted_rank = cbs_rank
            elif last5_rank is not None:
                weighted_rank = last5_rank
            else:
                continue
            
            team_scores.append({
                'team': team,
                'weighted_rank': weighted_rank
            })
        
        # Sort by weighted rank
        team_scores.sort(key=lambda x: x['weighted_rank'])
        
        # Take top 5 and bottom 5
        if len(team_scores) >= 5:
            for i, score in enumerate(team_scores[:5], 1):
                label_prefix = ['MOST', '2nd MOST', '3rd MOST', '4th MOST', '5th MOST'][i-1]
                weighted_results.append({
                    'Bet': f"{label_prefix} {pos} {stat}",
                    'Team': score['team'],
                    'Source': f"CBS + Last 5 ({int(CBS_WEIGHT*100)}/{int(LAST5_WEIGHT*100)})"
                })
            
            bottom_5 = team_scores[-5:][::-1]
            for i, score in enumerate(bottom_5, 1):
                label_prefix = ['LEAST', '2nd LEAST', '3rd LEAST', '4th LEAST', '5th LEAST'][i-1]
                weighted_results.append({
                    'Bet': f"{label_prefix} {pos} {stat}",
                    'Team': score['team'],
                    'Source': f"CBS + Last 5 ({int(CBS_WEIGHT*100)}/{int(LAST5_WEIGHT*100)})"
                })
    
    weighted_df = pd.DataFrame(weighted_results)
    print(f"  [OK] Created {len(weighted_df)} weighted rankings\n")
    
    return weighted_df

# Process betting_info
betting_info_processed = betting_info.copy()
betting_info_processed['Team'] = None
betting_info_processed['Player'] = ''

missing_players = []

for idx, row in betting_info_processed.iterrows():
    player_name = extract_player_name(row['Bet'])
    team, matched_name = find_team_fuzzy(player_name, player_to_team, all_players)
    
    if team:
        team_full_name = TEAM_NAMES.get(team, team)
        betting_info_processed.at[idx, 'Team'] = team_full_name
        original_name = original_names.get(matched_name, matched_name)
        betting_info_processed.at[idx, 'Player'] = original_name
    else:
        missing_players.append(player_name)

# Combine CBS and Last5
weighted_stats = combine_weighted_rankings()
weighted_stats['Week'] = latest_week

# Prepare output
betting_info_processed = betting_info_processed[['Bet', 'Team', 'Source', 'Week']]
weighted_stats = weighted_stats[['Bet', 'Team', 'Source', 'Week']]

# Combine
combined_df = pd.concat([betting_info_processed, weighted_stats], ignore_index=True)
combined_df = combined_df.sort_values('Team', ascending=True).reset_index(drop=True)

# Save
output_path = 'exports/betting_info.csv'
combined_df.to_csv(output_path, index=False)

# Summary
print("="*60)
print("SUMMARY")
print("="*60)

if missing_players:
    print(f"[WARNING] Players not found ({len(set(missing_players))}):")
    for player in sorted(set(missing_players))[:5]:
        print(f"  - {player}")
    if len(set(missing_players)) > 5:
        print(f"  ... and {len(set(missing_players)) - 5} more")
else:
    print(f"[OK] Matched all {len(betting_info_processed)} players")

print(f"\n[OK] Total picks: {len(combined_df)}")
print(f"  - {len(betting_info_processed)} betting picks (Week {latest_week})")
print(f"  - {len(weighted_stats)} weighted rankings")
print(f"\n[OK] Saved to: {output_path}")
print("="*60)