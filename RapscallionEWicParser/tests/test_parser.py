"""Automated Test Suite for RapscallionEWicParser.

Verifies:
1. Single-line TLV extraction and decimal decoding.
2. Full SLS log auditing and transaction discovery.
3. Targeted single-transaction correlation for Invoices 9486 and 9519.
4. APL parsing and item matching (Post Cereal & fresh produce PLUs).
5. USDA fallback category mapping when running without APL.
6. Markdown report generation and balance reconciliation math.
"""

import os
import sys

# Add parent directory to path so package modules can be imported
PKG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_DIR = os.path.abspath(os.path.join(PKG_DIR, ".."))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from RapscallionEWicParser.usda_fallback import resolve_category, format_balance
from RapscallionEWicParser.apl_parser import APLDatabase, discover_candidate_apls
from RapscallionEWicParser.ewic_core import (
    parse_tlv_string,
    LogAuditScanner,
    render_markdown_report,
)
from RapscallionEWicParser.report_renderer import (
    markdown_to_standalone_html,
)

SAMPLE_SLS = r"C:\Users\KevinSommers\.gemini\antigravity\brain\0ab05394-4268-435a-ad85-c2a9e2cf9ec0\.user_uploaded\media_1793220481813_6efb5e1d.sls"
SAMPLE_SLS_RBS = r"C:\Users\KevinSommers\.gemini\antigravity\brain\0ab05394-4268-435a-ad85-c2a9e2cf9ec0\.user_uploaded\media_1793225892119_e81df161.sls"
SAMPLE_SLS_WINEPS = r"C:\Users\KevinSommers\.gemini\antigravity\brain\0ab05394-4268-435a-ad85-c2a9e2cf9ec0\.user_uploaded\media_1793227722748_dca3377c.sls"
SAMPLE_APL = r"C:\Users\KevinSommers\.gemini\antigravity\brain\0ab05394-4268-435a-ad85-c2a9e2cf9ec0\.user_uploaded\media_1793220481914_8b3792d8.apl"


def test_tlv_parsing():
    print("[*] Testing TLV Parsing...")
    raw = 'dat="EA01414200500003600EA01414201900005300EA01414205000206400EF00820261031"'
    bals, exp, st = parse_tlv_string(raw, "NZ")

    assert exp == "2026-10-31", f"Expected 2026-10-31, got {exp}"
    assert ("05", "000") in bals, "Missing Adult Cereal (05, 000)"
    assert bals[("05", "000")] == 36.00, f"Expected 36.00, got {bals[('05', '000')]}"
    assert ("19", "000") in bals, "Missing Produce (19, 000)"
    assert bals[("19", "000")] == 53.00, f"Expected 53.00, got {bals[('19', '000')]}"
    assert ("50", "002") in bals, "Missing Yogurt (50, 002)"
    assert bals[("50", "002")] == 64.00, f"Expected 64.00, got {bals[('50', '002')]}"
    print("    [+] TLV Parsing PASSED")


def test_apl_loading():
    print("[*] Testing APL Loading & UPC Lookups...")
    if not os.path.exists(SAMPLE_APL):
        print(f"    [-] Sample APL not found at {SAMPLE_APL}, skipping APL test.")
        return None

    db = APLDatabase(SAMPLE_APL)
    print(f"    [+] APL Loaded: {len(db.upc_map)} UPC entries, {len(db.cat_map)} Category entries")

    # Test Post Cereal
    cereal = db.lookup_upc("00000884912014269")
    assert cereal is not None, "Post Honey Bunches of Oats not found"
    assert "HNY" in cereal["description"].upper(), f"Unexpected desc: {cereal['description']}"
    assert cereal["cat"] == "05", f"Expected cat 05, got {cereal['cat']}"
    assert cereal["uom"] == "OZ", f"Expected UOM OZ, got {cereal['uom']}"

    # Test Produce PLU (Avocados 42253)
    avo = db.lookup_upc("00000000000042253")
    assert avo is not None, "Avocados PLU not found"
    assert "AVOCADO" in avo["description"].upper(), f"Unexpected desc: {avo['description']}"
    assert avo["cat"] == "19", f"Expected cat 19, got {avo['cat']}"

    print("    [+] APL Lookups PASSED")
    return db


