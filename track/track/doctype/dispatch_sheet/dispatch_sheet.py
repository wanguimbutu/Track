# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DispatchSheet(Document):
	pass

import frappe

@frappe.whitelist()
def fetch_qr_details_for_dispatch(docname):
    """
    Fills item_code, item_name, batch_no, and status in dispatch_qr_codes
    table from Scan Log and Item when user clicks 'Fetch QR Code Details'
    """
    doc = frappe.get_doc("Dispatch Sheet", docname)

    for row in doc.dispatch_qr_codes:
        if not row.qr_code:
            continue

        log = frappe.db.get_value("Scan Log", row.qr_code, ["item_code", "batch_no", "status"], as_dict=True)
        if log:
            row.item_code = log.item_code
            row.batch_no = log.batch_no
            row.status = log.status

            item_name = frappe.db.get_value("Item", log.item_code, "item_name")
            if item_name:
                row.item_name = item_name

    doc.save()
    return "Success"


def on_submit(doc, method):
    """
    On Submit hook for Dispatch Sheet — updates Scan Log entries
    to mark the QR codes as 'Dispatched'
    """
    for row in doc.dispatch_qr_codes:
        if row.qr_code:
            frappe.db.set_value("Scan Log", row.qr_code, "status", "Dispatched")
