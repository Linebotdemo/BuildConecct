from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

import crud
import models
import schemas
from database import get_db

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("", response_model=List[schemas.ReportOut])
def list_reports(db: Session = Depends(get_db)):
    reports = (
        db.query(models.Report)
          .options(joinedload(models.Report.project))
          .order_by(models.Report.created_at.desc())
          .all()
    )
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "project_name": r.project.name if r.project else None,
            "report_text": r.report_text,
            "photo_url": r.photo_url,
            "audio_url": r.audio_url,
            "status": r.status,
            "reporter": r.reporter,
            "created_at": r.created_at,
        }
        for r in reports
    ]

@router.post("", response_model=schemas.ReportOut, status_code=201)
def create_report(report_in: schemas.ReportCreate, db: Session = Depends(get_db)):
    project = crud.get_project(db, report_in.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    report = crud.create_report(db, report_in.dict())
    return {
        **report.__dict__,
        "project_name": project.name,
    }

@router.put("/{report_id}", response_model=schemas.ReportOut)
def update_report(report_id: int, update: schemas.ReportUpdate, db: Session = Depends(get_db)):
    report = crud.update_report(db, report_id, update.dict())
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    project = crud.get_project(db, report.project_id)
    return {
        **report.__dict__,
        "project_name": project.name if project else None,
    }
