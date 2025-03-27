import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from main import get_line_user as _get_line_user, create_line_user as _create_line_user, update_line_user as _update_line_user
import models

# ------------------------
# Company
# ------------------------
def get_company_by_code(db: Session, company_code: str) -> Optional[models.Company]:
    return db.query(models.Company).filter(models.Company.company_code == company_code).first()

# ------------------------
# Projects
# ------------------------
def get_project(db: Session, project_id: int, company_id: Optional[int] = None) -> Optional[models.Project]:
    query = db.query(models.Project).filter(models.Project.id == project_id)
    if company_id is not None:
        query = query.filter(models.Project.company_id == company_id)
    return query.first()

def get_projects(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Project]:
    query = db.query(models.Project)
    if company_id is not None:
        query = query.filter(models.Project.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def get_line_user(db, line_user_id: str):
    return _get_line_user(db, line_user_id)

def create_line_user(db, line_user_id: str, user_name: str = ""):
    return _create_line_user(db, line_user_id, user_name)


def create_project(db: Session, project_data: dict) -> models.Project:
    db_project = models.Project(**project_data)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project
def update_project(db: Session, project_id: int, project_update: dict, company_id: Optional[int] = None) -> Optional[models.Project]:
    project = get_project(db, project_id, company_id)
    if not project:
        return None
    for key, value in project_update.items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project

def delete_project(db: Session, project_id: int, company_id: Optional[int] = None) -> bool:
    project = get_project(db, project_id, company_id)
    if project:
        db.delete(project)
        db.commit()
        return True
    return False

# ------------------------
# Reports
# ------------------------
def get_report(db: Session, report_id: int, company_id: Optional[int] = None) -> Optional[models.Report]:
    query = db.query(models.Report).filter(models.Report.id == report_id)
    if company_id is not None:
        query = query.filter(models.Report.company_id == company_id)
    return query.first()

def get_reports(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None,
                search: Optional[str] = None, company_id: Optional[int] = None) -> List[models.Report]:
    query = db.query(models.Report)
    if company_id is not None:
        query = query.filter(models.Report.company_id == company_id)
    if status:
        query = query.filter(models.Report.status == status)
    if search:
        query = query.filter(models.Report.report_text.contains(search))
    return query.offset(skip).limit(limit).all()

def create_report(db: Session, report_data: dict) -> models.Report:
    db_report = models.Report(**report_data)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report
def update_report(db: Session, report_id: int, report_update: dict, company_id: Optional[int] = None) -> Optional[models.Report]:
    report = get_report(db, report_id, company_id)
    if not report:
        return None
    for key, value in report_update.items():
        setattr(report, key, value)
    db.commit()
    db.refresh(report)
    return report

def delete_report(db: Session, report_id: int, company_id: Optional[int] = None) -> bool:
    report = get_report(db, report_id, company_id)
    if report:
        db.delete(report)
        db.commit()
        return True
    return False

# ------------------------
# Schedule Items
# ------------------------
def get_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None) -> Optional[models.ScheduleItem]:
    query = db.query(models.ScheduleItem).filter(models.ScheduleItem.id == item_id)
    if company_id is not None:
        query = query.filter(models.ScheduleItem.company_id == company_id)
    return query.first()

def get_schedule_items(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None,
                       project_id: Optional[int] = None, company_id: Optional[int] = None) -> List[models.ScheduleItem]:
    query = db.query(models.ScheduleItem)
    if company_id is not None:
        query = query.filter(models.ScheduleItem.company_id == company_id)
    if project_id:
        query = query.filter(models.ScheduleItem.project_id == project_id)
    if status:
        query = query.filter(models.ScheduleItem.status == status)
    return query.offset(skip).limit(limit).all()

def create_schedule_item(db: Session, item_data: dict) -> models.ScheduleItem:
    db_item = models.ScheduleItem(**item_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
def update_schedule_item(db: Session, item_id: int, item_update: dict, company_id: Optional[int] = None) -> Optional[models.ScheduleItem]:
    item = get_schedule_item(db, item_id, company_id)
    if not item:
        return None
    for key, value in item_update.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item

def delete_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None) -> bool:
    item = get_schedule_item(db, item_id, company_id)
    if item:
        db.delete(item)
        db.commit()
        return True
    return False