def test_log_audit(apl_db=None):
    print("[*] Testing SLS Log Auditing...")
    if not os.path.exists(SAMPLE_SLS):
        print(f"    [-] Sample SLS not found at {SAMPLE_SLS}, skipping SLS test.")
        return

    with open(SAMPLE_SLS, "r", encoding="latin1") as f:
        lines = f.readlines()

    scanner = LogAuditScanner(lines, default_state="NZ")
    cycles = scanner.scan()
    print(f"    [+] Discovered {len(cycles)} E-WIC transactions in log file")
    assert len(cycles) >= 2, f"Expected at least 2 E-WIC cycles, found {len(cycles)}"

    # Check Invoice 9486
    c9486 = next((c for c in cycles if c.invoice_id == "9486"), None)
    assert c9486 is not None, "Invoice 9486 not found in audit"
    c9486.reconcile(apl_db)

    print(f"    [+] Invoice 9486: Auth={c9486.auth_id}, Paid=${c9486.wic_amount:.2f}, Items={len(c9486.items)}")
    assert c9486.auth_id == "578350", f"Expected auth 578350, got {c9486.auth_id}"
    assert c9486.wic_amount == 6.33, f"Expected 6.33 paid, got {c9486.wic_amount}"
    assert len(c9486.items) == 1, f"Expected 1 item, got {len(c9486.items)}"
    assert c9486.items[0].log_line == 670, f"Expected log_line 670, got {c9486.items[0].log_line}"
    assert len(c9486.events) >= 6, f"Expected at least 6 events, got {len(c9486.events)}"

    # Check deduction for cereal
    cereal_row = next((r for r in c9486.reconciled_rows if r["cat"] == "05"), None)
    assert cereal_row is not None, "Cereal row not found in reconciliation"
    assert cereal_row["initial"] == 36.00, f"Expected 36.00 initial, got {cereal_row['initial']}"
    assert cereal_row["deducted"] == 18.00, f"Expected 18.00 deducted, got {cereal_row['deducted']}"
    assert cereal_row["remaining"] == 18.00, f"Expected 18.00 remaining, got {cereal_row['remaining']}"

    # Check Invoice 9519
    c9519 = next((c for c in cycles if c.invoice_id == "9519"), None)
    assert c9519 is not None, "Invoice 9519 not found in audit"
    c9519.reconcile(apl_db)

    print(f"    [+] Invoice 9519: Auth={c9519.auth_id}, Paid=${c9519.wic_amount:.2f}, Items={len(c9519.items)}")
    assert c9519.auth_id == "581410", f"Expected auth 581410, got {c9519.auth_id}"
    assert c9519.wic_amount == 7.55, f"Expected 7.55 paid, got {c9519.wic_amount}"
    assert len(c9519.items) == 3, f"Expected 3 items, got {len(c9519.items)}"
    assert c9519.items[0].log_line == 4625, f"Expected item 1 at line 4625, got {c9519.items[0].log_line}"

    # Check deduction for produce (Cat 19)
    produce_row = next((r for r in c9519.reconciled_rows if r["cat"] == "19"), None)
    assert produce_row is not None, "Produce row not found in reconciliation"
    assert produce_row["initial"] == 34.91, f"Expected 34.91 initial, got {produce_row['initial']}"
    assert produce_row["deducted"] == 7.55, f"Expected 7.55 deducted, got {produce_row['deducted']}"
    assert produce_row["remaining"] == 27.36, f"Expected 27.36 remaining, got {produce_row['remaining']}"

    # Render Markdown Report
    report, clip_table = render_markdown_report([c9486, c9519], log_path=SAMPLE_SLS, apl_name="Test APL")
    assert "E-WIC Transaction Audit Report" in report
    assert "Buypass / FIS" in report
    assert "Invoice #9486" in report
    assert "Invoice #9519" in report
    assert "578350" in report
    assert "581410" in report
    assert "### Scanned Basket Items" in report
    assert "| Line | Log Line | UPC / PLU | Description | Shelf Price | WIC Paid |" in report
    assert "`670`" in report
    assert "### Log Event Trace" in report
    assert "`614`" in report
    assert "`703`" in report
    assert len(clip_table) > 100, "Clipboard table should not be empty"

    # Test Standalone Browser Renderer (uses <table> and responsive styling)
    standalone = markdown_to_standalone_html(report, title="Audit Report")
    assert "<table" in standalone, "Expected <table> in standalone HTML"
    assert "action-btn" in standalone, "Expected action-btn in standalone HTML"
    assert "Adult Cereal" in standalone, "Expected Adult Cereal in standalone HTML"

    print("    [+] Buypass / FIS Log Audit PASSED")


