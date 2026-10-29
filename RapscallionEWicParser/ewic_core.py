"""Core E-WIC Protocol Parser, Multi-State TLV Decoder & Log Aggregation Engine.

Handles Buypass / FIS retail POS logs (*.sls), extracts E-WIC transaction cycles,
correlates inquiry and settlement events, extracts line items, and performs
reconciliation against Approved Product Lists (APL) or USDA fallbacks.
"""

import re
import os
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Sequence, Set
from .usda_fallback import resolve_category, format_balance
from .apl_parser import APLDatabase


@dataclass
class LogEventRecord:
    """Represents a milestone event in an E-WIC transaction cycle."""
    line_no: int
    timestamp: str
    event_type: str
    summary: str
    raw_tag: str = ""


def extract_timestamp(line: str) -> str:
    """Extract ts='HH:MM:SS.mmm' from log line if present."""
    m = re.search(r'ts="([^"]+)"', line)
    return m.group(1) if m else ""


class EWICLineItem:
    """Represents a scanned basket item within an E-WIC transaction."""

    def __init__(self, line_no: int, upc: str, qty: float, price: float, log_line: int = 0):
        self.line_no = line_no
        self.upc = upc
        self.qty = qty
        self.price = price
        self.log_line = log_line
        self.description = ""
        self.cat = ""
        self.subcat = ""
        self.uom = ""
        self.wic_paid = 0.0

    def resolve_with_apl(self, apl_db: Optional[APLDatabase]) -> None:
        """Resolve item description, category, and UOM using APL if available."""
        if apl_db:
            info = apl_db.lookup_upc(self.upc)
            if info:
                self.description = info.get("description", "")
                self.cat = info.get("cat", "")
                self.subcat = info.get("subcat", "")
                self.uom = info.get("uom", "")
                return

        # Fallback if no APL or item not in APL
        if not self.description:
            # Check if produce PLU (e.g. 4011, 4225, etc.)
            clean_upc = self.upc.lstrip("0")
            if len(clean_upc) in (4, 5):
                self.description = f"PLU {clean_upc}"
            else:
                self.description = f"UPC {self.upc}"


class EWICTransactionCycle:
    """Encapsulates a full E-WIC cycle: Inquiry -> Basket -> Settlement -> Balance."""

    def __init__(self, invoice_id: str):
        self.invoice_id = str(invoice_id)
        self.state = "NZ"
        self.terminal_id = ""
        self.store_id = ""
        self.operator_id = ""
        self.card_track = ""
        self.exp_date = ""
        self.preauth_id = ""
        self.inquiry_sequence_no: Optional[str] = None
        self.auth_id = ""
        self.auth_display = ""
        self.status = "APPROVED"
        self.wic_amount = 0.0
        self.org_amount = 0.0
        self.bank_name: str = ""
        self.log_version: str = "V3"
        self.is_inquiry_only: bool = False

        # Correlation tokens
        self.client_tokens: List[str] = []
        self.sequence_no = ""

        # Balances: (cat, subcat) -> float balance
        self.inquiry_balances: Dict[Tuple[str, str], float] = {}
        self.settled_balances: Dict[Tuple[str, str], float] = {}

        # Basket items
        self.items: List[EWICLineItem] = []

        # Line tracking in log file
        self.inquiry_line = 0
        self.settlement_line = 0
        self.events: List[LogEventRecord] = []

        # Reconciled rows: list of dicts
        self.reconciled_rows: List[Dict[str, Any]] = []

    def reconcile(self, apl_db: Optional[APLDatabase] = None, show_zeros: bool = True) -> None:
        """Calculate deductions and map categories to descriptions and UOMs."""
        # 1. Resolve items
        total_items_price = sum(item.price for item in self.items)
        for item in self.items:
            item.resolve_with_apl(apl_db)
            # If single item, it receives the full paid amount
            if len(self.items) == 1:
                item.wic_paid = self.wic_amount if self.wic_amount > 0 else item.price
            elif total_items_price > 0 and self.wic_amount > 0:
                # Proportional or equal share
                ratio = min(1.0, self.wic_amount / total_items_price)
                item.wic_paid = round(item.price * ratio, 2)
            else:
                item.wic_paid = item.price

        # Update event descriptions for items if resolved
        for ev in self.events:
            if ev.event_type.startswith("Basket Item #"):
                m_no = re.search(r'#(\d+)', ev.event_type)
                if m_no:
                    l_no = int(m_no.group(1))
                    match_item = next((it for it in self.items if it.line_no == l_no), None)
                    if match_item and match_item.description:
                        ev.summary = f"Xml line item (UPC {match_item.upc} - {match_item.description}, Shelf ${match_item.price:,.2f})"

        # 2. Reconcile balances
        all_keys = set(self.inquiry_balances.keys()) | set(self.settled_balances.keys())
        rows = []

        for cat, subcat in sorted(all_keys):
            init_bal = self.inquiry_balances.get((cat, subcat), 0.0)
            if self.is_inquiry_only:
                deducted = 0.0
                rem_bal = init_bal
            else:
                rem_bal = self.settled_balances.get((cat, subcat), init_bal)
                deducted = round(init_bal - rem_bal, 2)
                if deducted < 0:
                    deducted = 0.0

            if not show_zeros and init_bal == 0 and deducted == 0:
                continue

            # Lookup metadata from APL or USDA fallback
            if apl_db:
                cat_info = apl_db.lookup_category(cat, subcat)
            else:
                cat_info = resolve_category(cat, subcat)

            desc = cat_info.get("description", f"Category {cat}")
            uom = cat_info.get("uom", "EA")
            is_curr = cat_info.get("is_currency", False) or uom == "$$$"

            rows.append({
                "cat": cat,
                "subcat": subcat,
                "cat_sub": f"{cat}/{subcat}",
                "description": desc,
                "initial": init_bal,
                "deducted": deducted,
                "remaining": rem_bal,
                "uom": uom,
                "is_currency": is_curr
            })

        self.reconciled_rows = rows


