import frappe
from frappe import _
from frappe.model.document import Document
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import get_auto_batch_nos

@frappe.whitelist()
def auto_select_batches_for_delivery_note(docname):
    doc = frappe.get_doc("Delivery Note", docname)

    if doc.docstatus != 0:
        frappe.throw(_("Cannot modify submitted document"))

    updated = False
    for item in doc.items:
        if item.serial_and_batch_bundle or not item.qty or item.qty <= 0:
            continue

        item_doc = frappe.get_cached_doc("Item", item.item_code)
        if not item_doc.has_batch_no:
            continue

        batches = get_auto_batch_nos({
            "item_code": item.item_code,
            "warehouse": item.warehouse,
            "qty": item.qty,
            "based_on": "FIFO"
        })

        if not batches:
            frappe.msgprint(f"No batches available for item {item.item_code}")
            continue

        bundle_doc = frappe.get_doc({
            "doctype": "Serial and Batch Bundle",
            "item_code": item.item_code,
            "warehouse": item.warehouse,
            "type_of_transaction": "Outward",
            "voucher_type": "Delivery Note",
            "reference_doctype": "Delivery Note",
            "reference_name": doc.name,
            "entries": [
                {
                    "batch_no": batch.get("batch_no"),
                    "qty": batch.get("qty"),
                    "warehouse": item.warehouse
                } for batch in batches
            ]
        })
        bundle_doc.insert(ignore_permissions=True)
        item.serial_and_batch_bundle = bundle_doc.name
        updated = True

    if updated:
        doc.save()
        return {"success": True, "message": "Batches selected successfully."}
    else:
        return {"success": False, "message": "No items required batch selection."}
