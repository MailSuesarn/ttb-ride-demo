import os
import re
import io
import json
import modal
from modal import App, Volume, Image

# =========================
# App / Image
# =========================
app = modal.App("olmocr-service-ttb-ride")

image = (
    Image.debian_slim()
    .pip_install(
        # Hugging Face + Transformers stack
        "huggingface_hub",
        "transformers>=4.43.0",
        "accelerate>=0.32.0",
        "bitsandbytes>=0.43.0",
        "peft>=0.11.0",
        # Torch + Torchvision + PIL
        "torch",
        "torchvision",
        "Pillow",
    )
    .env({"HF_HUB_CACHE": "/cache"})
)

# Secret for Hugging Face downloads (adjust to your workspace)
secrets = [modal.Secret.from_name("hf-secret")]

# =========================
# Constants / Config
# =========================
GPU = os.getenv("OLMOCR_GPU", "T4")
MODEL_ID = os.getenv("OLMOCR_MODEL", "allenai/olmOCR-7B-0725")
ADAPTER_REPO = os.getenv("OLMOCR_ADAPTER_REPO", "")  # optional PEFT adapter repo
REVISION = os.getenv("OLMOCR_ADAPTER_REVISION", None)  # optional adapter revision

CACHE_DIR = "/cache"
MIN_CONTAINERS = int(os.getenv("OLMOCR_MIN_CONTAINERS", "0"))

MAX_MAX_NEW_TOKENS = int(os.getenv("MAX_MAX_NEW_TOKENS", 2048))
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("DEFAULT_MAX_NEW_TOKENS", 1024))
MAX_INPUT_TOKEN_LENGTH = int(os.getenv("MAX_INPUT_TOKEN_LENGTH", 4096))

# -------------------------
# Document-specific prompts
# -------------------------
# ID CARD (Thai National ID) — keys aligned with your earlier example
ID_SYSTEM_PROMPT = """
You are an OCR assistant that extracts Thai National ID card fields and returns ONLY valid JSON.
Use the EXACT keys and keep the language as-is (do not translate):
{
  "National Identification Number": "13-digit ID with spaces if present",
  "First and Last Name": "e.g., Thai name string",
  "Date of Birth": "e.g., 22 March 1957",
  "Address": "Thai address string",
  "Date of Issue": "e.g., 26 July 2016",
  "Date of Expiry": "e.g., 21 March 2025"
}
No extra commentary. No markdown. Return only a single JSON object.
"""

ID_USER_INSTRUCTION = """
Perform OCR on the attached Thai National ID card and output ONLY the JSON with the keys shown.
Ensure you keep spacing/delimiters as seen on the card (e.g., the 13-digit ID can include spaces).
Return only that JSON object.
"""

# INCOME DOCUMENT (Payslip / income proof) — numeric-friendly schema
INCOME_SYSTEM_PROMPT = """
You are an OCR assistant that extracts income details from a Thai payslip or income proof and returns ONLY valid JSON.
Use the EXACT keys below. Convert Thai numerals to Arabic numerals. Extract an integer for monthly income in THB.
{
  "holder_name": "Full name if present, else empty string",
  "monthly_income_thb": 12000,
  "employer": "Company name/Source if present, else empty string",
  "period": "YYYY-MM if present, else empty string"
}
Rules:
- monthly_income_thb must be a number (no commas/THB text).
- If amounts appear per period (weekly/biweekly), still output monthly income estimate if clearly stated as monthly. If not clear, choose the most prominent monthly figure on the doc.
- Prefer the explicit 'monthly' amount if multiple figures exist.
No extra commentary. No markdown. Return only a single JSON object.
"""

INCOME_USER_INSTRUCTION = """
Perform OCR on the attached payslip/income proof and output ONLY the JSON with the keys shown.
- Ensure "monthly_income_thb" is an integer (Arabic numerals), no commas, no currency text.
- If month/period is visible, normalize to YYYY-MM format.
Return only that JSON object.
"""

