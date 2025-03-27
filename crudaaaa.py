import datetime
from sqlalchemy.orm import Session
from typing import List, Optional
import models, schemas

# ------------------------
# Company
# ------------------------
def get_company_by_code(db: Session, company_code: str) -> Optional[models.Company]:
    return db.query(models.Company).filter(models.Company.company_code == company_code).first()

# ------------------------
# Projects
# ------------------------
def get_project(db: Session, project_id: int, company_id: Optional[int] = None):
    query = db.query(models.Project).filter(models.Project.id == project_id)
    if company_id is not None:
        query = query.filter(models.Project.company_id == company_id)
    return query.first()

def get_projects(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Project]:
    query = db.query(models.Project)
    if company_id is not None:
        query = query.filter(models.Project.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_project(db: Session, project_data: dict):
    db_project = models.Project(**project_data)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

def update_project(db: Session, project_id: int, project_update: dict, company_id: Optional[int] = None):
    db_project = get_project(db, project_id, company_id)
    if not db_project:
        return None
    for key, value in project_update.items():
        setattr(db_project, key, value)
    db.commit()
    db.refresh(db_project)
    return db_project

def delete_project(db: Session, project_id: int, company_id: Optional[int] = None):
    db_project = get_project(db, project_id, company_id)
    if db_project:
        db.delete(db_project)
        db.commit()
        return True
    return False

# ------------------------
# Reports
# ------------------------
def get_report(db: Session, report_id: int, company_id: Optional[int] = None):
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

def create_report(db: Session, report_data: dict):
    db_report = models.Report(**report_data)
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def update_report(db: Session, report_id: int, report_update: dict, company_id: Optional[int] = None):
    db_report = get_report(db, report_id, company_id)
    if not db_report:
        return None
    for key, value in report_update.items():
        setattr(db_report, key, value)
    db.commit()
    db.refresh(db_report)
    return db_report

def delete_report(db: Session, report_id: int, company_id: Optional[int] = None):
    db_report = get_report(db, report_id, company_id)
    if db_report:
        db.delete(db_report)
        db.commit()
        return True
    return False

# ------------------------
# Schedule Items
# ------------------------
def get_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None):
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

def create_schedule_item(db: Session, item_data: dict):
    db_item = models.ScheduleItem(**item_data)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def update_schedule_item(db: Session, item_id: int, item_update: dict,
                         company_id: Optional[int] = None):
    db_item = get_schedule_item(db, item_id, company_id)
    if not db_item:
        return None
    for key, value in item_update.items():
        setattr(db_item, key, value)
    db.commit()
    db.refresh(db_item)
    return db_item

def delete_schedule_item(db: Session, item_id: int, company_id: Optional[int] = None):
    db_item = get_schedule_item(db, item_id, company_id)
    if db_item:
        db.delete(db_item)
        db.commit()
        return True
    return False

# ------------------------
# Orders
# ------------------------
def get_order(db: Session, order_id: int, company_id: Optional[int] = None):
    query = db.query(models.Order).filter(models.Order.id == order_id)
    if company_id is not None:
        query = query.filter(models.Order.company_id == company_id)
    return query.first()

def get_orders(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Order]:
    query = db.query(models.Order)
    if company_id is not None:
        query = query.filter(models.Order.company_id == company_id)
    return query.offset(skip).limit(limit).all()

def create_order(db: Session, order_data: dict):
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

def update_order(db: Session, order_id: int, order_update: dict, company_id: Optional[int] = None):
    db_order = get_order(db, order_id, company_id)
    if not db_order:
        return None
    old_status = db_order.order_status
    for key, value in order_update.items():
        setattr(db_order, key, value)
    db.commit()
    db.refresh(db_order)
    if old_status == "ordered" and db_order.order_status == "received":
        update_inventory_for_order(db, db_order)
    return db_order

def delete_order(db: Session, order_id: int, company_id: Optional[int] = None):
    db_order = get_order(db, order_id, company_id)
    if db_order:
        db.delete(db_order)
        db.commit()
        return True
    return False

