"""Standard USDA E-WIC Fallback Category Database.

Used when an active APL file is not supplied or when a category/subcategory
is missing from the provided APL catalog.
"""

from typing import Dict, Any, Tuple

# Standard USDA 2-digit category definitions
# Category -> (Description, Default UOM, is_currency)
USDA_CATEGORY_MAP: Dict[str, Tuple[str, str, bool]] = {
    "01": ("Formula", "CAN", False),
    "02": ("Cheese/Tofu", "LB", False),
    "03": ("Eggs", "DOZ", False),
    "04": ("Juice", "OZ", False),
    "05": ("Adult Cereal", "OZ", False),
    "06": ("Legumes", "JBG", False),
    "07": ("Peanut Butter", "JAR", False),
    "08": ("Fish", "OZ", False),
    "09": ("Infant Cereal", "BOX", False),
    "12": ("Infant Fruits/Vegetables", "OZ", False),
    "13": ("Infant Meats", "JAR", False),
    "16": ("Whole Grains/Bread", "OZ", False),
    "19": ("Whole Grains", "OZ", False),
    "21": ("Infant Formula", "CAN", False),
    "31": ("Exempt Infant Formula", "CAN", False),
    "41": ("WIC Eligible Nutritionals", "PKG", False),
    "49": ("Plant-Based Milk Alternatives", "GAL", False),
    "50": ("CVB Produce", "$$$", True),
    "51": ("Milk Whole", "GAL", False),
    "52": ("Infant Produce", "OZ", False),
    "54": ("Infant Cereal", "OZ", False),
}

# Subcategory override lookup: (cat, subcat) -> (Description, UOM, is_currency)
USDA_SUBCAT_OVERRIDES: Dict[Tuple[str, str], Tuple[str, str, bool]] = {
    # Nevada / Southwest State Variations
    ("19", "000"): ("Fruits & Veg CVV", "$$$", True),
    ("19", "001"): ("Fruits & Veg CVV", "$$$", True),
    ("50", "000"): ("Yogurt", "OZ", False),
    ("50", "001"): ("Yogurt-Whole Milk", "OZ", False),
    ("50", "002"): ("Yogurt-Low/Non-Fat", "OZ", False),
    ("52", "000"): ("Milk LowFat / Skim", "GAL", False),
    ("52", "002"): ("Fluid Milk 1%/FF", "GAL", False),
    ("54", "000"): ("Juice 64 oz", "CBL", False),
    ("54", "002"): ("Juice 64 oz", "CBL", False),
}


def resolve_category(cat: str, subcat: str = "000", is_nv_schema: bool = False) -> Dict[str, Any]:
    """Resolve category and subcategory info using USDA standards or regional overrides."""
    cat_padded = str(cat).zfill(2)
    subcat_padded = str(subcat).zfill(3)

    # Check regional overrides if flagged or present
    if (cat_padded, subcat_padded) in USDA_SUBCAT_OVERRIDES:
        desc, uom, is_curr = USDA_SUBCAT_OVERRIDES[(cat_padded, subcat_padded)]
        return {
            "cat": cat_padded,
            "subcat": subcat_padded,
            "description": desc,
            "uom": uom,
            "is_currency": is_curr
        }

    # Standard USDA fallback
    if cat_padded in USDA_CATEGORY_MAP:
        desc, uom, is_curr = USDA_CATEGORY_MAP[cat_padded]
        return {
            "cat": cat_padded,
            "subcat": subcat_padded,
            "description": desc,
            "uom": uom,
            "is_currency": is_curr
        }

    # Generic fallback for unknown category
    return {
        "cat": cat_padded,
        "subcat": subcat_padded,
        "description": f"Category {cat_padded}",
        "uom": "EA",
        "is_currency": False
    }


def format_balance(amount: float, is_currency: bool = False, uom: str = "") -> str:
    """Format numeric balance as currency or unit quantity."""
    if is_currency or uom == "$$$":
        return f"${amount:,.2f}"
    return f"{amount:,.2f}"

