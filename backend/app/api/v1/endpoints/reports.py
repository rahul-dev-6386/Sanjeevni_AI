from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.report import MedicalReportResponse, UploadStatusResponse
from app.services.report_service import ReportService
from app.ocr import ocr_manager

router = APIRouter(prefix="/api/reports", tags=["Medical Reports"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_report(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadStatusResponse:
    allowed_types = {
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {file.content_type} not supported. Use PDF, JPG, or PNG.",
        )

    service = ReportService(db)
    report = await service.upload_async(current_user.id, file, background_tasks)
    return UploadStatusResponse(report_id=report.id, status=report.status)


@router.get("/{report_id}/status", response_model=UploadStatusResponse)
def get_report_status(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ReportService(db)
    report = service.get_status(report_id, current_user.id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return UploadStatusResponse(report_id=report.id, status=report.status, error_message=report.error_message)


@router.post("/ocr", status_code=status.HTTP_200_OK)
async def ocr_extract(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    file_bytes = await file.read()
    result = ocr_manager.extract_structured(file_bytes, file.content_type or "")
    return result


@router.get("", response_model=list[MedicalReportResponse])
def list_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ReportService(db)
    return service.get_user_reports(current_user.id)


@router.get("/{report_id}", response_model=MedicalReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ReportService(db)
    report = service.get_report(report_id, current_user.id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ReportService(db)
    if not service.delete_report(report_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return {"message": "Report deleted"}
