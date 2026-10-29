"""APL (Approved Product List) Parser and In-Memory Lookup Engine.

Parses USDA / State WIC Direct Store Delivery fixed-width APL files
(specifically D4 item records and D6 category hierarchy records).
Provides fast normalization, UPC/PLU resolution, and window-level session caching.
"""

import os
import glob
from typing import Dict, Any, Optional, List, Tuple
from .usda_fallback import resolve_category


class APLDatabase:
    """In-memory index for a single parsed APL file."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.agency_code: str = ""
        self.effective_date: str = ""

        # UPC Lookups: key -> dict of item attributes
        # Stores both full 17-digit raw UPCs, stripped UPCs, and PLU keys
        self.upc_map: Dict[str, Dict[str, Any]] = {}

        # Category Lookups: (cat, subcat) -> dict of category metadata
        self.cat_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        self._parse()

    def _parse(self) -> None:
        """Parse fixed-width lines from the APL file."""
        if not os.path.exists(self.file_path):
            return

        with open(self.file_path, "r", encoding="latin1", errors="replace") as f:
            for line in f:
                if len(line) < 10:
                    continue

                rec_type = line[0:2]

                # A1: Header Record
                if rec_type == "A1":
                    # Header contains date and state/agency code
                    self.effective_date = line[8:16].strip()
                    if len(line) >= 60:
                        self.agency_code = line[56:60].strip()

                # D6: Category & Subcategory Definition
                elif rec_type == "D6":
                    if len(line) < 184:
                        continue
                    cat = line[79:81].strip().zfill(2)
                    cat_desc = line[81:131].strip()
                    subcat = line[131:134].strip().zfill(3)
                    subcat_desc = line[134:184].strip()
                    uom = line[184:194].strip() if len(line) >= 194 else ""

                    entry = {
                        "cat": cat,
                        "cat_desc": cat_desc,
                        "subcat": subcat,
                        "subcat_desc": subcat_desc,
                        "uom": uom,
                        "is_currency": (uom == "$$$" or cat == "19")
                    }
                    self.cat_map[(cat, subcat)] = entry
                    # Also map (cat, "000") as a generic category descriptor
                    if (cat, "000") not in self.cat_map:
                        self.cat_map[(cat, "000")] = entry

                # D4: UPC / PLU Item Record
                elif rec_type == "D4":
                    if len(line) < 184:
                        continue
                    raw_upc = line[12:29].strip()
                    desc = line[29:79].strip()
                    cat = line[79:81].strip().zfill(2)
                    cat_desc = line[81:131].strip()
                    subcat = line[131:134].strip().zfill(3)
                    subcat_desc = line[134:184].strip()
                    uom = line[184:194].strip() if len(line) >= 194 else ""
                    size = line[194:204].strip() if len(line) >= 204 else ""
                    size_uom = line[204:214].strip() if len(line) >= 214 else ""

                    item_info = {
                        "raw_upc": raw_upc,
                        "description": desc,
                        "cat": cat,
                        "cat_desc": cat_desc,
                        "subcat": subcat,
                        "subcat_desc": subcat_desc,
                        "uom": uom,
                        "size": size,
                        "size_uom": size_uom,
                        "is_currency": (uom == "$$$" or cat == "19")
                    }

                    # Index by raw 17-char string
                    self.upc_map[raw_upc] = item_info

                    # Index by stripped UPC (no leading zeroes)
                    stripped = raw_upc.lstrip("0")
                    if stripped and stripped not in self.upc_map:
                        self.upc_map[stripped] = item_info

                    # Index produce PLUs (which often start with 100000000000XXXXX)
                    if raw_upc.startswith("100000000000"):
                        plu_tail = raw_upc[12:]
                        if plu_tail not in self.upc_map:
                            self.upc_map[plu_tail] = item_info
                        # Also without last check digit if 5 digits
                        if len(plu_tail) == 5 and plu_tail[:4] not in self.upc_map:
                            self.upc_map[plu_tail[:4]] = item_info

    def lookup_upc(self, upc: str) -> Optional[Dict[str, Any]]:
        """Look up item metadata for a given UPC or PLU string."""
        if not upc:
            return None

        clean_upc = str(upc).strip()

        # 1. Direct match
        if clean_upc in self.upc_map:
            return self.upc_map[clean_upc]

        # 2. Stripped leading zeroes
        stripped = clean_upc.lstrip("0")
        if stripped in self.upc_map:
            return self.upc_map[stripped]

        # 3. 17-digit zero padded
        padded_17 = clean_upc.zfill(17)
        if padded_17 in self.upc_map:
            return self.upc_map[padded_17]

        # 4. PLU produce check: if leading zeros were stripped, try trailing 4-5 digits
        if len(stripped) <= 6:
            if stripped in self.upc_map:
                return self.upc_map[stripped]
            # Try with produce prefix '1' padded to 17 digits
            plu_padded = ("1" + clean_upc.zfill(16))[-17:]
            if plu_padded in self.upc_map:
                return self.upc_map[plu_padded]

        # 5. Check if stripped without check digit matches
        if len(stripped) > 4:
            no_chk = stripped[:-1]
            if no_chk in self.upc_map:
                return self.upc_map[no_chk]

        return None

    def lookup_category(self, cat: str, subcat: str = "000") -> Dict[str, Any]:
        """Look up category metadata from APL, with fallback to USDA standards."""
        cat_p = str(cat).zfill(2)
        subcat_p = str(subcat).zfill(3)

        # 1. Exact match (cat, subcat)
        if (cat_p, subcat_p) in self.cat_map:
            ent = self.cat_map[(cat_p, subcat_p)]
            return {
                "cat": cat_p,
                "subcat": subcat_p,
                "description": ent["cat_desc"] or ent["subcat_desc"],
                "subcat_desc": ent["subcat_desc"],
                "uom": ent["uom"],
                "is_currency": ent["is_currency"]
            }

        # 2. General category match (cat, "000")
        if (cat_p, "000") in self.cat_map:
            ent = self.cat_map[(cat_p, "000")]
            return {
                "cat": cat_p,
                "subcat": subcat_p,
                "description": ent["cat_desc"],
                "subcat_desc": ent["subcat_desc"],
                "uom": ent["uom"],
                "is_currency": ent["is_currency"]
            }

        # 3. Fallback to standard USDA definitions
        return resolve_category(cat_p, subcat_p)


# Global window session cache: window_id -> APLDatabase
_WINDOW_APL_CACHE: Dict[int, APLDatabase] = {}


def get_cached_apl(window_id: int) -> Optional[APLDatabase]:
    """Retrieve active APL database for the specified window session."""
    return _WINDOW_APL_CACHE.get(window_id)


def set_cached_apl(window_id: int, apl_db: APLDatabase) -> None:
    """Store active APL database for the specified window session."""
    _WINDOW_APL_CACHE[window_id] = apl_db


def clear_apl_cache(window_id: Optional[int] = None) -> None:
    """Clear cached APL database for a window or all windows."""
    if window_id is not None:
        _WINDOW_APL_CACHE.pop(window_id, None)
    else:
        _WINDOW_APL_CACHE.clear()


def discover_candidate_apls(active_file_path: Optional[str] = None, project_folders: Optional[List[str]] = None) -> List[str]:
    """Search for candidate *.apl and *apl*.txt files locally."""
    candidates = []
    seen = set()

    search_dirs = []
    if active_file_path and os.path.isfile(active_file_path):
        search_dirs.append(os.path.dirname(active_file_path))

    if project_folders:
        for folder in project_folders:
            if os.path.isdir(folder) and folder not in search_dirs:
                search_dirs.append(folder)

    for s_dir in search_dirs:
        # Search direct directory and immediate subdirectories
        patterns = [
            os.path.join(s_dir, "*.apl"),
            os.path.join(s_dir, "*apl*.txt"),
            os.path.join(s_dir, "*", "*.apl"),
            os.path.join(s_dir, "*", "*apl*.txt"),
        ]
        for pat in patterns:
            for p in glob.glob(pat):
                norm = os.path.normpath(p)
                if norm not in seen and os.path.isfile(norm):
                    seen.add(norm)
                    candidates.append(norm)

    return sorted(candidates)

