from ttb_ride.state import TState
from ttb_ride.utils.debug import dbg
from ttb_ride.utils.text import thai_id_checksum_ok, mask_nid, relaxed_name_match
from ttb_ride.ocr.client import ocr_id_extract_path, ocr_income_extract_path

# will be set by app.main after engine.setup()
ENGINE = None

SYSTEM_PROMPT_REPEAT_INTENT = (
    "The user is trying to start another motorcycle loan in the same session after an approval already exists.\n"
    "Politely ask what changed (bike, income, corrections). Offer to start a new application if they confirm."
)

def set_engine(engine):
    global ENGINE
    ENGINE = engine


def reset_application_for_reapply(state: TState, announce: bool = True) -> None:
    state["docs"] = {"bike": {"ok": False}, "income": {"ok": False}, "id": {"ok": False}}
    state["decision"] = {}
    state["ui"]["need"] = {"bike": True, "income": True, "id": True}
    state["ui"]["show_uploads"] = True
    state["ui"]["show_satisfaction"] = False
    state["flags"]["docs_complete_announced"] = False
    state["flags"]["user_triggered_appraise"] = False
    state["flags"]["reapply_ready"] = False
    state["flags"]["approved_once"] = False
    state["flags"]["last_feedback"] = ""
    if announce:
        tagline = (
            "เริ่มคำขอใหม่ได้เลยครับ/ค่ะ\n"
            "โปรดอัปโหลดเอกสาร 3 รายการ: ① รูปมอเตอร์ไซค์ ② สลิปเงินเดือน ③ บัตรประจำตัวประชาชน"
        )
        state["messages"].append(("assistant", tagline))
    dbg(state, "reset_application_for_reapply")


def router_intent(state: TState) -> TState:
    latest_user_idx, latest_user_text = None, ""
    for idx in range(len(state["messages"]) - 1, -1, -1):
        role, text = state["messages"][idx]
        if role == "user":
            latest_user_idx, latest_user_text = idx, text
            break
    if latest_user_idx is None:
        dbg(state, "router_no_user"); return state

    last_seen = state.get("cursors", {}).get("last_user_pos_handled", -1)
    if latest_user_idx == last_seen:
        dbg(state, "intent_skip", reason="no_new_user_message"); return state

    out = ENGINE.intent_gate(latest_user_text).dict()
    state["intent"].update(out)
    dbg(state, "intent_gate", intent=out["motorcycle_loan_intent"], confidence=out["confidence"], rationale=out.get("rationale", "")[:160])

    if out["motorcycle_loan_intent"] and state.get("flags", {}).get("approved_once", False):
        if state["flags"].get("reapply_ready", False) or state["flags"].get("last_feedback") == "unhappy":
            reset_application_for_reapply(state, announce=True)
            state.setdefault("cursors", {})["last_user_pos_handled"] = latest_user_idx
            return state
        else:
            reply = ENGINE.contextual_chat(state, SYSTEM_PROMPT_REPEAT_INTENT)
            state["messages"].append(("assistant", reply))
            state["ui"]["show_uploads"] = False
            state.setdefault("cursors", {})["last_user_pos_handled"] = latest_user_idx
            dbg(state, "repeat_intent_guard")
            return state

    if out["motorcycle_loan_intent"]:
        if not state["ui"]["show_uploads"]:
            state["ui"]["show_uploads"] = True
            tagline = (
                "นี่คือบริการ “เมื่อคุณขอ คุณพร้อมจ่าย เราพร้อมให้”\n"
                "โปรดอัปโหลดเอกสาร 3 รายการ:\n ① รูปมอเตอร์ไซค์\n ② รูปเอกสารรายได้ (สลิปเงินเดือน)\n ③ รูปบัตรประจำตัวประชาชน (ถ่ายรูปจากหน้าบัตร)\n"
                "ทางเราจะประเมินวงเงินให้ครับ/ค่ะ"
            )
            state["messages"].append(("assistant", tagline))

    state.setdefault("cursors", {})["last_user_pos_handled"] = latest_user_idx
    return state


def general_chat(state: TState) -> TState:
    if not any(role == "user" for role, _ in state.get("messages", [])):
        dbg(state, "chat_skip", reason="no_user_text"); return state
    reply = ENGINE.contextual_chat(state)
    state["messages"].append(("assistant", reply))
    dbg(state, "general_chat_reply", tokens=len(reply or ""))
    return state


