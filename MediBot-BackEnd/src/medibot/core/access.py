"""Shared RBAC rules: src/medibot/core/access.py."""

COLLECTION_ACCESS_ROLES = {
    "general": ["doctor", "nurse", "billing_executive", "technician", "admin"],
    "clinical": ["doctor", "admin"],
    "nursing": ["nurse", "doctor", "admin"],
    "billing": ["billing_executive", "admin"],
    "equipment": ["technician", "admin"],
}

ALL_ROLES = ["doctor", "nurse", "billing_executive", "technician", "admin"]
