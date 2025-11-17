from app import init_db, add_player, add_voter, add_match, send_vote_emails
import pandas as pd

if __name__ == "__main__":
    init_db()

    # --- Load player list for this round ---
    players_df = pd.read_excel("players.xlsx")         # who is in the vote
    emails_df = pd.read_excel("player_emails.xlsx")    # master emails table

    # Basic checks
    if "Player" not in players_df.columns:
        raise ValueError("players.xlsx must have a 'Player' column.")

    required_email_cols = {"Player", "Email"}
    if not required_email_cols.issubset(emails_df.columns):
        raise ValueError("player_emails.xlsx must have 'Player' and 'Email' columns.")

    # Clean up whitespace
    players_df["Player"] = players_df["Player"].astype(str).str.strip()
    emails_df["Player"] = emails_df["Player"].astype(str).str.strip()
    emails_df["Email"] = emails_df["Email"].astype(str).str.strip()

    # Merge: keep all players from players.xlsx, bring in Email where available
    merged = players_df.merge(
        emails_df[["Player", "Email"]],
        on="Player",
        how="left"
    )

    # --- Add players + voters ---
    missing_emails = []

    for _, row in merged.iterrows():
        name = row["Player"]
        email = row.get("Email", "")

        if not name:
            continue  # skip blank

        # Add to players table (always)
        add_player(name)

        # Only add voter if we have an email
        if email and email.lower() != "nan":
            add_voter(name, email)
        else:
            missing_emails.append(name)

    if missing_emails:
        print("Warning: these players have no email in player_emails.xlsx:")
        for name in missing_emails:
            print("  -", name)

    # --- Ask for round name ---
    round_name = input("Enter round name (e.g. 'Round 1 vs Tigers'): ").strip()
    if not round_name:
        round_name = "Round 1"  # fallback if you just press Enter

    # --- Create a match with that name ---
    match_id = add_match(round_name)
    print(f"Created match with id: {match_id}, name: {round_name!r}")

    # --- Send vote links to each voter ---
    send_vote_emails(match_id)

    print("Setup done.")