from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from ttb_ride.config import MODEL_TEXT, MODEL_VLM
from ttb_ride.schemas import IntentOut, IsMotorcycleOut, AppraisalOut
from ttb_ride.utils.text import sanitize_for_llm
from ttb_ride.utils.images import pil_to_jpeg_data_url
from PIL import Image

SYSTEM_PROMPT_CORE = (
    "You are TTB Ride, a banking assistant for motorcycle loans in Thailand.\n"
    "Respond in Thai if the user writes Thai; otherwise, use English.\n"
    "You can chat generally, but your primary job is guiding users through motorcycle loan steps.\n"
    "Always consider session state (uploads, OCR results, appraisal, approval).\n"
    "Be concise, friendly, and non-binding."
)

class TtbRideEngine:
    def __init__(self):
        self.llm = None
        self.llm_struct_intent = None
        self.vlm = None
        self.vlm_struct_is_moto = None
        self.vlm_struct_appraise = None

    def setup(self):
        llm = ChatOpenAI(model=MODEL_TEXT, temperature=0)
        self.llm = llm
        self.llm_struct_intent = llm.with_structured_output(IntentOut)

        vlm = ChatOpenAI(model=MODEL_VLM, temperature=0)
        self.vlm = vlm
        self.vlm_struct_is_moto = vlm.with_structured_output(IsMotorcycleOut)
        self.vlm_struct_appraise = vlm.with_structured_output(AppraisalOut)
        global ENGINE
        ENGINE = self
        return self

    # ---- classifiers / VLM helpers ----
    def intent_gate(self, user_text: str) -> IntentOut:
        system = (
            "Classify if the user intends to APPLY for a motorcycle LOAN. "
            "Consider Thai/English phrasing; avoid keyword matching. Return JSON only."
        )
        out: IntentOut = self.llm_struct_intent.invoke([
            SystemMessage(content=system),
            HumanMessage(content=user_text),
        ])
        return out

    def vlm_is_motorcycle_from_path(self, path: str) -> IsMotorcycleOut:
        img = Image.open(path).convert("RGB")
        prompt = (
            "Verify whether the image shows a motorcycle (scooters/mopeds count). "
            "If ambiguous, set is_motorcycle=false. Return JSON only."
        )
        out: IsMotorcycleOut = self.vlm_struct_is_moto.invoke([
            HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": pil_to_jpeg_data_url(img)}},
            ])
        ])
        return out

    def vlm_appraise_from_path(self, path: str) -> AppraisalOut:
        img = Image.open(path).convert("RGB")
        prompt = (
            "You are a Thai motorcycle appraiser. From the image ONLY (no extra info), "
            "estimate a fair market value in THB for a used bike in normal condition. "
            "If uncertain, give a conservative estimate and lower confidence. Return JSON only."
        )
        out: AppraisalOut = self.vlm_struct_appraise.invoke([
            HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": pil_to_jpeg_data_url(img)}},
            ])
        ])
        return out

    def contextual_chat(self, state: "dict", extra_system: str = "") -> str:
        sys = SYSTEM_PROMPT_CORE + ("\n" + extra_system if extra_system else "")
        # compact history
        msgs = state.get("messages", [])[-12:]
        lc_msgs = [SystemMessage(content=sys)]
        total = 0
        for role, text in msgs:
            s = sanitize_for_llm(text or "")
            if not s:
                continue
            if total + len(s) > 12000:
                s = s[: max(0, 12000 - total)]
            lc_msgs.append(HumanMessage(content=s) if role == "user" else AIMessage(content=s))
            total += len(s)
            if total >= 12000:
                break
        resp = self.llm.invoke(lc_msgs)
        return resp.content or ""


# global handle for simple injection into agents
ENGINE: TtbRideEngine | None = None
