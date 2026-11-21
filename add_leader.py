"""
Admin tool: create (or change the PIN of) a club leader account.
Run from the project folder:  python add_leader.py

The PIN is stored scrambled (hashed) in leaders.csv, so you cannot type it into the
file by hand - always use this tool.
"""

import main


def run():
    clubs = main.load_clubs()
    leaders = main.load_leaders(clubs)
    print("Clubs:", ", ".join(f"{c['club_id']} ({c['name']})" for c in clubs))
    club_id = main.ask_text("Club ID: ", required=True)
    leader_name = main.ask_text("Leader name: ", required=True)
    pin = main.ask_text("PIN (4-8 digits): ", required=True)
    ok, message = main.add_leader(leaders, clubs, club_id, leader_name, pin)
    print(message)
    if ok:
        main.save_rows(main.LEADERS_FILE, main.LEADER_FIELDS, leaders)
        print(f"Saved to {main.LEADERS_FILE}.")


if __name__ == "__main__":
    run()