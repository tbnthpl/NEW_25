import io
import os
import zipfile
from pathlib import PurePath

from fastapi import HTTPException, UploadFile, status

MAX_EXCEL_UPLOAD_BYTES = int(os.environ.get("MAX_EXCEL_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_EXCEL_UNCOMPRESSED_BYTES = int(
    os.environ.get("MAX_EXCEL_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024))
)
MAX_EXCEL_COMPRESSION_RATIO = float(os.environ.get("MAX_EXCEL_COMPRESSION_RATIO", "200"))

_ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
_ALLOWED_CONTENT_TYPES = {
    "",
    "application/octet-stream",
    "binary/octet-stream",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

def _check_zip_bomb(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            total = 0
            for info in zf.infolist():
                total += int(info.file_size or 0)
                if total > MAX_EXCEL_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Workbook expands to more than "
                            f"{MAX_EXCEL_UNCOMPRESSED_BYTES // (1024 * 1024)} MB when uncompressed."
                        ),
                    )
            compressed = max(len(content), 1)
            if total / compressed > MAX_EXCEL_COMPRESSION_RATIO:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Workbook has an unusually high compression ratio. Re-save the file and try again.",
                )
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsupported Excel file.",
        ) from exc

def read_validated_excel_upload(file: UploadFile) -> bytes:
    filename = (file.filename or "").strip()
    ext = PurePath(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload an Excel file (.xlsx or .xls).",
        )

    content_type = (file.content_type or "").lower().strip()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Upload an Excel file (.xlsx or .xls).",
        )

    content = file.file.read(MAX_EXCEL_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(content) > MAX_EXCEL_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds the {MAX_EXCEL_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    if content.startswith(_ZIP_MAGIC):
        _check_zip_bomb(content)
    elif not content.startswith(_OLE_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unsupported Excel file.",
        )
    return content