def parse_tlv_string(
    raw_text: str,
    default_state: str = "NZ",
    state_prefix_map: Optional[Dict[str, str]] = None
) -> Tuple[Dict[Tuple[str, str], float], Optional[str], Optional[str]]:
    """Parse raw TLV string containing EA (balance) and EF (expiration) tags.

    Supports nationwide multi-state schema formats:
    - 14-digit value: [3-digit state prefix] + [3-digit cat] + [3-digit subcat] + [5-digit qty]
    - 13-digit value: [2-digit state prefix] + [3-digit cat] + [3-digit subcat] + [5-digit qty]
    - 11-digit value: [3-digit cat] + [3-digit subcat] + [5-digit qty]

    Returns:
        (balances_dict, expiration_date_str, detected_state_code)
    """
    balances: Dict[Tuple[str, str], float] = {}
    exp_date: Optional[str] = None
    detected_state = default_state

    # Clean enclosing attributes if passed like dat="..." (V3) or |dat:... (V4)
    if "|dat:" in raw_text:
        content = raw_text.split("|dat:", 1)[1].strip()
    elif 'dat="' in raw_text:
        m_dat = re.search(r'dat="([^"]+)"', raw_text)
        content = m_dat.group(1) if m_dat else raw_text
    elif "dat:" in raw_text:
        content = raw_text.split("dat:", 1)[1].strip()
    else:
        content = raw_text

    # Strip prefixes like [SMSPayStatus] or other brackets if present
    content = re.sub(r'^\[[^\]]+\]\s*', '', content)

    # Extract state token if present in the text (e.g., /PAYWICSTATE=NZ or BIN: ...,NZ)
    m_st = re.search(r'/(?:PAYWICSTATE|WICONLY)=([A-Z]{2})', raw_text)
    if not m_st:
        m_st = re.search(r'BIN:\s*\d+,([A-Z]{2})', raw_text)
    if m_st:
        detected_state = m_st.group(1)

    # Invert state prefix map to find state from prefix if needed
    prefix_to_state: Dict[str, str] = {}
    if state_prefix_map:
        for st, pfx in state_prefix_map.items():
            prefix_to_state[pfx] = st

    i = 0
    while i < len(content):
        tag = content[i:i+2]
        if not tag.isalnum() or len(content) < i + 5:
            # Resync to next known tag
            m = re.search(r'(EA|EF|PS)(\d{3})', content[i+1:])
            if m:
                i = i + 1 + m.start()
                continue
            break

        try:
            length = int(content[i+2:i+5])
        except ValueError:
            m = re.search(r'(EA|EF|PS)(\d{3})', content[i+1:])
            if m:
                i = i + 1 + m.start()
                continue
            break

        val = content[i+5:i+5+length]
        i += 5 + length

        # TAG EA: E-WIC Balance Record
        if tag == "EA":
            if len(val) == 14:
                # 14-digit format: 3 state + 3 cat + 3 subcat + 5 balance
                state_pfx = val[:3]
                if state_pfx in prefix_to_state:
                    detected_state = prefix_to_state[state_pfx]

                cat_num = int(val[3:6])
                cat = str(cat_num).zfill(2)
                subcat = val[6:9]
                qty_raw = int(val[9:14])
                qty = qty_raw / 100.0
                balances[(cat, subcat)] = qty

            elif len(val) == 13:
                # 13-digit format: 2 state + 3 cat + 3 subcat + 5 balance
                cat_num = int(val[2:5])
                cat = str(cat_num).zfill(2)
                subcat = val[5:8]
                qty_raw = int(val[8:13])
                qty = qty_raw / 100.0
                balances[(cat, subcat)] = qty

            elif len(val) == 11:
                # 11-digit format: 3 cat + 3 subcat + 5 balance
                cat_num = int(val[0:3])
                cat = str(cat_num).zfill(2)
                subcat = val[3:6]
                qty_raw = int(val[6:11])
                qty = qty_raw / 100.0
                balances[(cat, subcat)] = qty

        # TAG EF: Benefit Expiration Date
        elif tag == "EF":
            if len(val) >= 8:
                raw_exp = val[:8]
                if raw_exp.isdigit():
                    exp_date = f"{raw_exp[0:4]}-{raw_exp[4:6]}-{raw_exp[6:8]}"
                else:
                    exp_date = raw_exp

    return balances, exp_date, detected_state