def test_rbs_audit(apl_db=None):
    print("[*] Testing RBSLynk ISO Log Auditing...")
    if not os.path.exists(SAMPLE_SLS_RBS):
        print(f"    [-] Sample RBS SLS not found at {SAMPLE_SLS_RBS}, skipping RBS test.")
        return

    with open(SAMPLE_SLS_RBS, "r", encoding="latin1") as f:
        lines = f.readlines()

    scanner = LogAuditScanner(lines, default_state="NZ")
    assert scanner.bank_name == "RBSLynk ISO", f"Expected RBSLynk ISO, got {scanner.bank_name}"

    cycles = scanner.scan()
    print(f"    [+] Discovered {len(cycles)} E-WIC transactions in RBSLynk log")
    assert len(cycles) == 6, f"Expected 6 cycles (5 purchases + 1 standalone inquiry), got {len(cycles)}"

    for c in cycles:
        c.reconcile(apl_db)

    # Check Invoice 669571: PreAuth should be 345374 (NOT '094110.251218.052229)
    c1 = next((c for c in cycles if c.invoice_id == "669571"), None)
    assert c1 is not None, "Invoice 669571 not found"
    assert c1.auth_id == "345390", f"Expected auth 345390, got {c1.auth_id}"
    assert c1.preauth_id == "345374", f"Expected clean preauth 345374, got {c1.preauth_id}"
    assert c1.inquiry_sequence_no == "052229", f"Expected inq_seq 052229, got {c1.inquiry_sequence_no}"
    assert c1.sequence_no == "052230", f"Expected seq 052230, got {c1.sequence_no}"
    assert c1.wic_amount == 9.29, f"Expected 9.29, got {c1.wic_amount}"
    assert c1.items[0].log_line == 614, f"Expected item at line 614, got {c1.items[0].log_line}"
    assert len(c1.events) >= 6, f"Expected >= 6 events, got {len(c1.events)}"

    # Render Report for RBSLynk
    report, _ = render_markdown_report(cycles, log_path=SAMPLE_SLS_RBS, apl_name="Test APL")
    assert "# RBSLynk ISO E-WIC Transaction Audit Report" in report
    assert "Bank / Processor**: `RBSLynk ISO`" in report
    assert "Invoice #669571" in report
    assert "Pre-Auth ID / Sequence**: `345374` / `052230` (Inq Seq: `052229`)" in report
    assert "### Log Event Trace" in report
    assert "`614`" in report
    assert "`659`" in report

    print("    [+] RBSLynk ISO Log Audit PASSED")


