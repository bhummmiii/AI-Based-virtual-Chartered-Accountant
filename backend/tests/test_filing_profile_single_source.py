"""
Unit test suite for G1 (Y1): get_filing_profile single source of truth.
Validates:
- Case-insensitive normalization of return_frequency ("Monthly", "monthly", "Quarterly", "quarterly", "Q", "m")
- Null, empty, or unrecognized values return frequency None (NEVER defaults silently to Monthly)
- State code extraction from GSTIN (first 2 digits)
- Due date Category X (22nd) vs Category Y (24th) assignment
- State mismatch detection against statutory GST state map
- Multi-client isolation and compatibility with both ORM objects and dictionaries
"""

import pytest
from app.services.gst_filing_service import get_filing_profile, CATEGORY_X_STATES, GST_STATE_MAP


class MockClient:
    def __init__(self, return_frequency=None, gst_number=None, state=None):
        self.return_frequency = return_frequency
        self.gst_number = gst_number
        self.state = state


def test_filing_profile_monthly_variants():
    for variant in ["Monthly", "monthly", "MONTHLY", "m", "M", " monthly "]:
        client = MockClient(return_frequency=variant, gst_number="27AABCA1234A1Z5", state="Maharashtra")
        prof = get_filing_profile(client)
        assert prof["frequency"] == "monthly", f"Failed for variant {variant}"
        assert prof["state_code"] == "27"
        assert prof["due_category"] == "X"
        assert prof["state_mismatch"] is False


def test_filing_profile_quarterly_variants():
    for variant in ["Quarterly", "quarterly", "QUARTERLY", "q", "Q", " quarterly "]:
        client = MockClient(return_frequency=variant, gst_number="27AABCA1234A1Z5", state="Maharashtra")
        prof = get_filing_profile(client)
        assert prof["frequency"] == "quarterly", f"Failed for variant {variant}"
        assert prof["state_code"] == "27"
        assert prof["due_category"] == "X"
        assert prof["state_mismatch"] is False


def test_filing_profile_never_defaults_silently_to_monthly():
    invalid_or_null_values = [None, "", "   ", "company", "annual", "unknown", 123, "yearly"]
    for val in invalid_or_null_values:
        client = MockClient(return_frequency=val, gst_number="27AABCA1234A1Z5", state="Maharashtra")
        prof = get_filing_profile(client)
        assert prof["frequency"] is None, f"Expected None for invalid return_frequency {repr(val)}, got {prof['frequency']}"


def test_filing_profile_state_categories():
    # Category X states: 22, 23, 24, 25, 26, 27, 29, 30, 31, 32, 33, 34, 35, 36, 37
    # Category Y states: 01-21, 38, etc. (e.g. 07 Delhi)
    mh_client = MockClient(return_frequency="Quarterly", gst_number="27AABCA1234A1Z5", state="Maharashtra")
    dl_client = MockClient(return_frequency="Quarterly", gst_number="07AABCA1234A1Z5", state="Delhi")
    ka_client = MockClient(return_frequency="Quarterly", gst_number="29AABCA1234A1Z5", state="Karnataka")

    assert get_filing_profile(mh_client)["due_category"] == "X"
    assert get_filing_profile(ka_client)["due_category"] == "X"
    assert get_filing_profile(dl_client)["due_category"] == "Y"


def test_filing_profile_state_mismatch():
    # GSTIN 27 is Maharashtra, but state is Delhi
    mismatched = MockClient(return_frequency="Quarterly", gst_number="27AABCA1234A1Z5", state="Delhi")
    prof = get_filing_profile(mismatched)
    assert prof["state_mismatch"] is True

    # GSTIN 27 matches Maharashtra
    matched = MockClient(return_frequency="Quarterly", gst_number="27AABCA1234A1Z5", state="Maharashtra")
    assert get_filing_profile(matched)["state_mismatch"] is False


def test_filing_profile_dict_input():
    d = {
        "return_frequency": "Quarterly",
        "gst_number": "27AABCA1234A1Z5",
        "state": "Maharashtra",
    }
    prof = get_filing_profile(d)
    assert prof["frequency"] == "quarterly"
    assert prof["state_code"] == "27"
    assert prof["due_category"] == "X"
