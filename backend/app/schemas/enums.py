from enum import Enum

class CultivarEnum(str, Enum):
    LAKATAN = "Lakatan"
    LATUNDAN = "Latundan"
    CARDABA = "Cardaba"

class RipenessEnum(str, Enum):
    UNRIPE = "Unripe"
    SEMI_RIPE = "Semi Ripe"
    RIPE = "Ripe"
    OVERRIPE = "Overripe"

class TreatmentEnum(str, Enum):
    NATURAL = "Natural"
    ETHEPHON = "Ethephon"

class RoleEnum(str, Enum):
    ADMIN = "Admin"
    OPERATOR = "Operator"

class InventoryStatusEnum(str, Enum):
    IN_STOCK = "In Stock"
    SOLD = "Sold"
    FOR_PROCESSING = "For Processing"
    SPOILED = "Spoiled"

class ActiveStatusEnum(str, Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"

class DeviceStatusEnum(str, Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"

class IntakeStatusEnum(str, Enum):
    ACTIVE = "Active"
    DEPLETED = "Depleted"

class PasswordSetupReasonEnum(str, Enum):
    NEW_ACCOUNT = "new_account"
    PASSWORD_RESET = "password_reset"

class PinSetupReasonEnum(str, Enum):
    NEW_ACCOUNT = "new_account"
    PIN_RESET = "pin_reset"
