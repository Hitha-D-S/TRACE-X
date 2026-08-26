"""Upload dataset endpoints — CSV/JSON file ingestion."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import get_current_user
from app.detection.pipeline import process_batch
from app.models.transaction import TransactionCreate

router = APIRouter()
settings = get_settings()

# In-memory upload job store
_upload_jobs: Dict[str, Dict[str, Any]] = {}

ALLOWED_EXTENSIONS = {".csv", ".json"}
ALLOWED_MIMETYPES = {
    "text/csv", "application/json",
    "text/plain",
}

# Column name heuristics for auto-mapping
COLUMN_ALIASES = {
    "transaction_id": ["transaction_id", "tx_id", "id", "txn_id", "reference_id"],
    "source_account_id": ["source_account_id", "sender_account", "from_account", "debit_account", "sender"],
    "destination_account_id": ["destination_account_id", "receiver_account", "to_account", "credit_account", "beneficiary"],
    "amount": ["amount", "value", "txn_amount", "transaction_amount", "sum"],
    "currency": ["currency", "ccy", "currency_code"],
    "timestamp": ["timestamp", "datetime", "date", "txn_date", "transaction_date", "created_at"],
    "transaction_type": ["transaction_type", "type", "txn_type", "payment_type"],
    "channel": ["channel", "medium", "payment_channel"],
    "location": ["location", "city", "branch", "place"],
    "reference": ["reference", "remarks", "narration", "description", "note"],
}


def _infer_column_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """Map file headers to internal field names using heuristics."""
    headers_lower = {h.lower().strip(): h for h in headers}
    mapping: Dict[str, Optional[str]] = {}

    for field, aliases in COLUMN_ALIASES.items():
        matched = next((headers_lower[a] for a in aliases if a in headers_lower), None)
        mapping[field] = matched

    return mapping


def _parse_rows_csv(content: bytes) -> List[Dict[str, str]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _parse_rows_json(content: bytes) -> List[Dict[str, Any]]:
    data = json.loads(content)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "transactions" in data:
        return data["transactions"]
    raise ValueError("JSON must be an array of transaction objects or {'transactions': [...]}")


def _normalize_row(
    row: Dict[str, Any],
    mapping: Dict[str, Optional[str]],
    dataset_id: str,
) -> Optional[TransactionCreate]:
    """Normalize a mapped row into TransactionCreate. Returns None on validation error."""
    def _get(field: str, default=None):
        col = mapping.get(field)
        if col and col in row:
            val = row[col]
            return val if val not in ("", None) else default
        return default

    try:
        amount_raw = _get("amount", 0)
        amount = Decimal(str(amount_raw)) if amount_raw else Decimal("0")

        src = _get("source_account_id") or _get("source_account_id", "")
        dst = _get("destination_account_id") or _get("destination_account_id", "")

        if not src or not dst:
            return None


        return TransactionCreate(
            id=_get("transaction_id") or str(uuid.uuid4()),
            source_account_id=str(src).strip(),
            destination_account_id=str(dst).strip(),
            amount=amount,
            currency=(_get("currency") or "INR").upper()[:3],
            timestamp=_get("timestamp") or datetime.now(timezone.utc),
            transaction_type=(_get("transaction_type") or "OTHER").upper(),
            channel=(_get("channel") or "OTHER").upper(),
            location=_get("location"),
            reference=_get("reference"),
            dataset_id=dataset_id,
            source="USER_UPLOAD",
            sender_name=row.get("sender_name") or row.get("sender"),
            receiver_name=row.get("receiver_name") or row.get("receiver"),
            source_bank_name=row.get("source_bank_name") or row.get("source_bank"),
            destination_bank_name=row.get("destination_bank_name") or row.get("destination_bank"),
            sender_type=row.get("sender_type"),
            receiver_type=row.get("receiver_type"),
        )
    except Exception:
        return None


@router.post("/upload/preview")
async def upload_preview(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Parse first N rows and infer column mapping."""
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail=f"Unsupported file type: {ext}")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, detail=f"File exceeds {settings.max_upload_size_mb}MB limit")

    try:
        if ext == ".csv":
            rows = _parse_rows_csv(content)
        elif ext == ".json":
            rows = _parse_rows_json(content)
        else:
            raise HTTPException(400, detail="XLSX requires openpyxl — use CSV/JSON for MVP")
    except Exception as e:
        raise HTTPException(400, detail=f"Parse error: {str(e)}")

    headers = list(rows[0].keys()) if rows else []
    inferred_mapping = _infer_column_mapping(headers)
    sample = rows[:5]

    file_hash = hashlib.sha256(content).hexdigest()

    return {
        "filename": file.filename,
        "file_hash": file_hash,
        "total_rows_preview": len(rows),
        "headers": headers,
        "inferred_mapping": inferred_mapping,
        "sample_rows": sample,
        "note": "Confirm or correct the column mapping before committing ingestion.",
    }


