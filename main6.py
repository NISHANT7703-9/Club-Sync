"""
Club SYNC - Campus Club Finder & Recommendation System
Bennett University | Computational Thinking and Programming (2026CSAE100)

A menu-driven command-line program with three kinds of users:
    Guest        - browses clubs, events and notices (no login)
    Student      - registers / logs in; gets a personal shortlist and "new notice" alerts
    Club leader  - logs in with the club password; manages ONLY their own club's details, events, notices

Libraries: csv and datetime (data), hashlib (so passwords/PINs are not stored as plain text),
os (to find the data files next to this program).

Data files (keep them in the same folder as main.py):
    clubs.csv      club information                 (edited by the admin)
    events.csv     events                           (edited by club leaders)
    notices.csv    notices / announcements          (posted by club leaders)
    leaders.csv    club leader accounts             (created with add_leader.py)
    students.csv   registered students              (created by the program)
    shortlist.csv  each student's saved clubs       (created by the program)
    recommendations.txt  optional text export of recommendation results
"""

import csv
import hashlib
import os
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
# The data files are looked up next to main.py, so the program works no matter which
# folder VS Code (or the terminal) starts it from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLUBS_FILE = os.path.join(BASE_DIR, "clubs.csv")
EVENTS_FILE = os.path.join(BASE_DIR, "events.csv")
NOTICES_FILE = os.path.join(BASE_DIR, "notices.csv")
LEADERS_FILE = os.path.join(BASE_DIR, "leaders.csv")
STUDENTS_FILE = os.path.join(BASE_DIR, "students.csv")
SHORTLIST_FILE = os.path.join(BASE_DIR, "shortlist.csv")
REPORT_FILE = os.path.join(BASE_DIR, "recommendations.txt")

CLUB_FIELDS = ["club_id", "name", "category", "description", "skills",
               "time_hrs", "eligibility", "recruitment", "selection", "contact"]
EVENT_FIELDS = ["event_id", "club_id", "title", "date", "venue", "description"]
NOTICE_FIELDS = ["notice_id", "club_id", "message", "posted", "expires"]
LEADER_FIELDS = ["club_id", "leader_name", "pin_hash"]
STUDENT_FIELDS = ["student_id", "name", "password_hash", "last_seen"]
SHORTLIST_FIELDS = ["student_id", "club_id", "date_added"]

# Scoring rules for "Find My Club" (rule-based, no machine learning)
POINTS_INTEREST = 5     # interest matches the club's category / activities
POINTS_SKILL = 3        # a selected skill matches the club's skills
POINTS_TIME = 2         # club's time commitment fits the student's free time
POINTS_RECRUITING = 1   # recruitment is open
MAX_SCORE = POINTS_INTEREST + POINTS_SKILL + POINTS_TIME + POINTS_RECRUITING

REMINDER_DAYS = 7           # startup reminder looks this many days ahead
MAX_LOGIN_ATTEMPTS = 3      # wrong passwords allowed before going back
MIN_PASSWORD_LENGTH = 4
MAX_NOTICE_LENGTH = 200     # characters
MAX_NOTICE_DAYS = 30        # a notice can stay visible for at most this many days
DATETIME_FORMAT = "%Y-%m-%d %H:%M"


# ---------------------------------------------------------------------------
# 1. FILE HANDLING (load / save CSV and TXT)
# ---------------------------------------------------------------------------
def parse_date(text):
    """Return a date from 'YYYY-MM-DD', or None if the text is not a valid date."""
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(text):
    """Return a datetime from 'YYYY-MM-DD HH:MM', or None if invalid / empty."""
    try:
        return datetime.strptime(text.strip(), DATETIME_FORMAT)
    except ValueError:
        return None


