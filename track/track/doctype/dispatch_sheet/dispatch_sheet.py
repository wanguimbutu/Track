# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DispatchSheet(Document):
	pass


@frappe.whitelist()
def fetch_qr_details_for_dispatch(docname):
    """
    Fetch item_code, batch_no, item_name, and status from Scan Log
    for each QR code row in Dispatch Sheet (based on qr_code field, not name).
    """
    doc = frappe.get_doc("Dispatch Sheet", docname)

    if not doc.dispatch_qr_codes:
        frappe.msgprint("No QR codes found in the table.")
        return

    updated = 0
    missing_qrs = []
    updated_details = []

    for row in doc.dispatch_qr_codes:
        if not row.qr_code:
            continue

        frappe.msgprint(f" Looking for QR Code: <b>{row.qr_code}</b>")

        log = frappe.db.get_value("Scan Log", {"qr_code": row.qr_code}, ["item_code", "batch_no", "status"], as_dict=True)

        if log:
            row.item_code = log.item_code
            row.batch_no = log.batch_no
            row.status = log.status

            item_name = frappe.db.get_value("Item", log.item_code, "item_name")
            row.item_name = item_name or ""

            updated += 1
            updated_details.append(f"""
                <b>QR Code:</b> {row.qr_code}<br>
                &nbsp;&nbsp;<b>Item Code:</b> {log.item_code}<br>
                &nbsp;&nbsp;<b>Item Name:</b> {item_name or '-'}<br>
                &nbsp;&nbsp;<b>Batch No:</b> {log.batch_no}<br>
                &nbsp;&nbsp;<b>Status:</b> {log.status}<hr>
            """)
        else:
            missing_qrs.append(row.qr_code)

    if updated > 0:
        doc.save(ignore_permissions=True)
        frappe.msgprint(f"Fetched details for {updated} QR code(s):<br><br>" + "".join(updated_details))

    if missing_qrs:
        frappe.msgprint(f"Could not find the following QR code(s) in Scan Log:<br><b>{', '.join(missing_qrs)}</b>")

    if updated == 0 and not missing_qrs:
        frappe.msgprint("No changes were made.")



def on_submit(doc, method):
    """
    On Submit hook for Dispatch Sheet:
    - Ensures that all scannable items in linked Loading Sheets have QR codes
    - Validates QR code count matches loading qty (only for scannable items)
    - Updates Scan Log entries to 'Dispatched'
    """

    # 1. Collect items from loading sheets
    total_scannable_qty = 0
    scannable_items = {}
    all_items = []

    if doc.loading_sheets:
        for link in doc.loading_sheets:
            loading_doc = frappe.get_doc("Loading Sheet", link.loading_sheet)
            for row in loading_doc.loading_sheet_items:
                item_code = row.item_code
                all_items.append(item_code)

                is_scannable = frappe.db.get_value("Item", item_code, "custom_is_scanned")
                if is_scannable:
                    total_scannable_qty += row.qty
                    if item_code not in scannable_items:
                        scannable_items[item_code] = 0
                    scannable_items[item_code] += row.qty

    # 2. Collect QR codes
    qr_code_entries = [row for row in doc.dispatch_qr_codes if row.qr_code]
    qr_item_counts = {}
    for row in qr_code_entries:
        if row.item_code:
            qr_item_counts[row.item_code] = qr_item_counts.get(row.item_code, 0) + 1

    # 3. Validate QR code presence for scannable items
    missing = []
    for item_code, expected_qty in scannable_items.items():
        scanned_qty = qr_item_counts.get(item_code, 0)
        if scanned_qty < expected_qty:
            item_name = frappe.db.get_value("Item", item_code, "item_name")
            missing.append(f"{item_name or item_code} (Expected: {expected_qty}, Found: {scanned_qty})")

    if missing:
        msg = "<b>The following scannable items are missing QR codes:</b><br>" + "<br>".join(missing)
        frappe.throw(msg)

    # 4. Update Scan Log
    for row in doc.dispatch_qr_codes:
        if row.qr_code:
            log_name = frappe.db.get_value("Scan Log", {"qr_code": row.qr_code})
            if log_name:
                frappe.db.set_value("Scan Log", log_name, {
                    "status": "Dispatched",
                    "dispatch_reference": doc.name,
                    "date": doc.date
                })
            else:
                frappe.msgprint(f"⚠️ Could not find Scan Log for QR Code: {row.qr_code}")
