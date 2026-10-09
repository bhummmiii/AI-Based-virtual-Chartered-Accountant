"""
GST Filing Service — Single Source of Truth for Filing Profile, Period Calculations,
and Statutory Due Dates.
"""

from typing import Optional, Dict, Any
import re

CATEGORY_X_STATES = {
    "22", "23", "24", "25", "26", "27", "29", "30",
    "31", "32", "33", "34", "35", "36", "37"
}

GST_STATE_MAP = {
    "01": "JAMMU AND KASHMIR",
    "02": "HIMACHAL PRADESH",
    "03": "PUNJAB",
    "04": "CHANDIGARH",
    "05": "UTTARAKHAND",
    "06": "HARYANA",
    "07": "DELHI",
    "08": "RAJASTHAN",
    "09": "UTTAR PRADESH",
    "10": "BIHAR",
    "11": "SIKKIM",
    "12": "ARUNACHAL PRADESH",
    "13": "NAGALAND",
    "14": "MANIPUR",
    "15": "MIZORAM",
    "16": "TRIPURA",
    "17": "MEGHALAYA",
    "18": "ASSAM",
    "19": "WEST BENGAL",
    "20": "JHARKHAND",
    "21": "ODISHA",
    "22": "CHHATTISGARH",
    "23": "MADHYA PRADESH",
    "24": "GUJARAT",
    "25": "DAMAN AND DIU",
    "26": "DADRA AND NAGAR HAVELI",
    "27": "MAHARASHTRA",
    "29": "KARNATAKA",
    "30": "GOA",
    "31": "LAKSHADWEEP",
    "32": "KERALA",
    "33": "TAMIL NADU",
    "34": "PUDUCHERRY",
    "35": "ANDAMAN AND NICOBAR ISLANDS",
    "36": "TELANGANA",
    "37": "ANDHRA PRADESH",
    "38": "LADAKH",
    "97": "OTHER TERRITORY",
}


def get_filing_profile(client: Any) -> Dict[str, Any]:
    """Single source of truth for client's GST filing profile.

    Normalises return_frequency case-insensitively:
      'Monthly', 'monthly', 'm' -> 'monthly'
      'Quarterly', 'quarterly', 'q' -> 'quarterly'
      Anything else, unrecognized, or null -> None (NEVER defaults silently).

    Returns:
      frequency: 'monthly' | 'quarterly' | None
      state_code: first two digits of client's GSTIN (e.g. '27')
      due_category: 'X' | 'Y' (Category X: 22nd, Category Y: 24th for quarterly)
      state_mismatch: bool (True if GSTIN state contradicts stored state)
      stored_frequency: original raw value
      state_name: official statutory state name
    """
    raw_freq = getattr(client, "return_frequency", None)
    if raw_freq is None and isinstance(client, dict):
        raw_freq = client.get("return_frequency")

    # Case-insensitive normalization
    freq: Optional[str] = None
    if raw_freq is not None:
        norm = str(raw_freq).strip().lower()
        if norm in ("monthly", "m"):
            freq = "monthly"
        elif norm in ("quarterly", "q"):
            freq = "quarterly"
        # Anything else (e.g., 'company', '', None) evaluates strictly to None

    # GSTIN extraction
    gstin = getattr(client, "gst_number", None)
    if gstin is None and isinstance(client, dict):
        gstin = client.get("gst_number") or client.get("gstin")
    gstin_str = str(gstin or "").strip().upper()

    state_code: Optional[str] = None
    if len(gstin_str) >= 2 and gstin_str[:2].isdigit():
        state_code = gstin_str[:2]

    # Due category: X (22nd) or Y (24th)
    due_category = "X" if (state_code and state_code in CATEGORY_X_STATES) else "Y"

    # State mismatch check
    stored_state = getattr(client, "state", None)
    if stored_state is None and isinstance(client, dict):
        stored_state = client.get("state")

    state_mismatch = False
    if state_code and stored_state and state_code in GST_STATE_MAP:
        expected = GST_STATE_MAP[state_code].lower()
        st_clean = re.sub(r"[^a-z0-9]", "", str(stored_state).lower())
        exp_clean = re.sub(r"[^a-z0-9]", "", expected)
        if st_clean not in exp_clean and exp_clean not in st_clean:
            state_mismatch = True

    return {
        "frequency": freq,
        "state_code": state_code,
        "due_category": due_category,
        "state_mismatch": state_mismatch,
        "stored_frequency": raw_freq,
        "state_name": GST_STATE_MAP.get(state_code) if state_code else None,
    }