PROMPTS = {
    "id_card": (ID_SYSTEM_PROMPT, ID_USER_INSTRUCTION),
    "income": (INCOME_SYSTEM_PROMPT, INCOME_USER_INSTRUCTION),
}

hf_cache_volume = Volume.from_name("hf-hub-cache", create_if_missing=True)

# =========================
# Helpers
# =========================
JSON_FENCE = re.compile(r"\{[\s\S]*\}")

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

def extract_json(text: str):
    text = (text or "").strip()
    # Try direct JSON first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fenced JSON fallback
    m = JSON_FENCE.search(text)
    if not m:
        return None
    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        return None

_amount_pat = re.compile(r"([0-9๐-๙][0-9,๐-๙\.]*)\s*(?:THB|บาท|฿)?", re.IGNORECASE)

def _to_arabic_digits(s: str) -> str:
    return (s or "").translate(THAI_DIGITS)

def _parse_int_amount(s: str) -> int | None:
    """Parse an integer amount from a string; tolerant of commas, Thai digits, and decimals."""
    if not s:
        return None
    s = _to_arabic_digits(s)
    s = s.replace(",", "")
    # If decimal exists, drop fractional for integer monthly income
    try:
        return int(float(s))
    except Exception:
        return None

def normalize_income(parsed: dict | None, raw_text: str) -> dict:
    """
    Ensures a sturdy structure for income results:
    - monthly_income_thb as integer if possible
    - basic fallback extraction from raw_text if model returned strings
    """
    parsed = parsed.copy() if isinstance(parsed, dict) else {}
    # Holder
    holder = parsed.get("holder_name") or ""
    employer = parsed.get("employer") or ""
    period = parsed.get("period") or ""

    # Income normalization
    income = parsed.get("monthly_income_thb")
    if isinstance(income, str):
        income = _parse_int_amount(income)

    if not isinstance(income, int):
        # try to fish from raw text
        for m in _amount_pat.finditer(raw_text or ""):
            cand = _parse_int_amount(m.group(1))
            if cand and cand > 0:
                # pick the first reasonable positive number
                income = cand
                break

    out = {
        "holder_name": holder,
        "monthly_income_thb": income if isinstance(income, int) else None,
        "employer": employer,
        "period": period,
    }
    return out

