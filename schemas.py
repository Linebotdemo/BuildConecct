from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

# === Company ===
class CompanyBaseSchema(BaseModel):
    company_name: str

class CompanyCreateSchema(CompanyBaseSchema):
    company_code: Optional[str] = None

class CompanyOutSchema(CompanyBaseSchema):
    id: int
    company_code: str
    api_key: str

    class Config:
        from_attributes = True

# === User ===
class UserBaseSchema(BaseModel):
    email: str
    role: Optional[str] = "user"
    active: bool = True

class UserCreateSchema(UserBaseSchema):
    password: str
    company_id: Optional[int] = None

class UserOutSchema(UserBaseSchema):
    id: int
    company_id: Optional[int]

    class Config:
        from_attributes = True

class UserUpdateSchema(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    company_id: Optional[int] = None
    password: Optional[str] = None

    class Config:
        from_attributes = True

# === Project ===
class ProjectBaseSchema(BaseModel):
    name: str
    location: Optional[str] = None
    building_type: Optional[str] = None
    ground_floors: Optional[int] = None
    basement_floors: Optional[int] = None
    total_floor_area: Optional[float] = None
    project_manager: Optional[str] = None

class ProjectCreateSchema(ProjectBaseSchema):
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class ProjectSchema(ProjectBaseSchema):
    id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    ai_plan: Optional[str] = None
    progress: Optional[float] = 0.0

    class Config:
        from_attributes = True

# === Report ===
class ReportBaseSchema(BaseModel):
    project_id: int
    report_text: str
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None

class ReportCreateSchema(ReportBaseSchema):
    status: str = "pending"

class ReportUpdateSchema(BaseModel):
    report_text: Optional[str] = None
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    status: Optional[str] = None
    reporter: Optional[str] = None

    class Config:
        from_attributes = True

class ReportOutSchema(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    report_text: str
    photo_url: Optional[str] = None
    audio_url: Optional[str] = None
    status: str
    reporter: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# === ScheduleItem ===
class ScheduleItemBaseSchema(BaseModel):
    project_id: int
    task: str
    start_time: datetime
    end_time: datetime

class ScheduleItemCreateSchema(ScheduleItemBaseSchema):
    status: str = "not_started"

class ScheduleItemSchema(ScheduleItemBaseSchema):
    id: int
    status: str

    class Config:
        from_attributes = True

# === Order ===
class OrderBaseSchema(BaseModel):
    project_id: int
    material: str
    quantity: int
    storage: Optional[str] = None
    order_date: Optional[date] = None
    delivery_date: Optional[date] = None
    supplier_name: Optional[str] = None
    price: Optional[float] = None
    total_price: Optional[float] = None

class OrderCreateSchema(OrderBaseSchema):
    order_status: str = "pending"
    surplus: bool = False

class OrderSchema(OrderBaseSchema):
    id: int
    order_status: str
    surplus: bool

    class Config:
        from_attributes = True

# === Inventory ===
class InventoryBaseSchema(BaseModel):
    material_name: str
    quantity: int
    location: Optional[str] = None
    project_id: int

class InventoryCreateSchema(InventoryBaseSchema):
    pass

class InventorySchema(InventoryBaseSchema):
    id: int
    last_updated: Optional[datetime] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True

class InventoryUpdateSchema(BaseModel):
    material_name: Optional[str] = None
    quantity: Optional[int] = None
    location: Optional[str] = None
    project_id: Optional[int] = None
    last_updated: Optional[datetime] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True

class InventoryHistorySchema(BaseModel):
    id: int
    inventory_id: int
    updated_at: datetime
    updated_by: str
    change_data: Optional[str] = None

    class Config:
        from_attributes = True

# === Blueprint ===
class BlueprintBaseSchema(BaseModel):
    project_id: int
    name: str
    filename: str
    file_path: str
    version: Optional[str] = None

class BlueprintCreateSchema(BlueprintBaseSchema):
    pass

class BlueprintOutSchema(BlueprintBaseSchema):
    id: int
    created_at: datetime
    company_id: int

    class Config:
        from_attributes = True

# === Material ===
class MaterialBaseSchema(BaseModel):
    name: str
    price: float
    supplier_name: str
    minimum_stock: int

class MaterialCreateSchema(MaterialBaseSchema):
    company_id: Optional[int] = None

class MaterialSchema(MaterialBaseSchema):
    id: int
    company_id: Optional[int]

    class Config:
        from_attributes = True

# === Employee ===
class EmployeeBaseSchema(BaseModel):
    name: str
    qualifications: Optional[str] = None

class EmployeeCreateSchema(EmployeeBaseSchema):
    company_id: Optional[int] = None

class EmployeeSchema(EmployeeBaseSchema):
    id: int
    company_id: Optional[int]

    class Config:
        from_attributes = True

# === LineUser ===
class LineUserBaseSchema(BaseModel):
    line_user_id: str
    line_user_name: Optional[str] = None
    company_code: Optional[str] = None
    project_id: Optional[int] = None
    registered: bool = False
    current_state: Optional[str] = None

class LineUserCreateSchema(LineUserBaseSchema):
    pass

class LineUserSchema(LineUserBaseSchema):
    id: int

    class Config:
        from_attributes = True
