import sqlite3
import pandas as pd

DB_PATH = "votes.db"

def export_to_excel(output_file="votes_export.xlsx"):
    conn = sqlite3.connect(DB_PATH)

    # Read lookup table for players
    players_df = pd.read_sql_query("SELECT id, name FROM players", conn)
    # Make sure ids are ints
    players_df["id"] = players_df["id"].astype(int)
    player_map = dict(zip(players_df["id"], players_df["name"]))

    # Read everything else
    voters_df = pd.read_sql_query("SELECT * FROM voters", conn)
    matches_df = pd.read_sql_query("SELECT * FROM matches", conn)

    # Read votes with match + voter names joined
    raw_votes_df = pd.read_sql_query("""
        SELECT 
            votes.id,
            matches.name AS match_name,
            voters.name AS voter_name,
            votes.player_3,
            votes.player_2,
            votes.player_1
        FROM votes
        JOIN matches ON matches.id = votes.match_id
        JOIN voters ON voters.id = votes.voter_id
    """, conn)

    conn.close()

    if raw_votes_df.empty:
        print("No votes found in database.")
    else:
        # Ensure the player_* columns are ints (not floats)
        for col in ["player_3", "player_2", "player_1"]:
            raw_votes_df[col] = raw_votes_df[col].astype(int)

    # Replace numeric IDs with player names
    raw_votes_df["3_votes_for"] = raw_votes_df["player_3"].map(player_map)
    raw_votes_df["2_votes_for"] = raw_votes_df["player_2"].map(player_map)
    raw_votes_df["1_vote_for"] = raw_votes_df["player_1"].map(player_map)

    # Keep a clean votes table with names only
    votes_df = raw_votes_df[[
        "id",
        "match_name",
        "voter_name",
        "3_votes_for",
        "2_votes_for",
        "1_vote_for"
    ]]

    # Write to Excel with multiple sheets
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        players_df.to_excel(writer, sheet_name="Players", index=False)
        voters_df.to_excel(writer, sheet_name="Voters", index=False)
        matches_df.to_excel(writer, sheet_name="Matches", index=False)
        votes_df.to_excel(writer, sheet_name="Votes", index=False)

    print(f"Export completed: {output_file}")


if __name__ == "__main__":
    export_to_excel()