# =========================
# Remote Class
# =========================
@app.cls(
    image=image,
    secrets=secrets,
    gpu=GPU,
    timeout=1800,
    min_containers=MIN_CONTAINERS,
    volumes={CACHE_DIR: hf_cache_volume},
)
class OlmOCR:
    """
    Modal-deployed OCR service using allenai/olmOCR-7B-0725 (Qwen2.5-VL family).
    Supports document-specific prompts via:
      - ocr_id(...) for Thai National ID cards
      - ocr_income(...) for payslips/income docs
      - ocr(..., doc_type="id_card"|"income") for a single generic route
    """

    @modal.enter()
    def setup(self):
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig
        from peft import PeftModel

        # Processor
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)

        # Quantization
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_quant_type="nf4",
        )

        # Load model (quantized if possible; fallback to fp16/fp32)
        try:
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                MODEL_ID,
                trust_remote_code=True,
                quantization_config=quant_config,
                device_map="auto",
                low_cpu_mem_usage=True,
            )
        except Exception:
            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                MODEL_ID,
                trust_remote_code=True,
                torch_dtype=torch_dtype,
                device_map="auto",
                low_cpu_mem_usage=True,
            )

        # Optional adapter
        if ADAPTER_REPO:
            self.model = PeftModel.from_pretrained(self.model, ADAPTER_REPO, revision=REVISION)

        self.model.eval()

    # ---------------
    # Core run method
    # ---------------
    def _run_generation(
        self,
        image_bytes: bytes,
        system_prompt: str,
        user_instruction: str,
        max_new_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
        repetition_penalty: float,
    ) -> tuple[str, dict | None]:
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        messages = [
            {"role": "system", "content": [{"type": "text", "text": system_prompt.strip()}]},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": user_instruction.strip()},
                ],
            },
        ]

        prompt = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.processor(
            text=[prompt],
            images=[img],
            return_tensors="pt",
            padding=True,
            truncation=False,
            max_length=MAX_INPUT_TOKEN_LENGTH,
        )

        device = next(self.model.parameters()).device
        inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=int(max_new_tokens),
                do_sample=True,
                temperature=float(temperature),
                top_p=float(top_p),
                top_k=int(top_k),
                repetition_penalty=float(repetition_penalty),
            )

        input_len = inputs["input_ids"].shape[1]
        gen_ids = output_ids[0, input_len:]

        tokenizer = getattr(self.processor, "tokenizer", None) or self.processor
        raw_text = tokenizer.decode(gen_ids, skip_special_tokens=True)
        parsed = extract_json(raw_text)
        return raw_text, parsed

    # ----------------------------
    # Backwards-compatible generic
    # ----------------------------
    @modal.method()
    def ocr(
        self,
        image_bytes: bytes,
        instruction: str = "",
        doc_type: str = None,  # "id_card" | "income" | None
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = 0.2,
        top_p: float = 0.9,
        top_k: int = 50,
        repetition_penalty: float = 1.1,
    ) -> dict:
        """
        Generic OCR entrypoint.
        - If instruction is provided, it takes precedence (legacy behavior).
        - Else if doc_type in {"id_card","income"}, use the corresponding prompts.
        - Else fall back to ID card prompts for compatibility with older clients.
        Returns: {"doc_type", "raw", "parsed", "normalized"?}
        """
        if instruction:
            # Manual override path
            sys_prompt = "You are an OCR assistant. Return ONLY valid JSON for the user's request."
            user_instruction = instruction
            raw, parsed = self._run_generation(
                image_bytes, sys_prompt, user_instruction,
                max_new_tokens, temperature, top_p, top_k, repetition_penalty
            )
            return {"doc_type": doc_type or "custom", "raw": raw, "parsed": parsed}

        # Automatic by doc_type
        kind = (doc_type or "id_card").strip().lower()
        if kind not in PROMPTS:
            kind = "id_card"  # safe default

        sys_prompt, user_instruction = PROMPTS[kind]
        raw, parsed = self._run_generation(
            image_bytes, sys_prompt, user_instruction,
            max_new_tokens, temperature, top_p, top_k, repetition_penalty
        )

        out = {"doc_type": kind, "raw": raw, "parsed": parsed}
        if kind == "income":
            out["normalized"] = normalize_income(parsed, raw)
        return out

    # ----------------------------
    # Dedicated ID route
    # ----------------------------
    @modal.method()
    def ocr_id(
        self,
        image_bytes: bytes,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = 0.2,
        top_p: float = 0.9,
        top_k: int = 50,
        repetition_penalty: float = 1.1,
    ) -> dict:
        """
        Thai National ID card OCR → fixed JSON keys.
        Returns: { "doc_type": "id_card", "raw", "parsed" }
        """
        raw, parsed = self._run_generation(
            image_bytes, ID_SYSTEM_PROMPT, ID_USER_INSTRUCTION,
            max_new_tokens, temperature, top_p, top_k, repetition_penalty
        )
        return {"doc_type": "id_card", "raw": raw, "parsed": parsed}

    # ----------------------------
    # Dedicated Income route
    # ----------------------------
    @modal.method()
    def ocr_income(
        self,
        image_bytes: bytes,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = 0.2,
        top_p: float = 0.9,
        top_k: int = 50,
        repetition_penalty: float = 1.1,
    ) -> dict:
        """
        Income proof / payslip OCR → numeric-friendly schema.
        Returns: { "doc_type": "income", "raw", "parsed", "normalized" }
        """
        raw, parsed = self._run_generation(
            image_bytes, INCOME_SYSTEM_PROMPT, INCOME_USER_INSTRUCTION,
            max_new_tokens, temperature, top_p, top_k, repetition_penalty
        )
        return {
            "doc_type": "income",
            "raw": raw,
            "parsed": parsed,
            "normalized": normalize_income(parsed, raw),
        }