def agent2_docops(state: TState) -> TState:
    bike = state["docs"]["bike"]
    if bike.get("path") and not bike.get("ok"):
        parsed = ENGINE.vlm_is_motorcycle_from_path(bike["path"]).dict()
        bike["is_motorcycle"] = parsed["is_motorcycle"]
        bike["vlm_check_conf"] = parsed["confidence"]
        bike["ok"] = bool(parsed["is_motorcycle"])
        dbg(state, "bike_check", is_motorcycle=bike["is_motorcycle"], confidence=bike["vlm_check_conf"])
        if not bike["ok"]:
            state["messages"].append(("assistant", f"รูปภาพไม่ใช่มอเตอร์ไซค์ (conf {parsed['confidence']:.2f}). โปรดอัปโหลดใหม่"))

    idd = state["docs"]["id"]
    if idd.get("path") is not None and not idd.get("ok"):
        data = ocr_id_extract_path(idd["path"])
        idd["parsed"] = data.get("parsed", {})
        idd["nid"] = idd["parsed"].get("National Identification Number", "")
        idd["person_name"] = idd["parsed"].get("First and Last Name", "")
        idd["checksum_valid"] = thai_id_checksum_ok(idd["nid"])
        idd["ok"] = bool(idd["person_name"]) and bool(idd["nid"]) and bool(idd["checksum_valid"])
        dbg(state, "id_ocr", name=idd["person_name"], nid_masked=mask_nid(idd["nid"]), checksum=idd["checksum_valid"], ok=idd["ok"])
        if not idd["ok"]:
            nid_txt = mask_nid(idd.get("nid", ""))
            state["messages"].append(("assistant", f"ข้อมูลบัตรประชาชนไม่ครบหรือเลขไม่ถูกต้อง (เลข: {nid_txt}). โปรดอัปโหลดใหม่"))

    inc = state["docs"]["income"]
    if inc.get("path") is not None and not inc.get("ok"):
        data = ocr_income_extract_path(inc["path"])
        inc["raw"] = data
        inc["parsed"] = data.get("parsed", {})
        inc["normalized"] = data.get("normalized", {})
        inc["monthly_income_thb"] = inc["normalized"].get("monthly_income_thb")
        holder_name = inc["normalized"].get("holder_name") or inc["parsed"].get("holder_name") or inc["parsed"].get("name")
        dbg(state, "income_ocr", holder_name=holder_name, monthly_income_thb=inc["monthly_income_thb"])
        inc["ok"] = isinstance(inc["monthly_income_thb"], int)
        if not inc["ok"]:
            state["messages"].append(("assistant", "ไม่พบรายได้ต่อเดือนจากเอกสาร โปรดอัปโหลดใหม่"))

    state["ui"]["need"]["bike"] = not state["docs"]["bike"]["ok"]
    state["ui"]["need"]["income"] = not state["docs"]["income"]["ok"]
    state["ui"]["need"]["id"] = not state["docs"]["id"]["ok"]
    dbg(state, "docs_status", need_bike=state["ui"]["need"]["bike"], need_income=state["ui"]["need"]["income"], need_id=state["ui"]["need"]["id"])

    if all([state["docs"]["bike"]["ok"], state["docs"]["income"]["ok"], state["docs"]["id"]["ok"]]):
        if not state["flags"]["docs_complete_announced"]:
            state["messages"].append(("assistant", "✅ เอกสารครบถ้วน กำลังประเมินวงเงิน..."))
            state["flags"]["docs_complete_announced"] = True
        state["flags"]["user_triggered_appraise"] = True
        dbg(state, "ready_for_appraisal", trigger=True)
    return state


