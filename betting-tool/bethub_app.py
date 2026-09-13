import sqlite3, os, re, datetime as dt, subprocess, sys
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz

# ========== CONFIG ==========
DB_PATH = Path("bethub.db")
DATA_DIR = Path("data")
EXPORTS_DIR = Path("exports")
DATA_DIR.mkdir(exist_ok=True)
EXPORTS_DIR.mkdir(exist_ok=True)

SOURCES = [
    "CB Mismatch", "CBS Yds", "MattLocks", "NovelCalendar",
    "DoughNation", "Action", "Hit Rate", "Other"
]

# ========== DATABASE ==========
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_conn() as con:
        con.executescript("""
CREATE TABLE IF NOT EXISTS picks(
 id INTEGER PRIMARY KEY,
 week INTEGER,
 game_id TEXT,
 team TEXT,
 player TEXT,
 pick_text TEXT NOT NULL,
 source TEXT,
 like INTEGER DEFAULT 0,
 love INTEGER DEFAULT 0,
 notes TEXT,
 created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule(
 game_id TEXT PRIMARY KEY,
 week INTEGER,
 home TEXT,
 away TEXT,
 kickoff_utc TEXT
);

CREATE TABLE IF NOT EXISTS roster(
 id INTEGER PRIMARY KEY,
 player TEXT,
 team TEXT,
 position TEXT,
 depth INTEGER,
 week_loaded INTEGER
);

CREATE TABLE IF NOT EXISTS bets(
 bet_id INTEGER PRIMARY KEY,
 name TEXT,
 bet_type TEXT DEFAULT 'parlay',
 stake REAL,
 payout_total REAL,
 status TEXT DEFAULT 'open',
 include_in_estimate INTEGER DEFAULT 1,
 created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legs(
 leg_id INTEGER PRIMARY KEY,
 bet_id INTEGER REFERENCES bets(bet_id) ON DELETE CASCADE,
 leg_type TEXT DEFAULT 'yards',
 week INTEGER,
 game_id TEXT,
 team TEXT,
 player TEXT,
 pick_text TEXT,
 target_value REAL,
 current_value REAL DEFAULT 0,
 status TEXT DEFAULT 'open',
 created_at TEXT DEFAULT (datetime('now'))
);
""")
        
        # Migration: Add bet_type column if it doesn't exist
        try:
            con.execute("SELECT bet_type FROM bets LIMIT 1")
        except:
            con.execute("ALTER TABLE bets ADD COLUMN bet_type TEXT DEFAULT 'parlay'")
            con.commit()
        
        # Migration: Add leg_type column if it doesn't exist
        try:
            con.execute("SELECT leg_type FROM legs LIMIT 1")
        except:
            con.execute("ALTER TABLE legs ADD COLUMN leg_type TEXT DEFAULT 'yards'")
            con.commit()
        
        # Migration: Add depth column to roster if it doesn't exist
        try:
            con.execute("SELECT depth FROM roster LIMIT 1")
        except:
            con.execute("ALTER TABLE roster ADD COLUMN depth INTEGER")
            con.commit()

def df(query, params=()):
    with get_conn() as con:
        return pd.read_sql_query(query, con, params=params)

def run(sql, params=()):
    with get_conn() as con:
        con.execute(sql, params)
        con.commit()

init_db()

# ========== HELPERS ==========
def parse_player_from_text(text: str, roster_names: pd.Series) -> Tuple[Optional[str], Optional[str]]:
    text_clean = " " + re.sub(r"[^A-Za-z .'-]", " ", text) + " "
    best = None
    for name in roster_names.sort_values(key=lambda s: s.str.len(), ascending=False):
        pat = f" {re.escape(name)} "
        if re.search(pat, text_clean, flags=re.I):
            best = name
            break
    if best is None:
        return None, None
    team = df("SELECT team FROM roster WHERE lower(player)=lower(?) LIMIT 1", (best,))
    team = team["team"].squeeze() if not team.empty else None
    if pd.isna(team):
        team = None
    return best, team

def get_roster_df() -> pd.DataFrame:
    try:
        return df("SELECT DISTINCT player, team FROM roster")
    except Exception:
        return pd.DataFrame(columns=["player","team"])