def detect_bank_name(lines: Sequence[str]) -> str:
    """Detect the bank processor / driver name from log header and tokens."""
    for line in lines[:150]:
        m = re.search(r'cap="In(?:i|it)"\s+dat="([^"]+)"', line)
        if not m:
            m = re.search(r'cap:Ini(?: for Setup)?\|dat:([^\r\n|]+)', line)
        if m:
            ini = m.group(1).lower()
            if "buypass" in ini:
                return "Buypass / FIS"
            elif "worldpay" in ini or "vantiv" in ini:
                return "Worldpay ISO"
            elif "rbs" in ini or "lynk" in ini:
                return "RBSLynk ISO"
            elif "wineps" in ini or "openeps" in ini:
                return "WinEPS"
            return m.group(1)

        # V3 XML tags
        if "<ApiBuypass" in line:
            return "Buypass / FIS"
        if "<ApiRBS" in line or "<ApiLynk" in line:
            return "RBSLynk ISO"
        if "<ApiWinEps" in line or "<ApiOpenEps" in line:
            return "WinEPS"

        # V4 Source components
        if "sc:ApiBuypass" in line:
            return "Buypass / FIS"
        if "sc:ApiPayWorldpay" in line or "sc:ApiWorldpay" in line:
            return "Worldpay ISO"
        if "sc:ApiWinEps" in line:
            return "WinEPS"
        if "sc:ApiRBS" in line or "sc:ApiLynk" in line:
            return "RBSLynk ISO"

    for line in lines:
        if "/PAYHOSTNAME=WP" in line or "worldpay" in line.lower() or "vantiv" in line.lower():
            return "Worldpay ISO"
        if "/PAYHOSTNAME=BY" in line or "ApiBuypass" in line:
            return "Buypass / FIS"
        if "/PAYHOSTNAME=RB" in line or "ApiRBS" in line or "lynksystems" in line.lower():
            return "RBSLynk ISO"
        if "/PAYHOSTNAME=WE" in line or "/PAYMENT=WINEPS" in line or "ApiWinEps" in line or "openeps" in line.lower():
            return "WinEPS"

    return "Generic"


def is_ewic_balance_line(line: str) -> bool:
    """Check if line contains an E-WIC balance tag across all bank variants and versions."""
    if ('cap="E-WIC' in line or 'cap:E-WIC' in line) and "BALANCE" in line:
        return True
    if ('cap="SendRequest response"' in line or 'SendRequest response' in line) and "EA014" in line:
        return True
    if (
        'dat="EA014' in line
        or 'dat:EA014' in line
        or 'dat="[SMSPayStatus] EA014' in line
        or "EA014142" in line
        or 'dat:PS047' in line
        or 'dat="PS047' in line
    ):
        return True
    return False


def detect_log_version(lines: Sequence[str], file_path: Optional[str] = None) -> str:
    """Detect log software version format: 'V3' (.sls) or 'V4' (.sl4)."""
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".sl4":
            return "V4"
        elif ext == ".sls":
            return "V3"

    for line in lines[:30]:
        s = line.strip()
        if s.startswith("<Api"):
            return "V3"
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\|sc:", s) or "|sc:Api" in s or "|lv:" in s:
            return "V4"

    return "V3"


def clean_preauth_tokens(raw: str) -> Tuple[str, Optional[str]]:
    """Clean and parse pre-authorization ID and inquiry sequence across banks.

    Handles:
    - Buypass format: '578343' -> ('578343', None)
    - RBSLynk ISO composite format:
      "'094110.251218.052229 00005222925121809411034537412180941100000.052229.345374.0200...'"
      -> ('345374', '052229')
    """
    if not raw:
        return "N/A", None

    val = raw.strip("'\" ")
    if not val:
        return "N/A", None

    # RBSLynk ISO composite format: [time].[date].[inq_seq] [DE59].[inq_seq].[auth_id]...
    if "." in val and " " in val:
        tokens = val.split()
        first_parts = tokens[0].split(".")
        inq_seq = first_parts[2] if len(first_parts) >= 3 else None
        auth_found = None
        if len(tokens) > 1:
            dot_parts = tokens[1].split(".")
            for k in range(len(dot_parts) - 1):
                p1 = dot_parts[k].strip()
                p2 = dot_parts[k+1].strip()
                if re.match(r"^\d{4,8}$", p1) and re.match(r"^\d{4,8}$", p2):
                    inq_seq = p1
                    auth_found = p2
                    break
        auth_id = auth_found or (first_parts[2] if len(first_parts) >= 3 else val)
        return auth_id, inq_seq

    return val, None