def agent3_appraisal(state: TState) -> TState:
    if not state.get("flags", {}).get("user_triggered_appraise", False):
        dbg(state, "appraise_skipped", reason="flag_false"); return state
    state["flags"]["user_triggered_appraise"] = False

    if not all([state["docs"]["bike"].get("ok"), state["docs"]["income"].get("ok"), state["docs"]["id"].get("ok")]):
        state["messages"].append(("assistant", "เอกสารยังไม่ครบถ้วน โปรดอัปโหลดให้ครบก่อนนะครับ/ค่ะ"))
        dbg(state, "appraise_blocked", reason="docs_incomplete")
        return state

    bike = state["docs"]["bike"]; inc = state["docs"]["income"]; idd = state["docs"]["id"]

    holder = (inc.get("normalized", {}) or {}).get("holder_name") \
             or inc.get("parsed", {}).get("holder_name") \
             or inc.get("parsed", {}).get("name") or ""
    nam = idd.get("person_name") or ""
    same, score, breakdown = relaxed_name_match(holder, nam, threshold=0.50)
    state["decision"]["same_person"] = same
    state["decision"]["name_match_score"] = score
    dbg(state, "name_match", id_name=nam, income_name=holder, score=score, same_person=same, **breakdown)
    if not same:
        state["messages"].append(("assistant", "ชื่อในเอกสารรายได้และบัตรประชาชนดูเหมือนไม่ตรงกัน (สาธิต: ใช้เกณฑ์ง่าย) โปรดตรวจสอบหรืออัปโหลดใหม่"))
        return state

    appr = ENGINE.vlm_appraise_from_path(bike["path"]).dict()
    bike["appraised_value_thb"] = appr["appraised_value_thb"]
    bike["appraisal_conf"] = appr["confidence"]
    bike["appraisal_notes"] = appr["notes"]
    dbg(state, "appraisal_vlm", appraised_value_thb=bike["appraised_value_thb"], confidence=bike["appraisal_conf"], notes=bike["appraisal_notes"][:160])

    income = inc["monthly_income_thb"] or 0
    cap_income = int(0.5 * income)
    cap_bike = int(bike["appraised_value_thb"] or 0)
    approved = min(cap_income, cap_bike)
    state["decision"]["approved_amount_thb"] = approved
    state["decision"]["reason"] = f"min(0.5×รายได้ต่อเดือน={cap_income:,}, มูลค่ารถ={cap_bike:,}) → {approved:,} THB"

    dbg(state, "approval_math", monthly_income_thb=income, cap_income_50pct=cap_income, appraised_value_thb=cap_bike, approved_amount_thb=approved)

    msg = (f"วงเงินที่อนุมัติ: **{approved:,} THB**\n\n" f"_เหตุผล:_ {state['decision']['reason']}\n" f"(ความมั่นใจในการประเมินรูป: {bike['appraisal_conf']:.2f})")
    state["messages"].append(("assistant", msg))

    state["ui"]["show_uploads"] = False
    state["ui"]["show_satisfaction"] = True
    state["flags"]["approved_once"] = True
    return state


def feedback_extra_system(state: TState, kind: str) -> str:
    inc = state["docs"]["income"]; bike = state["docs"]["bike"]
    income = int(inc.get("monthly_income_thb") or 0)
    cap_income = int(0.5 * income)
    cap_bike = int(bike.get("appraised_value_thb") or 0)
    approved = int(state.get("decision", {}).get("approved_amount_thb") or 0)
    limiting = "income" if cap_income <= cap_bike else "bike"

    base = [
        "You are TTB Ride, a Thai motorcycle-loan assistant.",
        "Keep replies concise (2–4 short sentences), friendly, and non-binding.",
        "Policy math: approved ≤ min(50% of monthly income, appraised bike value).",
        f"Context: approved={approved:,} THB, monthly_income={income:,} THB, income_cap(50%)={cap_income:,} THB, bike_appraisal={cap_bike:,} THB, limiting_factor={limiting}.",
        "Write in Thai."
    ]
    if kind == "happy":
        base += [
            "The user clicked a 'Happy' button.",
            "Congratulate briefly and summarize next steps (identity verification, contract signing).",
            "Optionally invite questions (payout timing, repayment).",
            "Do NOT promise outcomes beyond the shown approval."
        ]
    else:
        base += [
            "The user clicked an 'Unhappy' button.",
            "Be empathetic. Ask what loan amount they hoped to get.",
            "Explain succinctly which factor likely limited the amount (income or bike value).",
            "Offer actionable next steps: newer income proof if higher, increase income, or use a higher-value bike.",
            "Explain the rule transparently: for target amount X, monthly income should be at least ~2×X (and still ≤ bike value)."
        ]
    return "\n".join(base)


def route_after_router(state: TState) -> str:
    last_seen = state.get("cursors", {}).get("last_user_pos_handled", -1)
    if last_seen < 0:
        return "END"
    if state.get("intent", {}).get("motorcycle_loan_intent") and not state.get("flags", {}).get("approved_once", False):
        return "docops"
    return "chat"

def route_after_docops(state: TState) -> str:
    ready = all([
        state["docs"]["bike"].get("ok"),
        state["docs"]["income"].get("ok"),
        state["docs"]["id"].get("ok"),
    ])
    if ready and state.get("flags", {}).get("user_triggered_appraise", False):
        return "appraise"
    return "END"
