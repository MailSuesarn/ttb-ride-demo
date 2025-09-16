import modal
from typing import Optional, Dict, Any

class OlmOCRClient:
    """
    Client for the Modal-deployed OlmOCR service.
    - Supports document-specific routing via `doc_type` ("id_card" | "income") on .ocr()
    - Adds explicit helpers: .ocr_id() and .ocr_income()
    """

    def __init__(self):
        OCR = modal.Cls.from_name("olmocr-service-ttb-ride", "OlmOCR")
        self.ocr_remote = OCR()

    def ocr(
        self,
        image_path: str,
        instruction: str = "",
        doc_type: Optional[str] = None,  # NEW
        **gen_kwargs: Any,               # optional generation args passthrough
    ) -> Dict[str, Any]:
        """
        Generic OCR: choose behavior by doc_type ("id_card" | "income") or custom instruction.
        If both `instruction` and `doc_type` are provided, `instruction` takes precedence (service behavior).
        """
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Call Modal method using keyword args to avoid positional mismatches
        result = self.ocr_remote.ocr.remote(
            image_bytes=image_bytes,
            instruction=instruction,
            doc_type=doc_type,
            **gen_kwargs,  # e.g., max_new_tokens=..., temperature=...
        )
        return result

    # Convenience wrappers for the dedicated routes you exposed on the service
    def ocr_id(self, image_path: str, **gen_kwargs: Any) -> Dict[str, Any]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return self.ocr_remote.ocr_id.remote(
            image_bytes=image_bytes,
            **gen_kwargs
        )

    def ocr_income(self, image_path: str, **gen_kwargs: Any) -> Dict[str, Any]:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return self.ocr_remote.ocr_income.remote(
            image_bytes=image_bytes,
            **gen_kwargs
        )


if __name__ == "__main__":
    client = OlmOCRClient()

    # --- Example: generic route with doc_type flag ---
    out_id = client.ocr("thai_id_card_front.jpg", doc_type="id_card")
    print("\n=== ID via doc_type ===")
    print("Parsed:", out_id.get("parsed"))

    # out_income = client.ocr("sample_payslip.jpg", doc_type="income")
    # print("\n=== Income via doc_type ===")
    # print("Parsed:", out_income.get("parsed"))
    # print("Normalized:", out_income.get("normalized"))

    # # --- Example: dedicated routes ---
    # out_id2 = client.ocr_id("thai_id_card_front.jpg")
    # print("\n=== ID via dedicated route ===")
    # print("Parsed:", out_id2.get("parsed"))

    # out_income2 = client.ocr_income("sample_payslip.jpg")
    # print("\n=== Income via dedicated route ===")
    # print("Parsed:", out_income2.get("parsed"))
    # print("Normalized:", out_income2.get("normalized"))