def get_inventory_by_material_and_project(db: Session, material_name: str, project_id: int,
                                            company_id: Optional[int] = None):
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
        new_quantity = inventory.quantity + order.quantity
        upd_data = {
            "quantity": new_quantity,
            "updated_by": "system",
            "last_updated": datetime.datetime.utcnow()
        }
        update_inventory(db, inventory.id, upd_data, order.company_id)
    else:
        new_inventory_data = {
            "project_id": order.project_id,
            "material_name": order.material,
            "location": order.storage,
            "quantity": order.quantity,
            "updated_by": "system",
            "last_updated": datetime.datetime.utcnow(),
            "company_id": order.company_id
        }
        create_inventory(db, new_inventory_data)

# ------------------------
# Inventory Management
# ------------------------
def get_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None):
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

def create_inventory(db: Session, inventory_data: dict):
    db_inv = models.Inventory(**inventory_data)
    db.add(db_inv)
    db.commit()
    db.refresh(db_inv)
    return db_inv

def update_inventory(db: Session, inventory_id: int, inv_update: dict,
                     company_id: Optional[int] = None):
    db_inv = get_inventory(db, inventory_id, company_id)
    if not db_inv:
        return None
    for key, value in inv_update.items():
        setattr(db_inv, key, value)
    db.commit()
    db.refresh(db_inv)
    return db_inv

def delete_inventory(db: Session, inventory_id: int, company_id: Optional[int] = None):
    db_inv = get_inventory(db, inventory_id, company_id)
    if db_inv:
        db.delete(db_inv)
        db.commit()
        return True
    return False

def create_inventory_history(db: Session, history_data: dict):
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
# Blueprint
# ------------------------
def get_blueprints(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None,
                   project_id: Optional[int] = None, search: Optional[str] = None,
                   sort: Optional[str] = None) -> List[models.Blueprint]:
    query = db.query(models.Blueprint)
    if company_id is not None:
        query = query.filter(models.Blueprint.company_id == company_id)
    if project_id is not None:
        query = query.filter(models.Blueprint.project_id == project_id)
    if search:
        query = query.filter(models.Blueprint.name.contains(search))
    if sort:
        if sort == "name_asc":
            query = query.order_by(models.Blueprint.name.asc())
        elif sort == "name_desc":
            query = query.order_by(models.Blueprint.name.desc())
    return query.offset(skip).limit(limit).all()

def create_blueprint(db: Session, blueprint_data: dict):
    db_blueprint = models.Blueprint(**blueprint_data)
    db.add(db_blueprint)
    db.commit()
    db.refresh(db_blueprint)
    return db_blueprint

def update_blueprint(db: Session, blueprint_id: int, blueprint_data: dict,
                     company_id: Optional[int] = None):
    db_blueprint = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id)
    if company_id is not None:
        db_blueprint = db_blueprint.filter(models.Blueprint.company_id == company_id)
    db_blueprint = db_blueprint.first()
    if not db_blueprint:
        return None
    for key, value in blueprint_data.items():
        setattr(db_blueprint, key, value)
    db.commit()
    db.refresh(db_blueprint)
    return db_blueprint

def delete_blueprint(db: Session, blueprint_id: int, company_id: Optional[int] = None):
    db_blueprint = db.query(models.Blueprint).filter(models.Blueprint.id == blueprint_id)
    if company_id is not None:
        db_blueprint = db_blueprint.filter(models.Blueprint.company_id == company_id)
    db_blueprint = db_blueprint.first()
    if db_blueprint:
        db.delete(db_blueprint)
        db.commit()
        return True
    return False

# ------------------------
# Material
# ------------------------
def create_material(db: Session, material_data: dict):
    db_material = models.Material(**material_data)
    db.add(db_material)
    db.commit()
    db.refresh(db_material)
    return db_material

def get_materials(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Material]:
    query = db.query(models.Material)
    if company_id is not None:
        query = query.filter(models.Material.company_id == company_id)
    return query.offset(skip).limit(limit).all()

# ------------------------
# Employee
# ------------------------
def create_employee(db: Session, employee_data: dict):
    db_employee = models.Employee(**employee_data)
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    return db_employee

def get_employees(db: Session, skip: int = 0, limit: int = 100, company_id: Optional[int] = None) -> List[models.Employee]:
    query = db.query(models.Employee)
    if company_id is not None:
        query = query.filter(models.Employee.company_id == company_id)
    return query.offset(skip).limit(limit).all()