class LogAuditScanner:
    """Scans and correlates POS log buffers (Buypass / FIS, RBSLynk ISO, etc.) into E-WIC cycles."""

    def __init__(
        self,
        lines: List[str],
        default_state: str = "NZ",
        state_prefix_map: Optional[Dict[str, str]] = None,
        lookback_limit: int = 1500
    ):
        self.lines = lines
        self.default_state = default_state
        self.state_prefix_map = state_prefix_map or {"NZ": "142", "NV": "142"}
        self.lookback_limit = lookback_limit
        self.bank_name = detect_bank_name(lines)
        self.log_version = detect_log_version(lines)

    def scan(self, target_invoice: Optional[str] = None) -> List[EWICTransactionCycle]:
        """Scan buffer and return correlated E-WIC transaction cycles (both purchases and standalone inquiries)."""
        cycles: List[EWICTransactionCycle] = []
        settlement_indices: List[Tuple[int, str]] = []
        processed_inquiry_lines: Set[int] = set()

        clean_target = str(target_invoice).strip() if target_invoice else None

        # 1. Identify all settlement responses (PAYTRANCODE=2)
        for idx, line in enumerate(self.lines):
            if "PAY Response" in line and "/PAYTRANCODE=2" in line:
                # Extract invoice number from line or preceding request
                inv_match = re.search(r'/(?:PAYINVOICE|F1032|FIL1)=(\d+)', line)
                if not inv_match:
                    # Check filename in /PAYOUTPUT
                    inv_match = re.search(r'_S0*(\d+)(?:_|\.|\b)', line)

                # If still not found, inspect preceding request
                if not inv_match and idx > 0:
                    for prev_i in range(max(0, idx - 15), idx):
                        prev_line = self.lines[prev_i]
                        inv_match = re.search(r'/(?:PAYINVOICE|F1032|FIL1)=(\d+)', prev_line)
                        if inv_match:
                            break
                        inv_match = re.search(r'_S0*(\d+)(?:_|\.|\b)', prev_line)
                        if inv_match:
                            break

                if inv_match:
                    inv_id = str(int(inv_match.group(1)))  # Normalize away leading zeros

                    # Deduplicate consecutive response entries for the same invoice within 2 lines (e.g. V4 dual logging)
                    if settlement_indices and settlement_indices[-1][1] == inv_id and (idx - settlement_indices[-1][0]) <= 2:
                        settlement_indices[-1] = (idx, inv_id)
                        continue

                    settlement_indices.append((idx, inv_id))

        # 2. For each settlement, correlate backward
        for set_idx, inv_id in settlement_indices:
            cycle = self._correlate_cycle(set_idx, inv_id)
            if cycle:
                if clean_target is not None:
                    norm_target = str(int(clean_target)) if clean_target.isdigit() else clean_target
                    matches = False
                    for cid in (cycle.invoice_id, cycle.sequence_no, cycle.auth_id, cycle.preauth_id):
                        if cid:
                            norm_cid = str(int(cid)) if cid.isdigit() else cid
                            if norm_cid == norm_target:
                                matches = True
                                break
                    if not matches:
                        continue

                cycles.append(cycle)
                if cycle.inquiry_line > 0:
                    processed_inquiry_lines.add(cycle.inquiry_line - 1)

        # 3. Identify standalone WIC balance inquiries (not part of any settlement cycle)
        for idx, line in enumerate(self.lines):
            if "PAY Response" in line and (
                "/PRN=TRS_POS_Bank_eWIC_Inquiry" in line
                or ("/CARDTYPE=W" in line and ("/PAYTRANCODE=6" in line or "/PAYTRANCODE=1" in line))
                or ("/PAYFUNCTION=119" in line and "/PAYTRANCODE=6" in line)
            ):
                # Find request line
                inq_req_idx = idx
                for prev_i in range(max(0, idx - 100), idx):
                    p_line = self.lines[prev_i]
                    if ("PAY Request" in p_line or "SmsPayRequest" in p_line) and (
                        "/PAYTRANCODE=6" in p_line or "/PAYTRANCODE=1" in p_line or "/PRN=TRS_POS_Bank_eWIC_Inquiry" in p_line
                    ):
                        inq_req_idx = prev_i
                        break

                if inq_req_idx in processed_inquiry_lines or idx in processed_inquiry_lines:
                    continue

                inq_cycle = self._build_standalone_inquiry_cycle(idx, inq_req_idx)
                if inq_cycle:
                    # Targeted check if requested
                    if clean_target is not None:
                        norm_target = str(int(clean_target)) if clean_target.isdigit() else clean_target
                        matches = False
                        for cid in (inq_cycle.invoice_id, inq_cycle.sequence_no, inq_cycle.auth_id):
                            if cid:
                                norm_cid = str(int(cid)) if cid.isdigit() else cid
                                if norm_cid == norm_target:
                                    matches = True
                                    break
                        if not matches:
                            continue

                    cycles.append(inq_cycle)
                    processed_inquiry_lines.add(inq_req_idx)
                    processed_inquiry_lines.add(idx)

        # Sort cycles by appearance in file
        cycles.sort(key=lambda c: c.settlement_line or c.inquiry_line)
        return cycles

    def _build_standalone_inquiry_cycle(self, resp_idx: int, req_idx: int) -> Optional[EWICTransactionCycle]:
        """Construct an EWICTransactionCycle for a standalone WIC balance inquiry."""
        resp_line = self.lines[resp_idx]

        m_seq = re.search(r'/PAYSEQUENCE=([^\s/]+)', resp_line)
        seq_no = m_seq.group(1).strip("'\" ") if m_seq else ""

        m_auth = re.search(r'/AUTHID=([^\s/]+)', resp_line)
        auth_id = m_auth.group(1).strip("'\" ") if m_auth else ""

        inv_id = seq_no or auth_id or f"Inq-{resp_idx + 1}"

        cycle = EWICTransactionCycle(inv_id)
        cycle.is_inquiry_only = True
        cycle.settlement_line = resp_idx + 1
        cycle.inquiry_line = req_idx + 1
        cycle.bank_name = self.bank_name
        cycle.log_version = self.log_version
        cycle.sequence_no = seq_no
        cycle.auth_id = auth_id

        m_state = re.search(r'/(?:PAYWICSTATE|WICONLY)=([A-Z]{2})', resp_line)
        if m_state:
            cycle.state = m_state.group(1)

        m_term = re.search(r'/PAYTERMID=([^\s/]+)', resp_line)
        if m_term:
            cycle.terminal_id = m_term.group(1)

        m_store = re.search(r'/PAYSTOREID=([^\s/]+)', resp_line)
        if m_store:
            cycle.store_id = m_store.group(1)

        m_oper = re.search(r'/PAYOPERID=([^\s/]+)', resp_line)
        if m_oper:
            cycle.operator_id = m_oper.group(1)

        m_disp = re.search(r"/PAYDISPLAY=(?:'([^']*)'|\"([^\"]*)\"|([^\s/>]+))", resp_line)
        if m_disp:
            cycle.auth_display = (m_disp.group(1) or m_disp.group(2) or m_disp.group(3) or "").strip("'\" ")

        bal_line_idx = None
        # Look for balance tag around the inquiry (up to 50 lines before or after)
        for b_i in range(max(0, req_idx - 10), min(len(self.lines), resp_idx + 25)):
            b_line = self.lines[b_i]
            if is_ewic_balance_line(b_line):
                bals, exp, st = parse_tlv_string(b_line, cycle.state, self.state_prefix_map)
                if bals:
                    cycle.inquiry_balances = bals
                    cycle.settled_balances = bals  # No deductions occurred in standalone inquiry
                    bal_line_idx = b_i
                if exp:
                    cycle.exp_date = exp
                if st and not cycle.state:
                    cycle.state = st
                if bals:
                    break

        if not cycle.inquiry_balances:
            return None

        # Build chronological event trace
        is_v4 = (self.log_version == "V4")
        t_req = "cap:PAY Request" if is_v4 else 'cap="PAY Request"'
        t_resp = "cap:PAY Response" if is_v4 else 'cap="PAY Response"'
        t_bal = "cap:E-WIC (BALANCE)" if is_v4 else 'cap="E-WIC (BALANCE)"'

        req_line = self.lines[req_idx]
        cycle.events.append(LogEventRecord(
            line_no=req_idx + 1,
            timestamp=extract_timestamp(req_line),
            event_type="Inquiry Request",
            summary=f"PAY Request (/PRN=eWIC_Inquiry, Term {cycle.terminal_id or 'N/A'}, Store {cycle.store_id or 'N/A'})",
            raw_tag=t_req
        ))

        if bal_line_idx is not None:
            bal_line = self.lines[bal_line_idx]
            cycle.events.append(LogEventRecord(
                line_no=bal_line_idx + 1,
                timestamp=extract_timestamp(bal_line),
                event_type="Initial Balances",
                summary=f"E-WIC Balance Record ({len(cycle.inquiry_balances)} categories loaded, Exp: {cycle.exp_date or 'N/A'})",
                raw_tag=t_bal
            ))

        cycle.events.append(LogEventRecord(
            line_no=resp_idx + 1,
            timestamp=extract_timestamp(resp_line),
            event_type="Inquiry Response",
            summary=f"PAY Response ({cycle.auth_display or 'Approved'}, Auth: {cycle.auth_id or 'N/A'}, Seq: {cycle.sequence_no or 'N/A'})",
            raw_tag=t_resp
        ))

        cycle.events.sort(key=lambda ev: ev.line_no)
        return cycle

    def _correlate_cycle(self, set_resp_idx: int, inv_id: str) -> Optional[EWICTransactionCycle]:
        """Correlate a single transaction cycle starting from settlement response."""
        cycle = EWICTransactionCycle(inv_id)
        cycle.settlement_line = set_resp_idx + 1
        cycle.bank_name = self.bank_name
        cycle.log_version = self.log_version

        set_resp_line = self.lines[set_resp_idx]

        # Extract settlement response parameters
        m_state = re.search(r'/(?:PAYWICSTATE|WICONLY)=([A-Z]{2})', set_resp_line)
        if m_state:
            cycle.state = m_state.group(1)

        m_term = re.search(r'/PAYTERMID=([^\s/]+)', set_resp_line)
        if m_term:
            cycle.terminal_id = m_term.group(1)

        m_store = re.search(r'/PAYSTOREID=([^\s/]+)', set_resp_line)
        if m_store:
            cycle.store_id = m_store.group(1)

        m_oper = re.search(r'/PAYOPERID=([^\s/]+)', set_resp_line)
        if m_oper:
            cycle.operator_id = m_oper.group(1)

        m_auth = re.search(r'/(?:AUTHID|AUTH)=([^\s/]+)', set_resp_line)
        if m_auth:
            cycle.auth_id = m_auth.group(1).strip("'\" ")
        else:
            # Check nearby lines for AuthorizationNumber=... (e.g. WinEPS V4)
            for near_i in range(max(0, set_resp_idx - 30), min(len(self.lines), set_resp_idx + 10)):
                m_auth_near = re.search(r'AuthorizationNumber=([^\s|]+)', self.lines[near_i])
                if m_auth_near:
                    cycle.auth_id = m_auth_near.group(1).strip("'\" ")
                    break

        m_disp = re.search(r"/PAYDISPLAY=(?:'([^']*)'|([^\s/]+))", set_resp_line)
        if m_disp:
            cycle.auth_display = (m_disp.group(1) or m_disp.group(2) or "").strip()

        # Pre-auth parsing (handles both Buypass and RBSLynk ISO formats)
        m_preauth = re.search(r'/PAYPREAUTHID=(?:\'([^\']*)\'|"([^"]*)"|([^\s/]+))', set_resp_line)
        if m_preauth:
            raw_p = (m_preauth.group(1) or m_preauth.group(2) or m_preauth.group(3) or "").strip("'\" ")
            auth_id, inq_seq = clean_preauth_tokens(raw_p)
            cycle.preauth_id = auth_id
            cycle.inquiry_sequence_no = inq_seq

        m_seq = re.search(r'/PAYSEQUENCE=([^\s/]+)', set_resp_line)
        if m_seq:
            cycle.sequence_no = m_seq.group(1)

        m_amnt = re.search(r'/PAYAMNT=([\d.]+)', set_resp_line)
        if m_amnt:
            try:
                cycle.wic_amount = float(m_amnt.group(1))
            except ValueError:
                pass

        m_org = re.search(r'/PAYORGAMNT=([\d.]+)', set_resp_line)
        if m_org:
            try:
                cycle.org_amount = float(m_org.group(1))
            except ValueError:
                pass

        # Check for client token (/CN=...)
        m_cn = re.search(r'/CN=([A-Z0-9]+)', set_resp_line)
        if m_cn:
            cycle.client_tokens.append(m_cn.group(1))

        # Check for card track mask
        m_trk = re.search(r'/PAYTRACK=([^\s/]+)', set_resp_line)
        if m_trk:
            cycle.card_track = m_trk.group(1)

        # 1. Look back up to 250 lines for settlement request details
        set_req_idx = set_resp_idx
        for prev_i in range(max(0, set_resp_idx - 250), set_resp_idx):
            line = self.lines[prev_i]
            if "PAY Request" in line and "/PAYTRANCODE=2" in line:
                set_req_idx = prev_i
                m_cn_req = re.search(r'/CN=([A-Z0-9]+)', line)
                if m_cn_req and m_cn_req.group(1) not in cycle.client_tokens:
                    cycle.client_tokens.append(m_cn_req.group(1))
                if not cycle.card_track:
                    m_trk_req = re.search(r'/PAYTRACK=([^\s/]+)', line)
                    if m_trk_req:
                        cycle.card_track = m_trk_req.group(1)
                break

        # 2. Scan for settled balance (cap="E-WIC (BALANCE)" right around settlement)
        settled_bal_idx = None
        for b_i in range(max(0, set_req_idx - 25), min(len(self.lines), set_resp_idx + 25)):
            line = self.lines[b_i]
            if is_ewic_balance_line(line):
                bals, exp, st = parse_tlv_string(line, cycle.state, self.state_prefix_map)
                if bals:
                    cycle.settled_balances = bals
                    settled_bal_idx = b_i
                if exp:
                    cycle.exp_date = exp
                if st and not cycle.state:
                    cycle.state = st

        # 3. Correlate backward to find the Inquiry (/PAYTRANCODE=1)
        start_lookback = max(0, set_req_idx - self.lookback_limit)
        inquiry_idx = None
        inq_bal_idx = None
        inq_resp_idx = None

        for rev_i in range(set_req_idx - 1, start_lookback - 1, -1):
            line = self.lines[rev_i]

            # Check for Inquiry Request (must have /PAYTRANCODE=1 and NOT /PAYTRANCODE=2)
            if "PAY Request" in line and "/PAYTRANCODE=1" in line:
                # Verify session match via CN, terminal, or card track
                is_match = False
                m_cn_inq = re.search(r'/CN=([A-Z0-9]+)', line)
                if m_cn_inq and m_cn_inq.group(1) in cycle.client_tokens:
                    is_match = True

                m_trk_inq = re.search(r'/PAYTRACK=([^\s/]+)', line)
                if m_trk_inq and cycle.card_track and m_trk_inq.group(1) == cycle.card_track:
                    is_match = True

                # If no CN or card track, match terminal within lookback
                if not is_match and cycle.terminal_id:
                    m_term_inq = re.search(r'/PAYTERMID=([^\s/]+)', line)
                    if m_term_inq and m_term_inq.group(1) == cycle.terminal_id:
                        is_match = True

                if is_match:
                    inquiry_idx = rev_i
                    cycle.inquiry_line = rev_i + 1
                    # Extract initial balance inside or following this inquiry (up to 80 lines forward)
                    for fwd_i in range(inquiry_idx, min(len(self.lines), inquiry_idx + 80)):
                        fwd_line = self.lines[fwd_i]
                        if is_ewic_balance_line(fwd_line):
                            bals, exp, st = parse_tlv_string(fwd_line, cycle.state, self.state_prefix_map)
                            if bals:
                                cycle.inquiry_balances = bals
                                inq_bal_idx = fwd_i
                            if exp and not cycle.exp_date:
                                cycle.exp_date = exp
                            if st and not cycle.state:
                                cycle.state = st
                            if bals:
                                break

                    # Search for inquiry response line (between inquiry_idx and inquiry_idx + 80)
                    for inq_r_i in range(inquiry_idx + 1, min(len(self.lines), inquiry_idx + 80)):
                        inq_r_line = self.lines[inq_r_i]
                        if "PAY Response" in inq_r_line and ("/PAYTRANCODE=1" in inq_r_line or "/PAYTRANCODE=6" in inq_r_line or "/PAYPREAUTHID=" in inq_r_line or ("/AUTHID=" in inq_r_line and "/PAYTRANCODE=2" not in inq_r_line)):
                            inq_resp_idx = inq_r_i
                            break
                    break

        # 4. Scan for XML line items across the entire transaction window
        items_start = inquiry_idx if inquiry_idx is not None else start_lookback
        discovered_items: Dict[int, EWICLineItem] = {}

        for item_i in range(items_start, min(len(self.lines), set_resp_idx + 15)):
            line = self.lines[item_i]
            if 'Xml line item' in line:
                m_line = re.search(r'Line=(\d+)', line)
                m_upc = re.search(r'UPC=([^\s"|]+)', line)
                m_qty = re.search(r'qty=([\d.]+)', line)
                m_price = re.search(r'price=([\d.]+)', line)

                if m_line and m_upc:
                    line_no = int(m_line.group(1))
                    upc = m_upc.group(1)

                    def _parse_val(val_str: Optional[str], default: float) -> float:
                        if not val_str:
                            return default
                        if "." in val_str:
                            return float(val_str)
                        return int(val_str) / 100.0

                    qty = _parse_val(m_qty.group(1) if m_qty else None, 1.0)
                    price = _parse_val(m_price.group(1) if m_price else None, 0.0)

                    if line_no not in discovered_items:
                        discovered_items[line_no] = EWICLineItem(line_no, upc, qty, price, log_line=item_i + 1)

        # Assign items sorted by line number
        cycle.items = [discovered_items[k] for k in sorted(discovered_items.keys())]

        # 5. Build chronological event trace
        is_v4 = (self.log_version == "V4")
        t_req = "cap:PAY Request" if is_v4 else 'cap="PAY Request"'
        t_resp = "cap:PAY Response" if is_v4 else 'cap="PAY Response"'
        t_bal = "cap:E-WIC (BALANCE)" if is_v4 else 'cap="E-WIC (BALANCE)"'
        t_item = "cap:Xml line item" if is_v4 else 'cap="Xml line item"'

        if inquiry_idx is not None:
            inq_line = self.lines[inquiry_idx]
            cycle.events.append(LogEventRecord(
                line_no=inquiry_idx + 1,
                timestamp=extract_timestamp(inq_line),
                event_type="Inquiry Request",
                summary=f"PAY Request (/PAYTRANCODE=1, Term {cycle.terminal_id or 'N/A'}, Store {cycle.store_id or 'N/A'})",
                raw_tag=t_req
            ))

        if inq_bal_idx is not None:
            inq_b_line = self.lines[inq_bal_idx]
            cycle.events.append(LogEventRecord(
                line_no=inq_bal_idx + 1,
                timestamp=extract_timestamp(inq_b_line),
                event_type="Initial Balances",
                summary=f"E-WIC Balance Record ({len(cycle.inquiry_balances)} categories loaded, Exp: {cycle.exp_date or 'N/A'})",
                raw_tag=t_bal
            ))

        if inq_resp_idx is not None:
            inq_r_line = self.lines[inq_resp_idx]
            cycle.events.append(LogEventRecord(
                line_no=inq_resp_idx + 1,
                timestamp=extract_timestamp(inq_r_line),
                event_type="Inquiry Response",
                summary=f"PAY Response (APPROVED, Pre-Auth: {cycle.preauth_id or 'N/A'}, Seq: {cycle.inquiry_sequence_no or 'N/A'})",
                raw_tag=t_resp
            ))

        for item in cycle.items:
            item_line_idx = item.log_line - 1
            item_line_str = self.lines[item_line_idx] if 0 <= item_line_idx < len(self.lines) else ""
            cycle.events.append(LogEventRecord(
                line_no=item.log_line,
                timestamp=extract_timestamp(item_line_str),
                event_type=f"Basket Item #{item.line_no}",
                summary=f"Xml line item (UPC {item.upc}, Shelf ${item.price:,.2f})",
                raw_tag=t_item
            ))

        if set_req_idx != set_resp_idx:
            set_r_line = self.lines[set_req_idx]
            cycle.events.append(LogEventRecord(
                line_no=set_req_idx + 1,
                timestamp=extract_timestamp(set_r_line),
                event_type="Settlement Request",
                summary=f"PAY Request (/PAYTRANCODE=2, Inv #{cycle.invoice_id}, Amnt: ${cycle.wic_amount:,.2f})",
                raw_tag=t_req
            ))

        if settled_bal_idx is not None:
            set_b_line = self.lines[settled_bal_idx]
            cycle.events.append(LogEventRecord(
                line_no=settled_bal_idx + 1,
                timestamp=extract_timestamp(set_b_line),
                event_type="Settled Balances",
                summary=f"E-WIC Balance Record ({len(cycle.settled_balances)} categories updated)",
                raw_tag=t_bal
            ))

        cycle.events.append(LogEventRecord(
            line_no=set_resp_idx + 1,
            timestamp=extract_timestamp(set_resp_line),
            event_type="Settlement Response",
            summary=f"PAY Response ({cycle.auth_display or 'APPROVED'}, Auth: {cycle.auth_id or 'N/A'}, Seq: {cycle.sequence_no or 'N/A'}, Paid: ${cycle.wic_amount:,.2f})",
            raw_tag=t_resp
        ))

        cycle.events.sort(key=lambda ev: ev.line_no)
        return cycle