def read_rows(filename, required=True):
    """Read a CSV file into a list of dictionaries. Returns [] if it cannot be read."""
    try:
        with open(filename, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        if required:
            print(f"  [Error] {filename} not found. Keep all project files in the same folder as main.py.")
    except (OSError, csv.Error) as error:
        print(f"  [Error] Could not read {filename}: {error}")
    return []


def clean(row, fields):
    """Keep only the wanted fields, as stripped strings ('' when missing)."""
    return {key: (row.get(key) or "").strip() for key in fields}


def load_clubs():
    """Read clubs.csv. Rows with missing id/name or a non-numeric time are skipped."""
    clubs = []
    for line_no, row in enumerate(read_rows(CLUBS_FILE), start=2):
        club = clean(row, CLUB_FIELDS)
        if not club["club_id"] or not club["name"] or not club["time_hrs"].isdigit():
            print(f"  [Warning] Skipping malformed row {line_no} in {CLUBS_FILE}.")
            continue
        club["club_id"] = club["club_id"].upper()
        club["time_hrs"] = int(club["time_hrs"])
        club["recruitment"] = club["recruitment"].capitalize()
        clubs.append(club)
    return clubs


def load_events():
    """Read events.csv (adds a 'when' date object to each event)."""
    events = []
    for line_no, row in enumerate(read_rows(EVENTS_FILE), start=2):
        event = clean(row, EVENT_FIELDS)
        event["when"] = parse_date(event["date"])
        if not event["event_id"] or not event["title"] or event["when"] is None:
            print(f"  [Warning] Skipping malformed row {line_no} in {EVENTS_FILE}.")
            continue
        event["club_id"] = event["club_id"].upper()
        events.append(event)
    return events


def load_notices(clubs):
    """Read notices.csv (adds 'posted_at' datetime and 'expires_on' date objects)."""
    notices = []
    for line_no, row in enumerate(read_rows(NOTICES_FILE, required=False), start=2):
        notice = clean(row, NOTICE_FIELDS)
        notice["posted_at"] = parse_datetime(notice["posted"])
        notice["expires_on"] = parse_date(notice["expires"])
        notice["club_id"] = notice["club_id"].upper()
        if (not notice["notice_id"] or not notice["message"] or notice["posted_at"] is None
                or notice["expires_on"] is None or not find_club(clubs, notice["club_id"])):
            print(f"  [Warning] Skipping malformed row {line_no} in {NOTICES_FILE}.")
            continue
        notices.append(notice)
    return notices


def load_leaders(clubs):
    """Read leaders.csv. Leaders of clubs that no longer exist are ignored."""
    leaders = []
    for line_no, row in enumerate(read_rows(LEADERS_FILE, required=False), start=2):
        leader = clean(row, LEADER_FIELDS)
        leader["club_id"] = leader["club_id"].upper()
        if not leader["pin_hash"] or not find_club(clubs, leader["club_id"]):
            print(f"  [Warning] Skipping malformed row {line_no} in {LEADERS_FILE}.")
            continue
        leaders.append(leader)
    return leaders


def load_students():
    """Read students.csv (registered students). A missing file just means none yet."""
    students = []
    for line_no, row in enumerate(read_rows(STUDENTS_FILE, required=False), start=2):
        student = clean(row, STUDENT_FIELDS)
        student["student_id"] = student["student_id"].upper()
        if not student["student_id"] or not student["password_hash"]:
            print(f"  [Warning] Skipping malformed row {line_no} in {STUDENTS_FILE}.")
            continue
        students.append(student)
    return students


def load_shortlist(clubs, students):
    """Read shortlist.csv. Unknown students/clubs and duplicates are dropped."""
    rows = []
    for row in read_rows(SHORTLIST_FILE, required=False):
        entry = clean(row, SHORTLIST_FIELDS)
        entry["student_id"] = entry["student_id"].upper()
        entry["club_id"] = entry["club_id"].upper()
        if (find_student(students, entry["student_id"]) and find_club(clubs, entry["club_id"])
                and entry["club_id"] not in shortlisted_ids(rows, entry["student_id"])):
            rows.append(entry)
    return rows


def load_state():
    """Load every data file into one dictionary that is passed to all menu functions."""
    clubs = load_clubs()
    students = load_students()
    return {"clubs": clubs, "events": load_events(), "notices": load_notices(clubs),
            "leaders": load_leaders(clubs), "students": students,
            "shortlist": load_shortlist(clubs, students), "user": None}


def save_rows(filename, fields, rows):
    """Write a list of dictionaries to a CSV file. Returns True if it worked."""
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return True
    except OSError as error:
        print(f"  [Error] Could not save {filename}: {error}")
        return False


def save_data(state, name):
    """Save one dataset ('clubs', 'events', 'notices', 'leaders', 'students', 'shortlist')."""
    files = {"clubs": (CLUBS_FILE, CLUB_FIELDS), "events": (EVENTS_FILE, EVENT_FIELDS),
             "notices": (NOTICES_FILE, NOTICE_FIELDS), "leaders": (LEADERS_FILE, LEADER_FIELDS),
             "students": (STUDENTS_FILE, STUDENT_FIELDS), "shortlist": (SHORTLIST_FILE, SHORTLIST_FIELDS)}
    filename, fields = files[name]
    return save_rows(filename, fields, state[name])


def save_recommendations(ranked, interests, skills, hours):
    """Append the recommendation results to a text file with a timestamp."""
    stamp = datetime.now().strftime(DATETIME_FORMAT)
    lines = [f"Club SYNC recommendations - {stamp}",
             f"Interests: {', '.join(interests)}",
             f"Skills: {', '.join(skills) if skills else 'none given'}",
             f"Free time: {hours} hrs/week", ""]
    for position, (score, club, breakdown) in enumerate(ranked, start=1):
        lines.append(f"{position}. {club['name']} ({club['club_id']}) - {score}/{MAX_SCORE}")
        lines.extend(f"     - {reason}" for reason in reasons_from(breakdown))
    lines.append("-" * 50)
    try:
        with open(REPORT_FILE, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
        return True
    except OSError as error:
        print(f"  [Error] Could not write {REPORT_FILE}: {error}")
        return False


# ---------------------------------------------------------------------------
# 2. INPUT VALIDATION HELPERS
# ---------------------------------------------------------------------------
def ask_text(prompt, required=False):
    """Ask for text. If required, keep asking until something is typed."""
    while True:
        text = input(prompt).strip()
        if text or not required:
            return text
        print("  Input cannot be empty. Please try again.")


def ask_int(prompt, low, high):
    """Ask for a whole number between low and high (inclusive)."""
    while True:
        try:
            number = int(input(prompt).strip())
        except ValueError:
            print("  Invalid input. Please enter a whole number.")
            continue
        if low <= number <= high:
            return number
        print(f"  Please enter a number between {low} and {high}.")


def ask_int_optional(prompt, low, high):
    """Like ask_int, but pressing Enter skips (returns None)."""
    while True:
        text = input(prompt).strip()
        if not text:
            return None
        if text.isdigit() and low <= int(text) <= high:
            return int(text)
        print(f"  Please enter a number between {low} and {high}, or press Enter to skip.")


def ask_choice(prompt, options, optional=False):
    """Ask the user to type one of the options (case-insensitive)."""
    lookup = {option.lower(): option for option in options}
    while True:
        text = input(prompt).strip().lower()
        if not text and optional:
            return None
        if text in lookup:
            return lookup[text]
        print("  Invalid choice. Options: " + ", ".join(options))


def ask_yes_no(prompt):
    """Ask a yes/no question. Returns True for yes."""
    while True:
        text = input(prompt).strip().lower()
        if text in ("y", "yes"):
            return True
        if text in ("n", "no"):
            return False
        print("  Please answer y or n.")


def ask_date_optional(prompt):
    """Ask for a date in YYYY-MM-DD. Enter skips (returns None)."""
    while True:
        text = input(prompt).strip()
        if not text:
            return None
        parsed = parse_date(text)
        if parsed:
            return parsed
        print("  Invalid date. Use the format YYYY-MM-DD (e.g. 2026-11-15).")


def ask_date_required(prompt):
    """Ask for a date in YYYY-MM-DD until a valid one is typed."""
    while True:
        when = ask_date_optional(prompt)
        if when:
            return when
        print("  A date is required.")


def valid_email(text):
    """Very simple email check: something@something.something, no spaces."""
    local, _, domain = text.partition("@")
    return (bool(local) and " " not in text and "." in domain
            and not domain.startswith(".") and not domain.endswith("."))


def ask_email(prompt):
    while True:
        text = input(prompt).strip()
        if valid_email(text):
            return text
        print("  Invalid email. Example: name@bennett.example")


def ask_club_id(clubs, prompt, optional=False):
    """Ask for a club ID that exists in the data."""
    while True:
        text = input(prompt).strip().upper()
        if not text and optional:
            return None
        club = find_club(clubs, text)
        if club:
            return club["club_id"]
        print("  No club with that ID. Try again.")


def parse_list(text):
    """'Python, Java ' -> ['python', 'java'] (lower-case, no blanks)."""
    return [item.strip().lower() for item in text.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# 3. ACCOUNTS: passwords, registration, login checks (logic only - easy to test)
# ---------------------------------------------------------------------------
def hash_secret(user_id, secret):
    """
    One-way scrambled version of a password. The plain text is never saved.
    ALL spaces are removed and upper/lower case is ignored before scrambling, so
    'S26CSEU0993@bennett.edu.in', ' s26cseu0993@Bennett.edu.in ' and
    'Geeks For Geeks.bennett.edu.in' / 'geeksforgeeks.bennett.edu.in' all count as the same.
    """
    cleaned = "".join(secret.split()).lower()
    return hashlib.sha256(f"{user_id.upper()}:{cleaned}".encode("utf-8")).hexdigest()


def default_club_password(club):
    """Standard club password: the club name + '@bennett.edu.in' (e.g. geeksforgeeks@bennett.edu.in)."""
    return "".join(club["name"].split()).lower() + "@bennett.edu.in"


def canonical_club_password(password):
    """
    The one form a club password is stored in: clubname@bennett.edu.in.
    Typing 'clubname.bennett.edu.in' (a dot instead of @) is accepted too.
    """
    cleaned = "".join(password.split()).lower()
    suffix = ".bennett.edu.in"
    if "@" not in cleaned and cleaned.endswith(suffix):
        cleaned = cleaned[:-len(suffix)] + "@bennett.edu.in"
    return cleaned


def find_student(students, student_id):
    for student in students:
        if student["student_id"] == student_id.upper():
            return student
    return None


def find_leader(leaders, club_id):
    for leader in leaders:
        if leader["club_id"] == club_id.upper():
            return leader
    return None


def valid_student_id(text):
    """Enrollment number: 6-15 letters/digits, e.g. S26CSEU0993."""
    return text.isalnum() and 6 <= len(text) <= 15


def register_student(students, student_id, name, password):
    """Add a new student. Returns (True, message) or (False, reason)."""
    student_id = student_id.strip().upper()
    if not valid_student_id(student_id):
        return False, "Enrollment number must be 6-15 letters/digits (e.g. S26CSEU0993)."
    if find_student(students, student_id):
        return False, "That enrollment number is already registered. Please log in."
    if not name.strip():
        return False, "Name cannot be empty."
    if len("".join(password.split())) < MIN_PASSWORD_LENGTH:
        return False, f"Password must have at least {MIN_PASSWORD_LENGTH} characters."
    students.append({"student_id": student_id, "name": name.strip(),
                     "password_hash": hash_secret(student_id, password), "last_seen": ""})
    return True, "Registration successful."


def check_student_login(students, student_id, password):
    """Return the student record if the password is right, otherwise None."""
    student = find_student(students, student_id)
    if student and student["password_hash"] == hash_secret(student["student_id"], password):
        return student
    return None


def check_leader_login(leaders, club_id, password):
    """Return the leader record if the club password is right, otherwise None."""
    leader = find_leader(leaders, club_id)
    if leader and leader["pin_hash"] == hash_secret(leader["club_id"], canonical_club_password(password)):
        return leader
    return None


def add_leader(leaders, clubs, club_id, leader_name, password):
    """Create or replace the leader of a club (used by add_leader.py). Returns (ok, message)."""
    club_id = club_id.strip().upper()
    if not find_club(clubs, club_id):
        return False, "No club with that ID in clubs.csv."
    if not leader_name.strip():
        return False, "Leader name cannot be empty."
    if len("".join(password.split())) < MIN_PASSWORD_LENGTH:
        return False, f"Password must have at least {MIN_PASSWORD_LENGTH} characters."
    record = {"club_id": club_id, "leader_name": leader_name.strip(),
              "pin_hash": hash_secret(club_id, canonical_club_password(password))}
    existing = find_leader(leaders, club_id)
    if existing:
        existing.update(record)
        return True, "Leader updated."
    leaders.append(record)
    return True, "Leader added."


def login_loop(id_prompt, secret_prompt, checker):
    """Ask for ID + secret up to MAX_LOGIN_ATTEMPTS times. Returns the record or None."""
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        identifier = input(id_prompt).strip().upper()
        secret = input(secret_prompt)
        record = checker(identifier, secret)
        if record:
            return record
        left = MAX_LOGIN_ATTEMPTS - attempt
        if left:
            print(f"  Wrong ID or password. {left} attempt(s) left.")
        else:
            print("  Too many failed attempts. Returning to the start menu.")
    return None


# ---------------------------------------------------------------------------
# 4. CLUB LOOKUP, SEARCH, FILTER
# ---------------------------------------------------------------------------
def find_club(clubs, club_id):
    for club in clubs:
        if club["club_id"].upper() == club_id.upper():
            return club
    return None


def skills_of(club):
    """Set of lower-case skills for a club ('python;c++' -> {'python', 'c++'})."""
    return {s.strip().lower() for s in club["skills"].split(";") if s.strip()}


def search_clubs(clubs, keyword):
    """
    Clubs whose name, category or skills match the keyword(s).
    With several words, clubs matching more words are listed first.
    """
    words = keyword.lower().split()
    scored = []
    for club in clubs:
        haystack = [club["name"].lower(), club["category"].lower()] + list(skills_of(club))
        hits = sum(1 for word in words if any(word in item for item in haystack))
        if hits > 0:
            scored.append((hits, club))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    return [club for _, club in scored]


def suggest_keywords(clubs, keyword, limit=3):
    """'Did you mean' helper: known words that start with the same 3 letters."""
    keyword = keyword.lower().strip()
    if len(keyword) < 3:
        return []
    known = set()
    for club in clubs:
        known.update(club["name"].lower().split())
        known.update(club["category"].lower().split())
        known.update(skills_of(club))
    return sorted(word for word in known if word.startswith(keyword[:3]))[:limit]


def filter_clubs(clubs, category=None, max_hours=None, recruitment=None,
                 skill=None, eligibility=None):
    """Apply every filter that is not None."""
    results = []
    for club in clubs:
        if category and club["category"].lower() != category.lower():
            continue
        if max_hours is not None and club["time_hrs"] > max_hours:
            continue
        if recruitment and club["recruitment"].lower() != recruitment.lower():
            continue
        if skill and not any(skill.lower() in s for s in skills_of(club)):
            continue
        if eligibility and eligibility.lower() not in club["eligibility"].lower():
            continue
        results.append(club)
    return results


# ---------------------------------------------------------------------------
# 5. RECOMMENDATION (rule-based scoring with a full explanation)
# ---------------------------------------------------------------------------
def score_club(club, interests, skills, hours, preferred_category=None):
    """
    Score one club using the four rules.
    Returns (score, breakdown, relevant).
      breakdown = list of (rule name, points earned, points possible, explanation)
      relevant  = True only if the interest or a skill matched, so a club that merely
                  has open recruitment is never recommended.
    """
    breakdown = []

    # Rule 1: interest / category match
    text = " ".join([club["name"], club["category"], club["description"]]).lower()
    matched_interests = [i for i in interests if i in text]
    if preferred_category and club["category"].lower() == preferred_category.lower():
        breakdown.append(("Interest / category", POINTS_INTEREST, POINTS_INTEREST,
                          f"'{club['category']}' is your preferred category"))
    elif matched_interests:
        breakdown.append(("Interest / category", POINTS_INTEREST, POINTS_INTEREST,
                          "matched " + ", ".join(f"'{i}'" for i in matched_interests)
                          + " in the club's name/category/description"))
    else:
        breakdown.append(("Interest / category", 0, POINTS_INTEREST,
                          "none of your interests appear in the club's name, category or description"))

    # Rule 2: skill match
    club_skills = skills_of(club)
    matched_skills = sorted({cs for s in skills for cs in club_skills if s in cs})
    if matched_skills:
        breakdown.append(("Skill match", POINTS_SKILL, POINTS_SKILL,
                          "your skill(s) match: " + ", ".join(matched_skills)))
    elif not skills:
        breakdown.append(("Skill match", 0, POINTS_SKILL, "you did not enter any skills"))
    else:
        breakdown.append(("Skill match", 0, POINTS_SKILL,
                          "none of your skills match (club uses: " + ", ".join(sorted(club_skills)) + ")"))

    # Rule 3: time commitment
    if club["time_hrs"] <= hours:
        breakdown.append(("Time fit", POINTS_TIME, POINTS_TIME,
                          f"needs {club['time_hrs']} hrs/week and you have {hours}"))
    else:
        breakdown.append(("Time fit", 0, POINTS_TIME,
                          f"needs {club['time_hrs']} hrs/week but you only have {hours}"))

    # Rule 4: recruitment status
    if club["recruitment"].lower() == "open":
        breakdown.append(("Recruitment open", POINTS_RECRUITING, POINTS_RECRUITING, "recruitment is open"))
    else:
        breakdown.append(("Recruitment open", 0, POINTS_RECRUITING, "recruitment is closed right now"))

    score = sum(earned for _, earned, _, _ in breakdown)
    relevant = breakdown[0][1] > 0 or breakdown[1][1] > 0
    return score, breakdown, relevant


def reasons_from(breakdown):
    """Short lines for the rules that earned points."""
    return [f"{rule} (+{earned}): {why}" for rule, earned, _, why in breakdown if earned > 0]


def recommend_clubs(clubs, interests, skills, hours, preferred_category=None, top_n=5):
    """Return the top clubs as a list of (score, club, breakdown), best first."""
    ranked = []
    for club in clubs:
        score, breakdown, relevant = score_club(club, interests, skills, hours, preferred_category)
        if relevant:
            ranked.append((score, club, breakdown))
    ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
    return ranked[:top_n]


# ---------------------------------------------------------------------------
# 6. EVENTS, NOTICES, SHORTLIST, STATISTICS (logic)
# ---------------------------------------------------------------------------
def filter_events(events, today, club_id=None, until=None):
    """Upcoming events (date >= today), optionally for one club / up to a date."""
    results = []
    for event in events:
        if event["when"] < today:
            continue
        if club_id and event["club_id"].upper() != club_id.upper():
            continue
        if until and event["when"] > until:
            continue
        results.append(event)
    results.sort(key=lambda e: e["when"])
    return results


def days_until_text(when, today):
    """'today', 'tomorrow' or 'in N days'."""
    days = (when - today).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def next_id(items, key, prefix):
    """Next free ID like CB13 / EV10 / NT05."""
    numbers = []
    for item in items:
        tail = item[key][len(prefix):]
        if item[key].upper().startswith(prefix) and tail.isdigit():
            numbers.append(int(tail))
    return f"{prefix}{max(numbers, default=0) + 1:02d}"


def make_notice(notices, club_id, message, posted_at, expires_on):
    """Create a notice dictionary and add it to the list."""
    posted_at = posted_at.replace(second=0, microsecond=0)
    notice = {"notice_id": next_id(notices, "notice_id", "NT"), "club_id": club_id.upper(),
              "message": message.strip(), "posted": posted_at.strftime(DATETIME_FORMAT),
              "expires": str(expires_on), "posted_at": posted_at, "expires_on": expires_on}
    notices.append(notice)
    return notice


def active_notices(notices, today):
    """Notices that have not expired (a notice is still visible ON its expiry date), newest first."""
    live = [n for n in notices if n["expires_on"] >= today]
    live.sort(key=lambda n: n["posted_at"], reverse=True)
    return live


def new_notices(notices, last_seen, today):
    """Active notices posted after the student's last visit (all of them if never visited)."""
    return [n for n in active_notices(notices, today)
            if last_seen is None or n["posted_at"] > last_seen]


def order_for_student(notices, starred_club_ids):
    """Put notices of shortlisted clubs first (the sort is stable, so newest stays first)."""
    return sorted(notices, key=lambda n: n["club_id"] not in starred_club_ids)


def shortlisted_ids(shortlist, student_id):
    """Set of club IDs on one student's shortlist."""
    return {e["club_id"] for e in shortlist if e["student_id"] == student_id.upper()}


def add_to_shortlist(shortlist, student_id, club_id, today):
    """Add a club to a student's shortlist. Returns False if it was already there."""
    if club_id.upper() in shortlisted_ids(shortlist, student_id):
        return False
    shortlist.append({"student_id": student_id.upper(), "club_id": club_id.upper(),
                      "date_added": str(today)})
    return True


def remove_from_shortlist(shortlist, student_id, club_id):
    """Remove a club from a student's shortlist. Returns False if it was not there."""
    before = len(shortlist)
    shortlist[:] = [e for e in shortlist
                    if not (e["student_id"] == student_id.upper() and e["club_id"] == club_id.upper())]
    return len(shortlist) < before


def compute_stats(clubs, events, today):
    """Summary numbers about the club data (used by the Statistics menu)."""
    per_category = {}
    for club in clubs:
        per_category[club["category"]] = per_category.get(club["category"], 0) + 1
    open_count = sum(1 for c in clubs if c["recruitment"].lower() == "open")
    hours = [c["time_hrs"] for c in clubs]
    return {
        "total": len(clubs),
        "open": open_count,
        "closed": len(clubs) - open_count,
        "per_category": per_category,
        "avg_hours": round(sum(hours) / len(hours), 1) if hours else 0,
        "most_demanding": max(clubs, key=lambda c: c["time_hrs"]) if clubs else None,
        "least_demanding": min(clubs, key=lambda c: c["time_hrs"]) if clubs else None,
        "upcoming_events": len(filter_events(events, today)),
    }


# ---------------------------------------------------------------------------
# 7. DISPLAY HELPERS
# ---------------------------------------------------------------------------
def wrap_text(text, width):
    """Split text into lines no longer than width (simple word wrap)."""
    lines, current = [], ""
    for word in text.split():
        while len(word) > width:                 # very long word: chop it
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    lines.append(current)
    return lines


def my_starred(state):
    """Club IDs on the logged-in student's shortlist (empty for guests and leaders)."""
    user = state["user"]
    if user and user["role"] == "student":
        return shortlisted_ids(state["shortlist"], user["id"])
    return set()


def print_club_table(clubs, starred=()):
    """Table of clubs. Clubs in `starred` (the shortlist) get a * in front."""
    print(f" {'ID':<6}{'Name':<24}{'Category':<18}{'Hrs/wk':<8}{'Recruitment'}")
    print("-" * 67)
    for club in clubs:
        mark = "*" if club["club_id"] in starred else " "
        print(f"{mark}{club['club_id']:<6}{club['name'][:22]:<24}{club['category'][:16]:<18}"
              f"{club['time_hrs']:<8}{club['recruitment']}")
    if starred:
        print("(* = on your shortlist)")


def show_club_details(club):
    print("\n" + "=" * 60)
    print(f"{club['name']}  ({club['club_id']})")
    print("=" * 60)
    print(f"Category    : {club['category']}")
    print(f"About       : {club['description']}")
    print(f"Skills      : {', '.join(sorted(skills_of(club)))}")
    print(f"Time        : {club['time_hrs']} hrs/week")
    print(f"Eligibility : {club['eligibility']}")
    print(f"Recruitment : {club['recruitment']}")
    print(f"Selection   : {club['selection']}")
    print(f"Contact     : {club['contact']}")


def offer_details(shown_clubs, state):
    """Pick one of the clubs just displayed to see details. Students may shortlist it."""
    user = state["user"]
    while True:
        text = input("\nEnter a club ID for details (or press Enter to go back): ").strip()
        if not text:
            return
        club = find_club(shown_clubs, text)
        if not club:
            print("  That ID is not in the list above.")
            continue
        show_club_details(club)
        if user["role"] != "student":
            print("\n(Log in as a student to save clubs to a shortlist.)")
        elif club["club_id"] in my_starred(state):
            print("\n(This club is already on your shortlist.)")
        elif ask_yes_no("\nAdd this club to your shortlist? (y/n): "):
            add_to_shortlist(state["shortlist"], user["id"], club["club_id"], date.today())
            if save_data(state, "shortlist"):
                print("  Added to your shortlist.")


def print_comparison(selected):
    label_w, col_w = 18, 28
    rows = [("Name", lambda c: c["name"]),
            ("Category", lambda c: c["category"]),
            ("Time (hrs/week)", lambda c: str(c["time_hrs"])),
            ("Skills", lambda c: ", ".join(sorted(skills_of(c)))),
            ("Eligibility", lambda c: c["eligibility"]),
            ("Recruitment", lambda c: c["recruitment"]),
            ("Selection", lambda c: c["selection"]),
            ("Contact", lambda c: c["contact"])]
    print("\n" + "=" * (label_w + col_w * len(selected)))
    for label, getter in rows:
        columns = [wrap_text(getter(club), col_w - 2) for club in selected]
        height = max(len(col) for col in columns)
        for i in range(height):
            left = label if i == 0 else ""
            line = f"{left:<{label_w}}"
            for col in columns:
                line += f"{(col[i] if i < len(col) else ''):<{col_w}}"
            print(line)
        print("-" * (label_w + col_w * len(selected)))

    common_skills = set.intersection(*[skills_of(c) for c in selected])
    print("Skills in common :", ", ".join(sorted(common_skills)) if common_skills else "none")
    print("Same category    :", "yes" if len({c["category"] for c in selected}) == 1 else "no")
    lowest = min(selected, key=lambda c: c["time_hrs"])
    print(f"Least time needed: {lowest['name']} ({lowest['time_hrs']} hrs/week)")
    open_clubs = [c["name"] for c in selected if c["recruitment"].lower() == "open"]
    print("Recruiting now   :", ", ".join(open_clubs) if open_clubs else "none")


def print_events(events, clubs, today, starred=()):
    """Event table with a 'When' countdown. Events of shortlisted clubs get a *."""
    print(f" {'ID':<6}{'Date':<12}{'When':<12}{'Club':<20}{'Event'}")
    print("-" * 74)
    for event in events:
        club = find_club(clubs, event["club_id"])
        club_name = club["name"] if club else event["club_id"]
        mark = "*" if event["club_id"] in starred else " "
        print(f"{mark}{event['event_id']:<6}{event['date']:<12}"
              f"{days_until_text(event['when'], today):<12}{club_name[:18]:<20}{event['title']}")
    if starred:
        print("(* = hosted by a shortlisted club)")


def print_notices(notices, clubs, today, starred=(), last_seen=None, track_new=False):
    """Show notices. With track_new, notices posted after last_seen are tagged NEW."""
    for notice in notices:
        club = find_club(clubs, notice["club_id"])
        club_name = club["name"] if club else notice["club_id"]
        tags = ""
        if track_new and (last_seen is None or notice["posted_at"] > last_seen):
            tags += "[NEW] "
        if notice["club_id"] in starred:
            tags += "* "
        print(f"\n{tags}{club_name}  -  posted {notice['posted']}, "
              f"visible until {notice['expires']} ({days_until_text(notice['expires_on'], today)})")
        for line in wrap_text(notice["message"], 66):
            print("     " + line)
    if starred:
        print("\n(* = from a shortlisted club)")


def print_statistics(stats):
    print("\n=== Club Statistics ===")
    print(f"Total clubs        : {stats['total']}")
    print(f"Recruiting (Open)  : {stats['open']}    Closed: {stats['closed']}")
    print(f"Average time needed: {stats['avg_hours']} hrs/week")
    if stats["most_demanding"]:
        print(f"Most time needed   : {stats['most_demanding']['name']} "
              f"({stats['most_demanding']['time_hrs']} hrs/week)")
        print(f"Least time needed  : {stats['least_demanding']['name']} "
              f"({stats['least_demanding']['time_hrs']} hrs/week)")
    print(f"Upcoming events    : {stats['upcoming_events']}")
    print("\nClubs per category:")
    for category in sorted(stats["per_category"]):
        count = stats["per_category"][category]
        print(f"  {category:<18}{'#' * count} {count}")


def print_breakdown(club, score, breakdown):
    """Show exactly how a club's score was worked out (explainability)."""
    print(f"\n--- How {club['name']} scored: {score}/{MAX_SCORE} ---")
    print(f"{'Rule':<22}{'Points':<10}{'Why'}")
    print("-" * 70)
    for rule, earned, possible, why in breakdown:
        print(f"{rule:<22}{str(earned) + '/' + str(possible):<10}{why}")
    if not (breakdown[0][1] or breakdown[1][1]):
        print("\nThis club is NOT recommended: neither an interest nor a skill matched,")
        print("and a club is only recommended when at least one of them matches.")


def show_reminders(state, today):
    """Notice for events happening in the next few days."""
    soon = filter_events(state["events"], today, until=today + timedelta(days=REMINDER_DAYS))
    if not soon:
        return
    print(f"\nReminder: {len(soon)} event(s) in the next {REMINDER_DAYS} days")
    print_events(soon[:5], state["clubs"], today, my_starred(state))


# ---------------------------------------------------------------------------
# 8. STUDENT / GUEST MENU ACTIONS (each takes the shared `state`)
# ---------------------------------------------------------------------------
def view_all_clubs(state):
    if not state["clubs"]:
        print("\nNo clubs available.")
        return
    print("\n----------- ALL CLUBS -----------")
    print_club_table(state["clubs"], my_starred(state))
    offer_details(state["clubs"], state)


def search_menu(state):
    clubs = state["clubs"]
    keyword = ask_text("\nEnter keyword(s) (name / category / skill): ", required=True)
    results = search_clubs(clubs, keyword)
    if not results:
        print(f"\nNo clubs found for '{keyword}'.")
        hints = suggest_keywords(clubs, keyword)
        if hints:
            print("Did you mean: " + ", ".join(hints) + "?")
        return
    print(f"\n{len(results)} club(s) found for '{keyword}':")
    print_club_table(results, my_starred(state))
    offer_details(results, state)


def filter_menu(state):
    clubs = state["clubs"]
    print("\n--- Filter clubs (press Enter to skip any filter) ---")
    categories = sorted({c["category"] for c in clubs})
    print("Categories:", ", ".join(categories))
    category = ask_choice("Category: ", categories, optional=True)
    max_hours = ask_int_optional("Maximum hours per week (1-40): ", 1, 40)
    recruitment = ask_choice("Recruitment status (Open/Closed): ", ["Open", "Closed"], optional=True)
    skill = ask_text("Required skill (e.g. python): ") or None
    eligibility = ask_text("Eligibility keyword (e.g. first, all years): ") or None

    results = filter_clubs(clubs, category, max_hours, recruitment, skill, eligibility)
    if not results:
        print("\nNo clubs match those filters.")
        return
    print(f"\n{len(results)} club(s) match:")
    print_club_table(results, my_starred(state))
    offer_details(results, state)


def explain_loop(state, interests, skills, hours, preferred):
    """Let the user see the score breakdown of any club (even one that was not recommended)."""
    while True:
        text = input("\nEnter a club ID to see how its score was worked out (or press Enter to skip): ").strip()
        if not text:
            return
        club = find_club(state["clubs"], text)
        if not club:
            print("  No club with that ID.")
            continue
        score, breakdown, _ = score_club(club, interests, skills, hours, preferred)
        print_breakdown(club, score, breakdown)


def find_my_club(state):
    clubs = state["clubs"]
    print("\n--- Find My Club ---")
    interests = parse_list(ask_text("Your interests (comma separated, e.g. coding, music): ", required=True))
    categories = sorted({c["category"] for c in clubs})
    print("Categories:", ", ".join(categories))
    preferred = ask_choice("Preferred category (optional): ", categories, optional=True)
    hours = ask_int("Free hours per week for a club (1-40): ", 1, 40)
    skills = parse_list(ask_text("Skills/experience you have (comma separated, optional): "))

    ranked = recommend_clubs(clubs, interests, skills, hours, preferred)
    if not ranked:
        print("\nNo clubs matched your interests or skills. Try different keywords.")
        return
    print(f"\n=== Top matches (score out of {MAX_SCORE}) ===")
    for position, (score, club, breakdown) in enumerate(ranked, start=1):
        print(f"\n{position}. {club['name']} ({club['club_id']})  -  Score: {score}/{MAX_SCORE}")
        for reason in reasons_from(breakdown):
            print(f"     - {reason}")
    print("\nNote: the score is only a guide. The choice of club is yours.")
    if ask_yes_no("\nSave these results to recommendations.txt? (y/n): "):
        if save_recommendations(ranked, interests, skills, hours):
            print(f"  Saved to {REPORT_FILE}.")
    explain_loop(state, interests, skills, hours, preferred)
    offer_details([club for _, club, _ in ranked], state)


def choose_clubs_to_compare(pool):
    """Ask for 2-3 valid, different club IDs from `pool` and return those clubs."""
    while True:
        text = ask_text("\nEnter 2 or 3 club IDs separated by commas (e.g. CB01, CB02): ", required=True)
        ids = []
        for item in text.split(","):
            item = item.strip().upper()
            if item and item not in ids:
                ids.append(item)
        if not 2 <= len(ids) <= 3:
            print("  Please enter 2 or 3 different club IDs.")
            continue
        missing = [i for i in ids if not find_club(pool, i)]
        if missing:
            print("  Unknown club ID(s): " + ", ".join(missing))
            continue
        return [find_club(pool, i) for i in ids]


def compare_menu(state):
    clubs = state["clubs"]
    print("\n--- Compare Clubs ---")
    if len(clubs) < 2:
        print("At least two clubs are needed to compare.")
        return
    print_club_table(clubs, my_starred(state))
    print_comparison(choose_clubs_to_compare(clubs))


def view_events(state):
    today = date.today()
    print(f"\n--- Upcoming Events (today is {today}) ---")
    club_id = ask_club_id(state["clubs"], "Filter by club ID (press Enter for all clubs): ", optional=True)
    until = ask_date_optional("Show events up to date YYYY-MM-DD (press Enter to skip): ")
    results = filter_events(state["events"], today, club_id, until)
    if not results:
        print("\nNo upcoming events found.")
        return
    print()
    print_events(results, state["clubs"], today, my_starred(state))
    while True:
        text = input("\nEnter an event ID for details (or press Enter to go back): ").strip().upper()
        if not text:
            return
        match = [e for e in results if e["event_id"].upper() == text]
        if not match:
            print("  That ID is not in the list above.")
            continue
        event = match[0]
        club = find_club(state["clubs"], event["club_id"])
        print(f"\n{event['title']}  ({event['event_id']})")
        print(f"Club  : {club['name'] if club else event['club_id']}")
        print(f"Date  : {event['date']} ({days_until_text(event['when'], today)})")
        print(f"Venue : {event['venue']}")
        print(f"About : {event['description']}")


def notices_menu(state):
    """Show current notices. For a logged-in student, new ones are tagged and 'last visit' is updated."""
    user = state["user"]
    today = date.today()
    live = active_notices(state["notices"], today)
    if not live:
        print("\nNo current notices.")
        return
    student = find_student(state["students"], user["id"]) if user["role"] == "student" else None
    last_seen = parse_datetime(student["last_seen"]) if student else None
    starred = my_starred(state)
    print("\n--- Notices ---")
    print_notices(order_for_student(live, starred), state["clubs"], today, starred,
                  last_seen, track_new=student is not None)
    if student:
        student["last_seen"] = datetime.now().strftime(DATETIME_FORMAT)
        save_data(state, "students")
    else:
        print("\n(Log in as a student to see which notices are new since your last visit.)")


def shortlist_menu(state):
    user = state["user"]
    if user["role"] != "student":
        print("\nPlease log in as a student to use a shortlist (choose Student > Login at the start).")
        return
    while True:
        mine = [e for e in state["shortlist"] if e["student_id"] == user["id"]]
        print("\n--- My Shortlist ---")
        if not mine:
            print("Your shortlist is empty. Open a club's details from the other menus")
            print("and answer 'y' to add it here.")
            return
        pool = [find_club(state["clubs"], e["club_id"]) for e in mine]
        print(f" {'ID':<6}{'Name':<24}{'Category':<18}{'Added'}")
        print("-" * 62)
        for entry, club in zip(mine, pool):
            print(f" {club['club_id']:<6}{club['name'][:22]:<24}{club['category'][:16]:<18}{entry['date_added']}")
        print("\n1. View club details\n2. Remove a club\n3. Compare shortlisted clubs\n4. Back to main menu")
        choice = ask_int("Choose (1-4): ", 1, 4)
        if choice == 1:
            show_club_details(find_club(pool, ask_club_id(pool, "Club ID: ")))
        elif choice == 2:
            club_id = ask_club_id(pool, "Club ID to remove: ")
            if remove_from_shortlist(state["shortlist"], user["id"], club_id) and save_data(state, "shortlist"):
                print("  Removed from your shortlist.")
        elif choice == 3:
            if len(pool) < 2:
                print("  Shortlist at least two clubs to compare them.")
            else:
                print_comparison(choose_clubs_to_compare(pool))
        else:
            return


def statistics_menu(state):
    if not state["clubs"]:
        print("\nNo club data to summarise.")
        return
    print_statistics(compute_stats(state["clubs"], state["events"], date.today()))


# ---------------------------------------------------------------------------
# 9. CLUB LEADER MENU ACTIONS - every action is limited to the leader's own club
# ---------------------------------------------------------------------------
def leader_club(state):
    return find_club(state["clubs"], state["user"]["club_id"])


def leader_events(state):
    """Only the events of the logged-in leader's club."""
    club_id = state["user"]["club_id"]
    return sorted((e for e in state["events"] if e["club_id"] == club_id), key=lambda e: e["when"])


def ask_event_id(pool, prompt):
    """Ask for an event ID that is inside `pool` (so a leader cannot pick another club's event)."""
    while True:
        text = input(prompt).strip().upper()
        for event in pool:
            if event["event_id"].upper() == text:
                return event
        print("  No event with that ID in your club.")


def leader_view_club(state):
    show_club_details(leader_club(state))


def leader_update_club(state):
    club = leader_club(state)
    editable = ["recruitment", "time_hrs", "contact", "eligibility", "selection", "description"]
    field = ask_choice("Field to change (" + "/".join(editable) + "): ", editable)
    if field == "recruitment":
        club[field] = ask_choice("New value (Open/Closed): ", ["Open", "Closed"])
    elif field == "time_hrs":
        club[field] = ask_int("New hours per week (1-40): ", 1, 40)
    elif field == "contact":
        club[field] = ask_email("New contact email: ")
    else:
        club[field] = ask_text(f"New {field}: ", required=True)
    if save_data(state, "clubs"):
        print(f"\n{club['name']} updated and saved.")
    if field == "recruitment" and ask_yes_no("Post a notice about the new recruitment status? (y/n): "):
        status = "OPEN" if club["recruitment"] == "Open" else "CLOSED"
        make_notice(state["notices"], club["club_id"], f"Recruitment is now {status} for {club['name']}.",
                    datetime.now(), date.today() + timedelta(days=7))
        if save_data(state, "notices"):
            print("  Notice posted (visible for 7 days).")


def leader_list_events(state):
    events = leader_events(state)
    if not events:
        print("\nYour club has no events yet.")
        return
    print()
    print_events(events, state["clubs"], date.today())


def leader_add_event(state):
    club = leader_club(state)
    event = {"event_id": next_id(state["events"], "event_id", "EV"), "club_id": club["club_id"]}
    event["title"] = ask_text("Event title: ", required=True)
    when = ask_date_required("Date (YYYY-MM-DD): ")
    if when < date.today():
        print("  Note: that date is in the past, so students will not see it as upcoming.")
    event["date"] = str(when)
    event["when"] = when
    event["venue"] = ask_text("Venue: ", required=True)
    event["description"] = ask_text("Short description: ", required=True)
    state["events"].append(event)
    if save_data(state, "events"):
        print(f"\nEvent added and saved as {event['event_id']}.")
    if when >= date.today():            # automatic notice, visible until the event day
        make_notice(state["notices"], club["club_id"],
                    f"New event: {event['title']} on {event['date']} at {event['venue']}.",
                    datetime.now(), when)
        if save_data(state, "notices"):
            print("  A notice about this event was posted automatically.")


def leader_edit_event(state):
    pool = leader_events(state)
    if not pool:
        print("\nYour club has no events to edit.")
        return
    print()
    print_events(pool, state["clubs"], date.today())
    event = ask_event_id(pool, "\nEvent ID to edit: ")
    field = ask_choice("Field to change (title/date/venue/description): ",
                       ["title", "date", "venue", "description"])
    if field == "date":
        when = ask_date_required("New date (YYYY-MM-DD): ")
        event["date"], event["when"] = str(when), when
    else:
        event[field] = ask_text(f"New {field}: ", required=True)
    if save_data(state, "events"):
        print("\nEvent updated and saved.")
    if field in ("date", "venue") and event["when"] >= date.today():
        make_notice(state["notices"], event["club_id"],
                    f"Update: {event['title']} is now on {event['date']} at {event['venue']}.",
                    datetime.now(), event["when"])
        if save_data(state, "notices"):
            print("  A notice about the change was posted automatically.")


def leader_delete_event(state):
    pool = leader_events(state)
    if not pool:
        print("\nYour club has no events to delete.")
        return
    print()
    print_events(pool, state["clubs"], date.today())
    event = ask_event_id(pool, "\nEvent ID to delete: ")
    if not ask_yes_no(f"Delete '{event['title']}'? (y/n): "):
        print("  Cancelled. Nothing was deleted.")
        return
    state["events"].remove(event)
    if save_data(state, "events"):
        print("\nEvent deleted and saved.")


def leader_post_notice(state):
    club = leader_club(state)
    while True:
        message = ask_text("Notice message: ", required=True)
        if len(message) <= MAX_NOTICE_LENGTH:
            break
        print(f"  Too long ({len(message)} characters). Maximum is {MAX_NOTICE_LENGTH}.")
    days = ask_int(f"Show this notice for how many days (1-{MAX_NOTICE_DAYS})? ", 1, MAX_NOTICE_DAYS)
    notice = make_notice(state["notices"], club["club_id"], message, datetime.now(),
                         date.today() + timedelta(days=days))
    if save_data(state, "notices"):
        print(f"\nNotice {notice['notice_id']} posted. It is visible until {notice['expires']}.")


def leader_notices(state):
    club_id = state["user"]["club_id"]
    mine = sorted((n for n in state["notices"] if n["club_id"] == club_id),
                  key=lambda n: n["posted_at"], reverse=True)
    if not mine:
        print("\nYour club has not posted any notices.")
        return
    today = date.today()
    print(f"\n{'ID':<6}{'Posted':<18}{'Status':<18}{'Message'}")
    print("-" * 70)
    for n in mine:
        status = "expired" if n["expires_on"] < today else f"until {n['expires']}"
        print(f"{n['notice_id']:<6}{n['posted']:<18}{status:<18}{n['message'][:40]}")
    text = input("\nEnter a notice ID to delete it (or press Enter to go back): ").strip().upper()
    if not text:
        return
    match = [n for n in mine if n["notice_id"].upper() == text]
    if not match:
        print("  No notice with that ID in your club.")
    elif ask_yes_no(f"Delete notice {match[0]['notice_id']}? (y/n): "):
        state["notices"].remove(match[0])
        if save_data(state, "notices"):
            print("  Notice deleted.")


# ---------------------------------------------------------------------------
# 10. LOGIN SCREENS AND MAIN MENUS
# ---------------------------------------------------------------------------
STUDENT_MENU = (("1", "View All Clubs"), ("2", "Search Clubs"), ("3", "Filter Clubs"),
                ("4", "Find My Club (Recommendation)"), ("5", "Compare Clubs"),
                ("6", "View Events"), ("7", "Notices"), ("8", "My Shortlist (login needed)"),
                ("9", "Statistics"), ("10", "Log out / back"))
STUDENT_ACTIONS = {"1": view_all_clubs, "2": search_menu, "3": filter_menu, "4": find_my_club,
                   "5": compare_menu, "6": view_events, "7": notices_menu, "8": shortlist_menu,
                   "9": statistics_menu}

LEADER_MENU = (("1", "View my club"), ("2", "Update my club details"), ("3", "View my events"),
               ("4", "Add an event"), ("5", "Edit an event"), ("6", "Delete an event"),
               ("7", "Post a notice"), ("8", "My notices (view / delete)"), ("9", "Log out"))
LEADER_ACTIONS = {"1": leader_view_club, "2": leader_update_club, "3": leader_list_events,
                  "4": leader_add_event, "5": leader_edit_event, "6": leader_delete_event,
                  "7": leader_post_notice, "8": leader_notices}


def run_menu(state, title, subtitle, options, actions):
    """Show a numbered menu repeatedly until the last option (log out) is chosen."""
    exit_key = options[-1][0]
    while True:
        print("\n" + "=" * 44)
        print(title.center(44))
        print(subtitle.center(44))
        print("=" * 44)
        for number, label in options:
            print(f"{number:>2}. {label}")
        print("=" * 44)
        choice = input("Enter your choice: ").strip()
        if choice == exit_key:
            return
        if choice not in actions:
            print(f"  Invalid choice. Please enter a number from 1 to {exit_key}.")
            continue
        actions[choice](state)


# def register_screen(state):
#     """Ask for the registration details. Returns the new student record or None if cancelled."""
#     print("\n--- Register (press Enter at the enrollment number to cancel) ---")
#     while True:
#         student_id = ask_text("Enrollment number: ")
#         if not student_id:
#             return None
#         name = ask_text("Full name: ")
#         password = input("Choose a password: ")
#         if input("Confirm password: ") != password:
#             print("  Passwords do not match. Please try again.")
#             continue
#         ok, message = register_student(state["students"], student_id, name, password)
#         print("  " + message)
#         if ok:
#             save_data(state, "students")
#             return find_student(state["students"], student_id)
    def register_screen(state):
    """Ask for registration details. Returns the new student record or None if cancelled."""

    print("\n--- Register (press Enter at the enrollment number to cancel) ---")

    while True:
        student_id = ask_text("Enrollment number: ")

        if not student_id:
            return None

        # Check whether enrollment number already exists
        if find_student(state["students"], student_id):
            print("  That enrollment number is already registered. Please log in.")
            continue

        name = ask_text("Full name: ")
        password = input("Choose a password: ")

        if input("Confirm password: ") != password:
            print("  Passwords do not match. Please try again.")
            continue

        ok, message = register_student(
            state["students"], student_id, name, password
        )

        print("  " + message)

        if ok:
            save_data(state, "students")
            return find_student(state["students"], student_id)




def student_access(state):
    """Guest / login / register screen. Returns a user dictionary, or None to go back."""
    while True:
        print("\n--- Student access ---")
        print("1. Continue as guest (browse only)\n2. Log in\n3. Register\n4. Back")
        choice = ask_int("Choose (1-4): ", 1, 4)
        if choice == 1:
            return {"role": "guest", "id": "", "name": "Guest"}
        if choice == 4:
            return None
        if choice == 2:
            print("(Tip: your password is your college email, e.g. S26CSEU0993@bennett.edu.in,")
            print(" unless you registered with a password of your own.)")
            student = login_loop("Enrollment number: ", "Password: ",
                                 lambda sid, pw: check_student_login(state["students"], sid, pw))
        else:
            student = register_screen(state)
        if student:
            user = {"role": "student", "id": student["student_id"], "name": student["name"]}
            fresh = new_notices(state["notices"], parse_datetime(student["last_seen"]), date.today())
            print(f"\nWelcome, {student['name']}! You have {len(fresh)} new notice(s)."
                  + (" Open 'Notices' to read them." if fresh else ""))
            return user


def student_session(state):
    user = student_access(state)
    if not user:
        return
    state["user"] = user
    show_reminders(state, date.today())
    subtitle = "Browsing as guest" if user["role"] == "guest" else f"Logged in: {user['id']}"
    run_menu(state, "CLUB SYNC - STUDENT", subtitle, STUDENT_MENU, STUDENT_ACTIONS)
    state["user"] = None


def leader_session(state):
    print("\n--- Club leader login ---")
    print("(Tip: the club password is the club name + @bennett.edu.in, for example")
    print(" geeksforgeeks@bennett.edu.in. Spaces and capital letters do not matter.)")
    leader = login_loop("Club ID (e.g. CB01): ", "Password: ",
                        lambda cid, pin: check_leader_login(state["leaders"], cid, pin))
    if not leader:
        return
    club = find_club(state["clubs"], leader["club_id"])
    state["user"] = {"role": "leader", "id": leader["club_id"], "name": leader["leader_name"],
                     "club_id": leader["club_id"]}
    today = date.today()
    upcoming = len([e for e in leader_events(state) if e["when"] >= today])
    live = len([n for n in state["notices"] if n["club_id"] == club["club_id"] and n["expires_on"] >= today])
    print(f"\nWelcome, {leader['leader_name']} ({club['name']}). "
          f"{upcoming} upcoming event(s), {live} active notice(s).")
    run_menu(state, "CLUB SYNC - CLUB LEADER", club["name"], LEADER_MENU, LEADER_ACTIONS)
    state["user"] = None


def main():
    state = load_state()
    try:
        while True:
            print("\n" + "=" * 44)
            print("CLUB SYNC - CAMPUS CLUB FINDER".center(44))
            print("=" * 44)
            print("1. Student (guest / login / register)\n2. Club leader login\n3. Exit")
            print("=" * 44)
            choice = input("Enter your choice: ").strip()
            if choice == "3":
                break
            if choice == "1":
                student_session(state)
            elif choice == "2":
                leader_session(state)
            else:
                print("  Invalid choice. Please enter 1, 2 or 3.")
    except (EOFError, KeyboardInterrupt):
        print()
    print("\nThank you for using Club SYNC. Goodbye!")


if __name__ == "__main__":
    main()
