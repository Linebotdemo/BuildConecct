from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import schemas, models, crud
from database import SessionLocal
from auth import get_current_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 資材登録
@router.post("/materials", response_model=schemas.Material)
def create_material(material: schemas.MaterialCreate, db: Session = Depends(get_db)):
    try:
        new_material = crud.create_material(db, material.dict())
        return new_material
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/materials", response_model=List[schemas.Material])
def list_materials(skip: int = 0, limit: int = 100, company_id: Optional[int] = None, db: Session = Depends(get_db)):
    return crud.get_materials(db, skip=skip, limit=limit, company_id=company_id)

# 従業員登録
@router.post("/employees", response_model=schemas.Employee)
def create_employee(
    employee: schemas.EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ["admin", "superadmin"]:
        raise HTTPException(status_code=403, detail="権限がありません（管理者のみ登録可能）")
    employee_data = employee.dict()
    employee_data["company_id"] = current_user.get("company_id")
    try:
        new_employee = crud.create_employee(db, employee_data)
        return new_employee
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/employees", response_model=List[schemas.Employee])
def list_employees(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if current_user["role"] == "superadmin":
        company_id = None
    else:
        company_id = current_user.get("company_id")
    try:
        return crud.get_employees(db, skip=skip, limit=limit, company_id=company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
