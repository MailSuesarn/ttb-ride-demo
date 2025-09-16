from typing import Any, Dict
from .ocr_agent import OlmOCRClient

def _get_ocr_client() -> OlmOCRClient:
    return OlmOCRClient()

def ocr_id_extract_path(path: str) -> Dict[str, Any]:
    ocr = _get_ocr_client()
    out = ocr.ocr_id(path)
    return {"parsed": out.get("parsed") or {}}

def ocr_income_extract_path(path: str) -> Dict[str, Any]:
    ocr = _get_ocr_client()
    out = ocr.ocr_income(path)
    return {"parsed": out.get("parsed") or {}, "normalized": out.get("normalized") or {}}