class MappingConfirmRequest(BaseModel):
    file_hash: str
    column_mapping: Dict[str, Optional[str]]
    dataset_name: Optional[str] = None


@router.post("/upload/mapping")
async def confirm_mapping(
    req: MappingConfirmRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Validate the confirmed column mapping and return a job ID."""
    required = ["source_account_id", "destination_account_id", "amount"]
    missing = [f for f in required if not req.column_mapping.get(f)]
    if missing:
        raise HTTPException(400, detail=f"Required columns not mapped: {missing}")

    job_id = str(uuid.uuid4())
    _upload_jobs[job_id] = {
        "id": job_id,
        "status": "PENDING",
        "file_hash": req.file_hash,
        "column_mapping": req.column_mapping,
        "dataset_name": req.dataset_name or f"upload-{job_id[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"job_id": job_id, "status": "PENDING", "message": "Call /upload/commit to ingest."}


class CommitRequest(BaseModel):
    job_id: str
    file_content_base64: Optional[str] = None  # for inline small files
    filename: str = "upload.csv"


@router.post("/upload/commit")
async def commit_upload(
    job_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Ingest the mapped, validated file through the detection pipeline."""
    job = _upload_jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")

    job["status"] = "PROCESSING"
    content = await file.read()
    ext = "." + (file.filename or "").rsplit(".", 1)[-1].lower()

    try:
        if ext == ".csv":
            rows = _parse_rows_csv(content)
        elif ext == ".json":
            rows = _parse_rows_json(content)
        else:
            raise HTTPException(400, detail="Unsupported format")
    except Exception as e:
        job["status"] = "FAILED"
        raise HTTPException(400, detail=f"Parse error: {str(e)}")

    if len(rows) > settings.max_upload_rows:
        job["status"] = "FAILED"
        raise HTTPException(400, detail=f"Exceeds max {settings.max_upload_rows} rows")

    mapping = job["column_mapping"]
    dataset_id = f"UPLOAD:{job['dataset_name']}"
    quarantined = []
    valid_txs = []

    for i, row in enumerate(rows):
        tx = _normalize_row(row, mapping, dataset_id)
        if tx is None:
            quarantined.append({
                "row": i + 1,
                "reason": "missing required fields or validation error",
                "raw": {k: str(v)[:100] for k, v in list(row.items())[:5]},
            })
        else:
            valid_txs.append(tx)

    # Process through pipeline
    result = await process_batch(valid_txs, dataset_id=dataset_id)

    job.update({
        "status": "DONE",
        "dataset_id": dataset_id,
        "rows_received": len(rows),
        "rows_ingested": len(valid_txs),
        "rows_quarantined": len(quarantined),
        "error_report": quarantined[:100],
        "pipeline_result": result,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "job_id": job_id,
        "status": "DONE",
        "dataset_id": dataset_id,
        "rows_received": len(rows),
        "rows_ingested": len(valid_txs),
        "rows_quarantined": len(quarantined),
        "alerts_generated": result.get("alerts_generated", 0),
        "message": f"Ingested {len(valid_txs)} rows. View results at dataset_id={dataset_id}",
    }


@router.get("/upload/{job_id}/status")
async def job_status(job_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    job = _upload_jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    return {k: v for k, v in job.items() if k != "error_report"}


@router.get("/upload/{job_id}/errors")
async def job_errors(job_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    job = _upload_jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail=f"Job {job_id} not found")
    return {
        "job_id": job_id,
        "rows_quarantined": job.get("rows_quarantined", 0),
        "errors": job.get("error_report", []),
    }