# ------------------------
# Orders
# ------------------------
def get_order(db: Session, order_id: int, company_id: Optional[int] = None) -> Optional[models.Order]:
    query = db.query(models.Order).filter(models.Order.id == order_id)
    if company_id is not None:
        query = query.filter(models.Order.company_id == company_id)
    return query.first()

def get_orders(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Order]:
    query = db.query(models.Order)
    if company_id is not None:
        query = query.filter(models.Order.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_order(db: Session, order_data: dict) -> models.Order:
    if "price" in order_data and "quantity" in order_data:
        try:
            order_data["total_price"] = float(order_data["price"]) * int(order_data["quantity"])
        except Exception:
            order_data["total_price"] = None
    db_order = models.Order(**order_data)
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order
def update_order(db: Session, order_id: int, order_update: dict, company_id: Optional[int] = None) -> Optional[models.Order]:
    order = get_order(db, order_id, company_id)
    if not order:
        return None
    old_status = order.order_status
    for key, value in order_update.items():
        setattr(order, key, value)
    db.commit()
    db.refresh(order)
    if old_status == "ordered" and order.order_status == "received":
        update_inventory_for_order(db, order)
    return order

def delete_order(db: Session, order_id: int, company_id: Optional[int] = None) -> bool:
    order = get_order(db, order_id, company_id)
    if order:
        db.delete(order)
        db.commit()
        return True
    return False

def get_inventory_by_material_and_project(db: Session, material_name: str, project_id: int, company_id: Optional[int] = None) -> Optional[models.Inventory]:
    query = db.query(models.Inventory).filter(
        models.Inventory.material_name == material_name,
        models.Inventory.project_id == project_id
    )
    if company_id is not None:
        query = query.filter(models.Inventory.company_id == company_id)
    return query.first()

def update_inventory_for_order(db: Session, order: models.Order):
    inventory = get_inventory_by_material_and_project(db, order.material, order.project_id, order.company_id)
    if inventory:
        inventory.quantity += order.quantity
        inventory.updated_by = "system"
        inventory.last_updated = datetime.datetime.utcnow()
        db.commit()
    else:
        create_inventory(db, {
            "project_id": order.project_id,
            "material_name": order.material,
            "location": order.storage,
            "quantity": order.quantity,
            "updated_by": "system",
            "last_updated": datetime.datetime.utcnow(),
            "company_id": order.company_id
        })
# ------------------------
# Inventory Management
# ------------------------
def get_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None) -> Optional[models.Inventory]:
    query = db.query(models.Inventory).filter(models.Inventory.id == inventory_id)
    if company_id is not None:
        query = query.filter(models.Inventory.company_id == company_id)
    return query.first()

def get_inventories(db: Session, skip: int = 0, limit: int = 100, search: Optional[str] = None,
                    project_id: Optional[int] = None, company_id: Optional[int] = None,
                    sort: Optional[str] = None) -> List[models.Inventory]:
    query = db.query(models.Inventory)
    if company_id is not None:
        query = query.filter(models.Inventory.company_id == company_id)
    if search:
        query = query.filter(models.Inventory.material_name.contains(search))
    if project_id:
        query = query.filter(models.Inventory.project_id == project_id)
    if sort:
        if sort == "id_asc":
            query = query.order_by(models.Inventory.id.asc())
        elif sort == "id_desc":
            query = query.order_by(models.Inventory.id.desc())
        elif sort == "quantity_asc":
            query = query.order_by(models.Inventory.quantity.asc())
        elif sort == "quantity_desc":
            query = query.order_by(models.Inventory.quantity.desc())
        else:
            query = query.order_by(models.Inventory.id.desc())
    else:
        query = query.order_by(models.Inventory.id.desc())
    return query.offset(skip).limit(limit).all()

def create_inventory(db: Session, inventory_data: dict) -> models.Inventory:
    db_inv = models.Inventory(**inventory_data)
    db.add(db_inv)
    db.commit()
    db.refresh(db_inv)
    return db_inv

