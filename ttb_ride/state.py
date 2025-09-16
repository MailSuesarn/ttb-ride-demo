from typing_extensions import TypedDict, NotRequired
from typing import Dict, Any, List

class DocSlot(TypedDict, total=False):
    path: NotRequired[str]
    ok: bool
    # Bike
    is_motorcycle: NotRequired[bool]
    vlm_check_conf: NotRequired[float]
    appraised_value_thb: NotRequired[int]
    appraisal_conf: NotRequired[float]
    appraisal_notes: NotRequired[str]
    # Income
    raw: NotRequired[Dict[str, Any]]
    parsed: NotRequired[Dict[str, Any]]
    normalized: NotRequired[Dict[str, Any]]
    monthly_income_thb: NotRequired[int]
    # ID
    person_name: NotRequired[str]
    nid: NotRequired[str]
    checksum_valid: NotRequired[bool]

class UIFlags(TypedDict):
    show_uploads: bool
    show_satisfaction: bool
    need: Dict[str, bool]

class Decision(TypedDict, total=False):
    same_person: bool
    name_match_score: float
    approved_amount_thb: int
    reason: str

class IntentState(TypedDict, total=False):
    motorcycle_loan_intent: bool
    confidence: float
    rationale: str

class TState(TypedDict, total=False):
    messages: list
    ui: UIFlags
    docs: Dict[str, DocSlot]
    decision: Decision
    intent: IntentState
    flags: Dict[str, bool]
    debug_logs: List[str]
    cursors: Dict[str, int]

def new_state() -> TState:
    return {
        "messages": [],
        "ui": {"show_uploads": False,
               "show_satisfaction": False,
               "need": {"bike": True, "income": True, "id": True}},
        "docs": {"bike": {"ok": False}, "income": {"ok": False}, "id": {"ok": False}},
        "decision": {},
        "intent": {"motorcycle_loan_intent": False, "confidence": 0.0, "rationale": ""},
        "flags": {"user_triggered_appraise": False,
                  "docs_complete_announced": False,
                  "approved_once": False,
                  "reapply_ready": False,
                  "last_feedback": ""},
        "debug_logs": [],
        "cursors": {"last_user_pos_handled": -1},
    }