def match_player_fuzzy(text: str, roster_players: pd.Series) -> Optional[str]:
    if roster_players.empty:
        return None
    text_pad = " " + re.sub(r"[^A-Za-z .'-]", " ", text) + " "
    for name in roster_players.sort_values(key=lambda s: s.str.len(), ascending=False):
        pat = f" {re.escape(name)} "
        if re.search(pat, text_pad, flags=re.I):
            return name
    cand, score, _ = process.extractOne(
        text, roster_players.tolist(),
        scorer=fuzz.WRatio, score_cutoff=86
    ) or (None, 0, None)
    return cand

def parse_bulk_picks(raw_text: str, source: str, week: int) -> pd.DataFrame:
    roster = get_roster_df()
    roster_players = roster["player"] if not roster.empty else pd.Series(dtype=str)
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    rows = []
    for ln in lines:
        if re.search(r"(NFL|Cody|Algorithm|Team|Rank|Defense|Score|Odds|Kickoff|Week\s+\d+)", ln, re.I):
            continue
        player = match_player_fuzzy(ln, roster_players) if not roster_players.empty else None
        team = None
        if player:
            team = roster.loc[roster["player"].str.lower()==player.lower(), "team"].head(1).squeeze()
            team = None if pd.isna(team) else str(team)
        rows.append({
            "pick_text": ln, "player": player or "", "team": team or "",
            "source": source, "week": int(week), "like": False, "love": False, "notes": ""
        })
    return pd.DataFrame(rows)

def load_roster_csv(path: Path, week: int):
    ros = pd.read_csv(path)
    ros["week_loaded"] = week
    with get_conn() as con:
        ros.to_sql("roster", con, if_exists="append", index=False)
    st.success(f"✓ Loaded {len(ros)} roster entries")

def load_schedule_csv(path: Path):
    sch = pd.read_csv(path)
    with get_conn() as con:
        sch.to_sql("schedule", con, if_exists="append", index=False)
    st.success(f"✓ Loaded {len(sch)} schedule entries")

def export_csv(query: str, filename: str):
    data = df(query)
    out = EXPORTS_DIR / filename
    data.to_csv(out, index=False)
    st.success(f"✓ Exported to {out}")

def estimate_payout() -> float:
    rows = df("SELECT payout_total FROM bets WHERE status='open' AND include_in_estimate=1")
    return float(rows["payout_total"].sum()) if not rows.empty else 0.0

def auto_update_bet_status(bet_id: int):
    """Auto-settle single bets when their only leg is won/lost"""
    bet_info = df("SELECT bet_type FROM bets WHERE bet_id=?", (bet_id,))
    if bet_info.empty:
        return
    
    bet_type = bet_info["bet_type"].iloc[0]
    if bet_type != "single":
        return
    
    legs = df("SELECT status FROM legs WHERE bet_id=?", (bet_id,))
    if len(legs) == 1:
        leg_status = legs["status"].iloc[0]
        if leg_status in ["won", "lost", "push"]:
            run("UPDATE bets SET status='settled' WHERE bet_id=?", (bet_id,))