def update_inventory(db: Session, inventory_id: int, inv_update: dict,
                     company_id: Optional[int] = None) -> Optional[models.Inventory]:
    inv = get_inventory(db, inventory_id, company_id)
    if not inv:
        return None
    for key, value in inv_update.items():
        setattr(inv, key, value)
    db.commit()
    db.refresh(inv)
    return inv

def delete_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None) -> bool:
    inv = get_inventory(db, inventory_id, company_id)
    if inv:
        db.delete(inv)
        db.commit()
        return True
    return False
def create_inventory_history(db: Session, history_data: dict) -> models.InventoryHistory:
    db_history = models.InventoryHistory(**history_data)
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history

def get_inventory_history(db: Session, inventory_id: int, skip: int = 0, limit: int = 100,
                          sort: Optional[str] = None) -> List[models.InventoryHistory]:
    query = db.query(models.InventoryHistory).filter(models.InventoryHistory.inventory_id == inventory_id)
    if sort == "updated_at_asc":
        query = query.order_by(models.InventoryHistory.updated_at.asc())
    else:
        query = query.order_by(models.InventoryHistory.updated_at.desc())
    return query.offset(skip).limit(limit).all()

# ------------------------
# Blueprints
# ------------------------
def get_blueprints(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None,
                   project_id: Optional[int] = None) -> List[models.Blueprint]:
    query = db.query(models.Blueprint)
    if company_id is not None:
        query = query.filter(models.Blueprint.company_id == company_id)
    if project_id:
        query = query.filter(models.Blueprint.project_id == project_id)
    return query.offset(skip).limit(limit).all()

def create_blueprint(db: Session, blueprint_data: dict) -> models.Blueprint:
    db_bp = models.Blueprint(**blueprint_data)
    db.add(db_bp)
    db.commit()
    db.refresh(db_bp)
    return db_bp

def delete_blueprint(db: Session, blueprint_id: int, company_id: Optional[int] = None) -> bool:
    bp = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id)
    if company_id is not None:
        bp = bp.filter(models.Blueprint.company_id == company_id)
    bp = bp.first()
    if bp:
        db.delete(bp)
        db.commit()
        return True
    return False

# ------------------------
# Materials
# ------------------------
def get_materials(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Material]:
    query = db.query(models.Material)
    if company_id is not None:
        query = query.filter(models.Material.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_material(db: Session, material_data: dict) -> models.Material:
    db_mat = models.Material(**material_data)
    db.add(db_mat)
    db.commit()
    db.refresh(db_mat)
    return db_mat

def delete_material(db: Session, material_id: int, company_id: Optional[int] = None) -> bool:
    mat = db.query(models.Material).filter(models.Material.id == material_id)
    if company_id is not None:
        mat = mat.filter(models.Material.company_id == company_id)
    mat = mat.first()
    if mat:
        db.delete(mat)
        db.commit()
        return True
    return False

# ------------------------
# Employees
# ------------------------
def get_employees(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Employee]:
    query = db.query(models.Employee)
    if company_id is not None:
        query = query.filter(models.Employee.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_employee(db: Session, employee_data: dict) -> models.Employee:
    db_emp = models.Employee(**employee_data)
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp

def delete_employee(db: Session, employee_id: int, company_id: Optional[int] = None) -> bool:
    emp = db.query(models.Employee).filter(models.Employee.id == employee_id)
    if company_id is not None:
        emp = emp.filter(models.Employee.company_id == company_id)
    emp = emp.first()
    if emp:
        db.delete(emp)
        db.commit()
        return True
    return False

# ==== LineUser 関連ラッパー ====
from main import get_line_user as _get_line_user, create_line_user as _create_line_user, update_line_user as _update_line_user

def get_line_user(db, line_user_id: str):
    return _get_line_user(db, line_user_id)

def create_line_user(db, line_user_id: str, user_name: str = ""):
    return _create_line_user(db, line_user_id, user_name)

def update_line_user(db, line_user, updates: dict):
    return _update_line_user(db, line_user, updates)

