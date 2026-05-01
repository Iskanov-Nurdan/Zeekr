HALAL = "halal"
HARAM = "haram"
DOUBTFUL = "doubtful"
UNKNOWN = "unknown"

STATUS_CHOICES = [
    (HALAL, "Halal"),
    (HARAM, "Haram"),
    (DOUBTFUL, "Doubtful"),
    (UNKNOWN, "Unknown"),
]

CHECK_TYPE_PRODUCT = "product"
CHECK_TYPE_INGREDIENT = "ingredient"
CHECK_TYPE_BRAND = "brand"
CHECK_TYPE_OCR = "ocr"

CHECK_TYPE_CHOICES = [
    (CHECK_TYPE_PRODUCT, "Product"),
    (CHECK_TYPE_INGREDIENT, "Ingredient"),
    (CHECK_TYPE_BRAND, "Brand"),
    (CHECK_TYPE_OCR, "OCR"),
]

SOURCE_INTERNAL = "internal"
SOURCE_EXTERNAL = "external"
SOURCE_AI = "ai"
SOURCE_OCR = "ocr"

SOURCE_CHOICES = [
    (SOURCE_INTERNAL, "Internal reference"),
    (SOURCE_EXTERNAL, "External source"),
    (SOURCE_AI, "AI analysis"),
    (SOURCE_OCR, "OCR import"),
]

ORIGIN_PLANT = "plant"
ORIGIN_ANIMAL = "animal"
ORIGIN_SYNTHETIC = "synthetic"
ORIGIN_MICROBIAL = "microbial"
ORIGIN_UNKNOWN = "unknown"

ORIGIN_CHOICES = [
    (ORIGIN_PLANT, "Plant"),
    (ORIGIN_ANIMAL, "Animal"),
    (ORIGIN_SYNTHETIC, "Synthetic"),
    (ORIGIN_MICROBIAL, "Microbial"),
    (ORIGIN_UNKNOWN, "Unknown"),
]

BOYCOTT_NONE = "none"
BOYCOTT_ACTIVE = "active"
BOYCOTT_REVIEW = "review"

BOYCOTT_CHOICES = [
    (BOYCOTT_NONE, "None"),
    (BOYCOTT_ACTIVE, "Active"),
    (BOYCOTT_REVIEW, "Under review"),
]

PRODUCT_CATEGORY_CHOICES = [
    ("beverages", "Beverages"),
    ("sweets", "Sweets"),
    ("dairy", "Dairy"),
    ("sauces", "Sauces"),
    ("fast_food", "Fast food"),
    ("cosmetics", "Cosmetics"),
    ("medicine", "Medicine"),
    ("supplements", "Supplements"),
    ("semi_finished", "Semi-finished"),
    ("meat", "Meat"),
    ("baby", "Baby products"),
    ("other", "Other"),
]