def render_markdown_report(
    cycles: List[EWICTransactionCycle],
    log_path: str = "Buffer",
    apl_name: Optional[str] = None,
    show_zeros: bool = True,
    highlight_deductions: bool = True,
    bank_name: Optional[str] = None
) -> Tuple[str, str]:
    """Generate Markdown audit report and clean copyable table string.

    Returns:
        (full_markdown_report, clean_clipboard_table)
    """
    if not cycles:
        return ("# E-WIC Audit Report\n\nNo E-WIC transactions discovered in log.", "")

    full_lines: List[str] = []
    clipboard_tables: List[str] = []

    file_display = os.path.basename(log_path) if log_path else "Active Buffer"
    apl_display = apl_name if apl_name else "Standard USDA Fallback"

    detected_bank = bank_name or cycles[0].bank_name or "Generic"
    detected_ver = cycles[0].log_version if cycles else "V3"

    title = f"# {detected_bank} E-WIC Transaction Audit Report" if detected_bank != "Generic" else "# E-WIC Transaction Audit Report"

    full_lines.append(title)
    full_lines.append("")
    full_lines.append(f"- **Log File**: `{file_display}`")
    full_lines.append(f"- **Bank / Processor**: `{detected_bank}`")
    full_lines.append(f"- **Log Format**: `{detected_ver}`")
    full_lines.append(f"- **APL Reference**: `{apl_display}`")
    full_lines.append(f"- **Transactions Found**: {len(cycles)}")
    full_lines.append("")

    for idx, cycle in enumerate(cycles):
        full_lines.append("---")
        if cycle.is_inquiry_only:
            tx_title = f"## Transaction {idx + 1}: Balance Inquiry (Seq: {cycle.sequence_no or cycle.invoice_id} | Auth: {cycle.auth_id or 'APPROVED'})"
        else:
            tx_title = f"## Transaction {idx + 1}: Invoice #{cycle.invoice_id} (F1032: {cycle.invoice_id})"
        full_lines.append(tx_title)
        full_lines.append("")
        if cycle.is_inquiry_only:
            full_lines.append("- **Transaction Type**: `Balance Inquiry (No Basket Items)`")
        full_lines.append(f"- **State / Schema**: `{cycle.state}`")
        full_lines.append(f"- **Terminal / Store**: Term `{cycle.terminal_id or 'N/A'}` | Store `{cycle.store_id or 'N/A'}`")
        full_lines.append(f"- **Benefit Expiration Date**: `{cycle.exp_date or 'N/A'}`")

        if cycle.is_inquiry_only:
            full_lines.append(f"- **Authorization**: `{cycle.auth_id or 'N/A'}` (`{cycle.auth_display or 'APPROVED'}`)")
            full_lines.append(f"- **Sequence Number**: `{cycle.sequence_no or 'N/A'}`")
            full_lines.append("- **Total WIC Paid Amount**: `$0.00 (Inquiry)`")
        else:
            full_lines.append(f"- **Settlement Authorization**: `{cycle.auth_id or 'N/A'}` (`{cycle.auth_display or 'APPROVED'}`)")

            if cycle.preauth_id:
                pre_str = f"`{cycle.preauth_id}` / `{cycle.sequence_no or 'N/A'}`"
                if cycle.inquiry_sequence_no and cycle.inquiry_sequence_no != cycle.sequence_no:
                    pre_str += f" (Inq Seq: `{cycle.inquiry_sequence_no}`)"
                full_lines.append(f"- **Pre-Auth ID / Sequence**: {pre_str}")

            full_lines.append(f"- **Total WIC Paid Amount**: `${cycle.wic_amount:,.2f}`")
        full_lines.append("")

        # Items Table
        if cycle.items:
            full_lines.append("### Scanned Basket Items")
            full_lines.append("")
            full_lines.append("| Line | Log Line | UPC / PLU | Description | Shelf Price | WIC Paid |")
            full_lines.append("| :---: | :---: | :--- | :--- | :---: | :---: |")
            for item in cycle.items:
                desc = item.description or f"UPC {item.upc}"
                log_ref = f"`{item.log_line}`" if item.log_line else "`N/A`"
                full_lines.append(f"| {item.line_no} | {log_ref} | `{item.upc}` | {desc} | ${item.price:,.2f} | ${item.wic_paid:,.2f} |")
            full_lines.append("")

        # Balance Reconciliation Table
        full_lines.append("### Balance Reconciliation Table")
        full_lines.append("")

        table_header = [
            "| Cat/Sub | Description | Initial Balance | Deducted | Remaining Balance | UOM |",
            "| :---: | :--- | :---: | :---: | :---: | :---: |"
        ]
        table_rows = []

        for row in cycle.reconciled_rows:
            is_curr = row["is_currency"]
            uom = row["uom"]
            init_str = format_balance(row["initial"], is_curr, uom)
            rem_str = format_balance(row["remaining"], is_curr, uom)

            ded_val = row["deducted"]
            ded_str = format_balance(ded_val, is_curr, uom)
            if highlight_deductions and ded_val > 0:
                ded_str = f"**{ded_str}**"

            table_rows.append(
                f"| {row['cat_sub']} | {row['description']} | {init_str} | {ded_str} | {rem_str} | {uom} |"
            )

        if not table_rows:
            table_rows.append("| - | No benefit categories reported | 0.00 | 0.00 | 0.00 | - |")

        full_lines.extend(table_header)
        full_lines.extend(table_rows)
        full_lines.append("")

        # Log Event Trace
        if cycle.events:
            full_lines.append("### Log Event Trace")
            full_lines.append("")
            full_lines.append("| Line | Time | Event | Summary |")
            full_lines.append("| :---: | :---: | :--- | :--- |")
            for ev in cycle.events:
                t_str = f"`{ev.timestamp}`" if ev.timestamp else "`N/A`"
                full_lines.append(f"| `{ev.line_no}` | {t_str} | {ev.event_type} | {ev.summary} |")
            full_lines.append("")

        # Save table to clipboard block
        if cycle.is_inquiry_only:
            clip_header = f"### WIC Balance Inquiry - Seq: {cycle.sequence_no or cycle.invoice_id} (Auth: {cycle.auth_id or 'APPROVED'})\n"
        else:
            clip_header = f"### WIC Balance Reconciliation - Invoice #{cycle.invoice_id} (Auth: {cycle.auth_id or 'APPROVED'})\n"
        clip_table = clip_header + "\n".join(table_header + table_rows) + "\n"
        clipboard_tables.append(clip_table)

    return "\n".join(full_lines), "\n\n".join(clipboard_tables)