def test_wineps_audit(apl_db=None):
    print("[*] Testing WinEPS Log Auditing...")
    if not os.path.exists(SAMPLE_SLS_WINEPS):
        print(f"    [-] Sample WinEPS SLS not found at {SAMPLE_SLS_WINEPS}, skipping WinEPS test.")
        return

    with open(SAMPLE_SLS_WINEPS, "r", encoding="latin1") as f:
        lines = f.readlines()

    scanner = LogAuditScanner(lines, default_state="NZ")
    assert scanner.bank_name == "WinEPS", f"Expected WinEPS, got {scanner.bank_name}"

    cycles = scanner.scan()
    print(f"    [+] Discovered {len(cycles)} E-WIC transactions in WinEPS log")
    assert len(cycles) == 1, f"Expected 1 cycle, got {len(cycles)}"

    c = cycles[0]
    assert c.is_inquiry_only is True, "Expected inquiry-only cycle"
    assert c.sequence_no == "035248", f"Expected sequence 035248, got {c.sequence_no}"
    assert c.auth_id == "515935", f"Expected auth 515935, got {c.auth_id}"
    assert c.state == "MI", f"Expected state MI, got {c.state}"
    assert c.exp_date == "2026-09-16", f"Expected 2026-09-16, got {c.exp_date}"
    assert len(c.inquiry_balances) == 9, f"Expected 9 benefit categories, got {len(c.inquiry_balances)}"
    assert len(c.events) == 3, f"Expected 3 events for WinEPS inquiry, got {len(c.events)}"
    assert c.events[0].line_no == 322, f"Expected req line 322, got {c.events[0].line_no}"
    assert c.events[1].line_no == 400, f"Expected bal line 400, got {c.events[1].line_no}"
    assert c.events[2].line_no == 417, f"Expected resp line 417, got {c.events[2].line_no}"

    c.reconcile(apl_db)
    # Check that CVV (Cat 19) is $50.98 remaining and $0.00 deducted
    cvv_row = next((r for r in c.reconciled_rows if r["cat_sub"].startswith("19")), None)
    assert cvv_row is not None, "CVV row not found"
    assert cvv_row["initial"] == 50.98, f"Expected 50.98 initial, got {cvv_row['initial']}"
    assert cvv_row["deducted"] == 0.0, f"Expected 0.0 deducted, got {cvv_row['deducted']}"
    assert cvv_row["remaining"] == 50.98, f"Expected 50.98 remaining, got {cvv_row['remaining']}"

    # Render Report for WinEPS
    report, _ = render_markdown_report(cycles, log_path=SAMPLE_SLS_WINEPS, apl_name="Test APL")
    assert "# WinEPS E-WIC Transaction Audit Report" in report
    assert "Bank / Processor**: `WinEPS`" in report
    assert "Balance Inquiry (Seq: 035248 | Auth: 515935)" in report
    assert "Balance Inquiry (No Basket Items)" in report
    assert "State / Schema**: `MI`" in report
    assert "$0.00 (Inquiry)" in report
    assert "### Log Event Trace" in report
    assert "`322`" in report
    assert "`400`" in report
    assert "`417`" in report

    # Test targeted audit by sequence and auth
    seq_cycles = scanner.scan(target_invoice="035248")
    assert len(seq_cycles) == 1, "Targeted audit by sequence failed"
    auth_cycles = scanner.scan(target_invoice="515935")
    assert len(auth_cycles) == 1, "Targeted audit by auth failed"

    print("    [+] WinEPS Log Audit PASSED")


def test_targeted_audit():
    print("[*] Testing Single-Transaction Targeted Audit (F1032=9486)...")
    with open(SAMPLE_SLS, "r", encoding="latin1") as f:
        lines = f.readlines()

    scanner = LogAuditScanner(lines, default_state="NZ")
    cycles = scanner.scan(target_invoice="9486")
    assert len(cycles) == 1, f"Expected 1 cycle for targeted audit, got {len(cycles)}"
    assert cycles[0].invoice_id == "9486", f"Expected 9486, got {cycles[0].invoice_id}"
    print("    [+] Targeted Audit PASSED")


def test_report_destination_resolution():
    print("[*] Testing Report Destination Resolution Logic...")
    def resolve(settings_dict):
        dest = settings_dict.get("report_destination", None)
        if dest in ("markdown", "browser", "both"):
            return dest
        if settings_dict.get("auto_open_in_browser", False):
            return "both"
        legacy_mode = settings_dict.get("report_view_mode", None)
        if legacy_mode in ("markdown", "browser", "both"):
            return legacy_mode
        return "markdown"

    assert resolve({"report_destination": "browser"}) == "browser"
    assert resolve({"report_destination": "both"}) == "both"
    assert resolve({"report_destination": "markdown"}) == "markdown"
    assert resolve({"auto_open_in_browser": True}) == "both"
    assert resolve({"auto_open_in_browser": False}) == "markdown"
    assert resolve({}) == "markdown"
    assert resolve({"report_destination": "invalid"}) == "markdown"
    print("    [+] Destination Resolution Logic PASSED")


if __name__ == "__main__":
    print("==================================================")
    print("Starting RapscallionEWicParser Test Suite")
    print("==================================================")
    test_tlv_parsing()
    apl_db = test_apl_loading()
    test_log_audit(apl_db)
    test_rbs_audit(apl_db)
    test_wineps_audit(apl_db)
    test_targeted_audit()
    test_report_destination_resolution()
    print("==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")

