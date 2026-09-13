"""
Authentication data seeder: scripts/auth/seed_users.py.

Creates auth_data/users.json with bcrypt-hashed passwords for the
5 demo accounts specified in the assignment. Run this once before starting
the FastAPI server:

    uv run python scripts/auth/seed_users.py

Re-running it is safe -- it always overwrites auth_data/users.json with fresh hashes
for the same 5 accounts. Do NOT treat auth_data/users.json's hashes as "secret" --
these are the assignment's own public demo credentials (documented in the
README per submission instructions), so hashing here is a best-practice
habit for production code, not a secrecy measure.

Uses the `bcrypt` library directly (not passlib) -- passlib is unmaintained
and has a known compatibility bug with bcrypt>=4.1 that raises a spurious
"password cannot be longer than 72 bytes" error even for short passwords.
"""
import json
import bcrypt

from medibot.core.config import USERS_PATH

# username -> (plaintext password, role)
# Matches the assignment's demo credentials exactly:
# username = person-style hint, password = the role name itself.
DEMO_ACCOUNTS = {
    "dr.mehta":     ("doctor",             "doctor"),
    "nurse.priya":  ("nurse",              "nurse"),
    "billing.ravi": ("billing_executive",  "billing_executive"),
    "tech.anand":   ("technician",         "technician"),
    "admin.sys":    ("admin",              "admin"),
}

users = []
for username, (password, role) in DEMO_ACCOUNTS.items():
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    users.append({
        "username": username,
        "password_hash": hashed.decode("utf-8"),
        "role": role,
    })

out_path = USERS_PATH
out_path.write_text(json.dumps(users, indent=2))

print(f"Wrote {len(users)} users to {out_path}")
for u in users:
    print(f"  {u['username']:15s} role={u['role']}")