# ========== STREAMLIT CONFIG ==========
st.set_page_config(page_title="BetHub", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for cleaner look
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {gap: 24px;}
    .stTabs [data-baseweb="tab"] {padding: 12px 24px; font-size: 16px;}
    div[data-testid="metric-container"] {background-color: #f0f2f6; padding: 15px; border-radius: 8px;}
</style>
""", unsafe_allow_html=True)

# ========== SIDEBAR ==========
with st.sidebar:
    st.title("⚙️ BetHub Controls")
    
    current_week = st.number_input("📅 Current Week", min_value=1, max_value=22, value=1, key="current_week")
    
    st.divider()
    
    with st.expander("📊 Data Management", expanded=False):
        st.markdown("**Roster**")
        if st.button("🔄 Run Depth Chart Scraper", use_container_width=True):
            with st.spinner("Scraping..."):
                try:
                    subprocess.check_call([sys.executable, "depth_chart.py"])
                    st.success("✓ Scrape complete")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        roster_file = st.file_uploader("Upload Roster CSV", type=["csv"], key="roster_up")
        if roster_file:
            tmp = DATA_DIR / "uploaded_roster.csv"
            tmp.write_bytes(roster_file.read())
            load_roster_csv(tmp, current_week)
        
        st.markdown("**Schedule**")
        if st.button("🔄 Run Schedule Scraper", use_container_width=True):
            with st.spinner("Scraping..."):
                try:
                    subprocess.check_call([sys.executable, "schedule.py"])
                    st.success("✓ Scrape complete")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        sched_file = st.file_uploader("Upload Schedule CSV", type=["csv"], key="sched_up")
        if sched_file:
            tmp = DATA_DIR / "uploaded_schedule.csv"
            tmp.write_bytes(sched_file.read())
            load_schedule_csv(tmp)
    
    with st.expander("💾 Exports", expanded=False):
        if st.button("📥 Export Picks", use_container_width=True):
            export_csv("SELECT * FROM picks ORDER BY created_at DESC", f"picks_{dt.date.today()}.csv")
        if st.button("📥 Export Bets & Legs", use_container_width=True):
            export_csv("SELECT * FROM bets", f"bets_{dt.date.today()}.csv")
            export_csv("SELECT * FROM legs", f"legs_{dt.date.today()}.csv")

# ========== MAIN UI ==========
st.title("🎯 BetHub")

tab1, tab2, tab3, tab4 = st.tabs(["💰 Bet Tracker", "📝 Picks Inbox", "⭐ Likes & Loves", "🏈 Games"])

# ========== BET TRACKER (PRIORITY TAB) ==========
with tab1:
    st.header("Bet Tracker")
    
    # Estimated Payout at top
    col1, col2 = st.columns([1, 2])
    with col1:
        est_payout = estimate_payout()
        st.metric("💵 Estimated Payout", f"${est_payout:,.2f}")
    
    st.divider()
    
    # Add Bet Section
    with st.expander("➕ Add New Bet", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            bet_name = st.text_input("Bet Name", placeholder="e.g., Sunday 3-leg parlay")
            bet_type = st.selectbox("Bet Type", ["parlay", "single"])
            stake = st.number_input("Stake ($)", min_value=0.0, step=5.0, value=10.0)
        with col2:
            payout = st.number_input("Total Payout ($)", min_value=0.0, step=10.0, value=50.0)
            include = st.checkbox("Include in Estimate", value=True)
        
        if st.button("💾 Save Bet", type="primary", disabled=not bet_name):
            run("""INSERT INTO bets(name, bet_type, stake, payout_total, include_in_estimate) 
                   VALUES(?,?,?,?,?)""",
                (bet_name.strip(), bet_type, float(stake), float(payout), int(include)))
            st.success("✓ Bet saved!")
            st.rerun()
    
    st.divider()
    
    # Display Bets
    bets_df = df("SELECT * FROM bets ORDER BY status ASC, created_at DESC")
    
    if bets_df.empty:
        st.info("No bets yet. Add one above to get started!")
    else:
        # Filter controls
        col1, col2 = st.columns([3, 1])
        with col1:
            show_settled = st.checkbox("Show Settled Bets", value=False)
        
        if not show_settled:
            bets_df = bets_df[bets_df["status"] == "open"]
        
        # Display each bet as a card
        for idx, bet in bets_df.iterrows():
            bet_id = int(bet["bet_id"])
            
            with st.container():
                st.markdown(f"### {bet['name']}")
                
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                col1.write(f"**Type:** {bet['bet_type'].title()}")
                col2.metric("Stake", f"${bet['stake']:.0f}")
                col3.metric("Payout", f"${bet['payout_total']:.0f}")
                col4.write(f"**Status:** {bet['status'].title()}")
                
                # Controls
                with col5:
                    if st.button("⚙️", key=f"toggle_{bet_id}"):
                        st.session_state[f"show_controls_{bet_id}"] = not st.session_state.get(f"show_controls_{bet_id}", False)
                
                # Show controls if toggled
                if st.session_state.get(f"show_controls_{bet_id}", False):
                    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)
                    new_status = ctrl_col1.selectbox(
                        "Status", ["open", "settled"],
                        index=0 if bet["status"]=="open" else 1,
                        key=f"status_{bet_id}"
                    )
                    new_include = ctrl_col2.checkbox(
                        "Include in Estimate",
                        value=bool(bet["include_in_estimate"]),
                        key=f"inc_{bet_id}"
                    )
                    if ctrl_col3.button("Update", key=f"upd_{bet_id}"):
                        run("UPDATE bets SET status=?, include_in_estimate=? WHERE bet_id=?",
                            (new_status, int(new_include), bet_id))
                        st.success("✓ Updated")
                        st.rerun()
                
                st.divider()
                
                # Legs Section
                st.markdown("**Legs:**")
                
                # Add Leg
                with st.expander("➕ Add Leg", expanded=False):
                    leg_type = st.selectbox("Leg Type", ["yards", "attd", "spread"], key=f"legtype_{bet_id}")
                    
                    pick_text = st.text_input(
                        "Pick Description",
                        placeholder="e.g., Travis Kelce 50+ ReYds",
                        key=f"picktext_{bet_id}"
                    )
                    
                    # Auto-detect player/team
                    roster_df = get_roster_df()
                    roster_names = roster_df["player"] if not roster_df.empty else pd.Series(dtype=str)
                    player_auto, team_auto = (None, None)
                    if pick_text and not roster_names.empty:
                        player_auto, team_auto = parse_player_from_text(pick_text, roster_names)
                    
                    lcol1, lcol2, lcol3 = st.columns(3)
                    leg_player = lcol1.text_input("Player", value=player_auto or "", key=f"legplayer_{bet_id}")
                    leg_team = lcol2.text_input("Team", value=team_auto or "", key=f"legteam_{bet_id}")
                    
                    if leg_type == "yards":
                        leg_target = lcol3.number_input("Target", min_value=0.0, step=1.0, key=f"legtarget_{bet_id}")
                    else:
                        leg_target = 0.0
                    
                    if st.button("💾 Add Leg", key=f"addleg_{bet_id}", disabled=not pick_text):
                        run("""INSERT INTO legs(bet_id, leg_type, week, team, player, pick_text, target_value) 
                               VALUES(?,?,?,?,?,?,?)""",
                            (bet_id, leg_type, current_week, leg_team or None, leg_player or None,
                             pick_text.strip(), float(leg_target)))
                        st.success("✓ Leg added")
                        st.rerun()
                
                # Display Legs
                legs_df = df("SELECT * FROM legs WHERE bet_id=? ORDER BY status ASC, created_at", (bet_id,))
                
                if legs_df.empty:
                    st.info("No legs yet")
                else:
                    for _, leg in legs_df.iterrows():
                        leg_id = int(leg["leg_id"])
                        leg_type = leg["leg_type"]
                        
                        # Color coding
                        if leg["status"] == "won":
                            bg_color = "#d1fadf"
                        elif leg["status"] == "lost":
                            bg_color = "#fee"
                        elif leg["status"] == "push":
                            bg_color = "#fff3cd"
                        else:
                            bg_color = "#f8f9fa"
                        
                        st.markdown(f"""
                        <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; margin: 10px 0;">
                            <strong>{leg['pick_text']}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        if leg_type == "yards":
                            lcol1, lcol2, lcol3, lcol4, lcol5 = st.columns([2, 1, 1, 1, 1])
                            
                            current = lcol1.number_input(
                                "Current",
                                value=float(leg["current_value"]),
                                step=1.0,
                                key=f"cur_{leg_id}"
                            )
                            
                            target = float(leg["target_value"])
                            needed = max(target - current, 0)
                            
                            lcol2.metric("Target", f"{target:.0f}")
                            lcol3.metric("Needed", f"{needed:.0f}")
                            
                            # Auto-update status based on current value
                            if current >= target and leg["status"] == "open":
                                new_status = "won"
                            else:
                                new_status = leg["status"]
                            
                            new_status = lcol4.selectbox(
                                "Status",
                                ["open", "won", "lost", "push"],
                                index=["open", "won", "lost", "push"].index(new_status),
                                key=f"legstatus_{leg_id}"
                            )
                            
                            if lcol5.button("💾", key=f"savleg_{leg_id}"):
                                run("UPDATE legs SET current_value=?, status=? WHERE leg_id=?",
                                    (float(current), new_status, leg_id))
                                auto_update_bet_status(bet_id)
                                st.success("✓ Saved")
                                st.rerun()
                        
                        else:  # ATTD or Spread
                            lcol1, lcol2 = st.columns([3, 1])
                            
                            new_status = lcol1.selectbox(
                                "Status",
                                ["open", "won", "lost"],
                                index=["open", "won", "lost"].index(leg["status"]),
                                key=f"legstatus_{leg_id}"
                            )
                            
                            if lcol2.button("💾", key=f"savleg_{leg_id}"):
                                run("UPDATE legs SET status=? WHERE leg_id=?", (new_status, leg_id))
                                auto_update_bet_status(bet_id)
                                st.success("✓ Saved")
                                st.rerun()
                
                st.markdown("---")

# ========== PICKS INBOX ==========
with tab2:
    st.header("Picks Inbox")
    
    tab_single, tab_bulk, tab_view = st.tabs(["Add Single Pick", "Bulk Add", "View Picks"])
    
    with tab_single:
        st.subheader("Add Single Pick")
        
        col1, col2 = st.columns(2)
        with col1:
            pick_text = st.text_input("Pick Text", placeholder="e.g., Jaylen Warren 30+ RuYds")
            source = st.selectbox("Source", SOURCES)
            week = st.number_input("Week", min_value=1, max_value=22, value=current_week)
        
        with col2:
            roster_df = get_roster_df()
            roster_names = roster_df["player"] if not roster_df.empty else pd.Series(dtype=str)
            player_auto, team_auto = (None, None)
            if pick_text and not roster_names.empty:
                player_auto, team_auto = parse_player_from_text(pick_text, roster_names)
            
            player = st.text_input("Player", value=player_auto or "")
            team = st.text_input("Team", value=team_auto or "")
        
        col1, col2, col3 = st.columns(3)
        like = col1.checkbox("❤️ Like")
        love = col2.checkbox("💖 Love")
        notes = st.text_area("Notes (optional)")
        
        if st.button("💾 Save Pick", type="primary", disabled=not pick_text):
            run("""INSERT INTO picks(week, team, player, pick_text, source, like, love, notes)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (int(week), team or None, player or None, pick_text.strip(),
                 source, int(like), int(love), notes.strip() or None))
            st.success("✓ Pick saved!")
    
    with tab_bulk:
        st.subheader("Bulk Add Picks")
        
        col1, col2 = st.columns(2)
        with col1:
            bulk_source = st.selectbox("Source (for all)", SOURCES, key="bulk_src")
            bulk_week = st.number_input("Week (for all)", min_value=1, max_value=22, value=current_week, key="bulk_wk")
        
        bulk_text = st.text_area(
            "Paste picks (one per line)",
            height=200,
            placeholder="Travis Kelce 50+ rec yards\nJaylen Warren 30+ rush yards\n..."
        )
        
        if st.button("🔍 Parse Picks", type="primary"):
            if not bulk_text.strip():
                st.warning("Paste some text first")
            else:
                parsed = parse_bulk_picks(bulk_text, bulk_source, bulk_week)
                if parsed.empty:
                    st.info("No picks found")
                else:
                    st.session_state["bulk_parsed"] = parsed
                    st.success(f"✓ Parsed {len(parsed)} picks")
        
        if "bulk_parsed" in st.session_state and not st.session_state["bulk_parsed"].empty:
            st.markdown("**Review and edit before saving:**")
            
            edited = st.data_editor(
                st.session_state["bulk_parsed"],
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "like": st.column_config.CheckboxColumn("❤️"),
                    "love": st.column_config.CheckboxColumn("💖"),
                }
            )
            
            col1, col2 = st.columns(2)
            if col1.button("🔄 Auto-fill Teams"):
                roster = get_roster_df()
                if roster.empty:
                    st.warning("No roster loaded")
                else:
                    team_map = roster.set_index(roster["player"].str.lower())["team"].to_dict()
                    edited["team"] = [
                        team_map.get(str(edited.loc[i,"player"]).lower(), edited.loc[i,"team"])
                        for i in edited.index
                    ]
                    st.session_state["bulk_parsed"] = edited
                    st.rerun()
            
            if col2.button("💾 Save All Picks", type="primary"):
                saved = 0
                for _, r in edited.iterrows():
                    if not str(r.get("pick_text","")).strip():
                        continue
                    run("""INSERT INTO picks(week, team, player, pick_text, source, like, love, notes)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (int(r["week"]), r.get("team") or None, r.get("player") or None,
                         str(r["pick_text"]).strip(), str(r["source"]),
                         int(r.get("like", False)), int(r.get("love", False)),
                         str(r.get("notes","")).strip() or None))
                    saved += 1
                st.session_state["bulk_parsed"] = None
                st.success(f"✓ Saved {saved} picks")
                st.rerun()
    
    with tab_view:
        st.subheader("View Picks")
        
        col1, col2, col3 = st.columns(3)
        view_week = col1.number_input("Week", min_value=1, max_value=22, value=current_week, key="view_wk")
        view_sources = col2.multiselect("Sources", SOURCES, default=SOURCES)
        
        show_likes = col3.checkbox("❤️ Likes Only")
        show_loves = col3.checkbox("💖 Loves Only")
        
        picks_df = df("SELECT * FROM picks WHERE week=?", (int(view_week),))
        
        if show_likes:
            picks_df = picks_df[picks_df["like"] == 1]
        if show_loves:
            picks_df = picks_df[picks_df["love"] == 1]
        if view_sources:
            picks_df = picks_df[picks_df["source"].isin(view_sources)]
        
        if picks_df.empty:
            st.info("No picks found")
        else:
            # Only show columns that exist
            display_cols = []
            for col in ["player", "team", "pick_text", "source", "notes"]:
                if col in picks_df.columns:
                    display_cols.append(col)
            
            st.dataframe(
                picks_df[display_cols].sort_values("source") if "source" in display_cols else picks_df[display_cols],
                use_container_width=True
            )

# ========== LIKES & LOVES ==========
with tab3:
    st.header("Likes & Loves")
    
    ll_week = st.number_input("Week", min_value=1, max_value=22, value=current_week, key="ll_wk")
    
    picks_df = df("SELECT * FROM picks WHERE week=?", (int(ll_week),))
    
    col1, col2 = st.columns(2)
    
    # Determine which columns exist
    display_cols = []
    for col in ["player", "team", "pick_text", "source"]:
        if col in picks_df.columns:
            display_cols.append(col)
    
    with col1:
        st.subheader("❤️ Likes")
        likes = picks_df[picks_df["like"] == 1] if not picks_df.empty else picks_df
        if likes.empty:
            st.info("No likes yet")
        else:
            st.dataframe(
                likes[display_cols],
                use_container_width=True,
                hide_index=True
            )
    
    with col2:
        st.subheader("💖 Loves")
        loves = picks_df[picks_df["love"] == 1] if not picks_df.empty else picks_df
        if loves.empty:
            st.info("No loves yet")
        else:
            st.dataframe(
                loves[display_cols],
                use_container_width=True,
                hide_index=True
            )

# ========== GAMES ==========
with tab4:
    st.header("Game Browser")
    
    game_week = st.number_input("Week", min_value=1, max_value=22, value=current_week, key="game_wk")
    
    games_df = df("SELECT * FROM schedule WHERE week=? ORDER BY kickoff_utc", (int(game_week),))
    
    if games_df.empty:
        st.info("No schedule loaded. Upload schedule CSV in sidebar.")
    else:
        game_labels = [f"{r['home']} vs {r['away']}" for _, r in games_df.iterrows()]
        selected_game = st.selectbox("Select Game", game_labels)
        
        game_row = games_df.iloc[game_labels.index(selected_game)]
        
        st.markdown(f"### {game_row['home']} vs {game_row['away']}")
        st.caption(f"Kickoff: {game_row['kickoff_utc']}")
        
        st.divider()
        
        picks_df = df("""
            SELECT * FROM picks 
            WHERE week=? AND (team=? OR team=?)
            ORDER BY source, player
        """, (int(game_week), game_row['home'], game_row['away']))
        
        if picks_df.empty:
            st.info("No picks for this game yet")
        else:
            # Only show columns that exist
            display_cols = []
            for col in ["player", "team", "pick_text", "source", "notes"]:
                if col in picks_df.columns:
                    display_cols.append(col)
            
            st.dataframe(
                picks_df[display_cols],
                use_container_width=True
            )