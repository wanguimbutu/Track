# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt
 
import frappe
from frappe.model.document import Document
from erpnext.stock.doctype.delivery_note.delivery_note import get_return_doc



class DeliveryReturn(Document):
	pass

def on_submit_delivery_return(doc, method):
        """
        On Submit of Delivery Return:
        - For each QR code in returned_items:
            - Update Scan Log:
                - status = 'Returned'
                - return_reference = this Delivery Return doc
                - return_date = doc.date
        """
        for row in doc.returned_items:
            if not row.qr_code:
                continue

            qr_code = row.qr_code.strip()

            scan_log_name = frappe.db.get_value("Scan Log", {"qr_code": qr_code})

            if scan_log_name:
                frappe.db.set_value("Scan Log", scan_log_name, {
                    "status": "Returned",
                    "return_reference": doc.name,
                    "return_date": doc.date
                })
            else:
                frappe.msgprint(f"Scan Log not found for QR Code: {qr_code}")



def validate_returned_qr_codes(doc, method):
    """
    On Save of Delivery Return:
    - For each QR code in returned_items:
        - Must exist in Scan Log with status == 'Dispatched'
        - Fetch item_code, item_name, dispatch_reference
    """
    invalid_qrs = []

    for row in doc.returned_items:
        if not row.qr_code:
            continue

        qr_code = row.qr_code.strip()
        log = frappe.db.get_value("Scan Log", {"qr_code": qr_code}, ["item_code", "dispatch_reference", "status"], as_dict=True)

        if not log or log.status != "Dispatched":
            invalid_qrs.append(qr_code)
            continue

        row.item_code = log.item_code
        row.dispatch_reference = log.dispatch_reference
        row.item_name = frappe.db.get_value("Item", log.item_code, "item_name")

    if invalid_qrs:
        frappe.throw(f"The following QR codes are not marked as 'Dispatched':<br><b>{', '.join(invalid_qrs)}</b>")


@frappe.whitelist()
def create_delivery_note_returns(docname):
    """
    Create Delivery Note Returns using ERPNext's built-in get_return_doc method.
    Adds custom_returned_qr_codes for each QR code in Delivery Return.
    """
    delivery_return = frappe.get_doc("Delivery Return", docname)
    created_notes = []

    deliveries = {}
    for row in delivery_return.returned_items:
        if row.delivery_note not in deliveries:
            deliveries[row.delivery_note] = []
        deliveries[row.delivery_note].append(row)

    for dn_name, rows in deliveries.items():
        return_doc = get_return_doc("Delivery Note", dn_name)

        # Add custom_returned_qr_codes
        for row in rows:
            return_doc.append("custom_returned_qr_codes", {
                "qr_code": row.qr_code,
                "qr_return_reference": delivery_return.name
            })

        return_doc.insert(ignore_permissions=True)
        created_notes.append(return_doc.name)

    frappe.msgprint(f"Created Delivery Note Returns:<br><b>{'<br>'.join(created_notes)}</b>")
    return created_notes
