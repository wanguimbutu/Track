import frappe
from frappe import _dict
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import get_auto_batch_nos

@frappe.whitelist()
def auto_select_batches_for_delivery_note(docname):
    """Automatically select batches for each item in a Delivery Note using FIFO."""

    doc = frappe.get_doc("Delivery Note", docname)

    if doc.docstatus != 0:
        frappe.throw("Cannot update batches on a submitted Delivery Note.")

    success = 0
    errors = []

    for item in doc.items:
        try:
            if item.serial_and_batch_bundle or not item.qty or item.qty <= 0:
                continue

            item_doc = frappe.get_cached_doc('Item', item.item_code)
            if not item_doc.has_batch_no:
                continue

            batches = get_auto_batch_nos(_dict({
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'qty': item.qty,
                'based_on': 'FIFO'
            }))

            if not batches:
                errors.append(f"No batches found for {item.item_code}")
                continue

            # Create Serial and Batch Bundle
            bundle_doc = frappe.get_doc({
                'doctype': 'Serial and Batch Bundle',
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'type_of_transaction': 'Outward',
                'voucher_type': 'Delivery Note',
                'reference_doctype': 'Delivery Note',
                'reference_name': docname,
                'entries': [
                    {
                        'batch_no': b.get('batch_no'),
                        'qty': b.get('qty'),
                        'warehouse': item.warehouse
                    } for b in batches
                ]
            })

            bundle_doc.insert(ignore_permissions=True)
            item.serial_and_batch_bundle = bundle_doc.name
            success += 1

        except Exception as e:
            error_msg = f"{item.item_code}: {str(e)}"
            frappe.log_error(title="Batch Auto-Selection Failed", message=error_msg)
            errors.append(error_msg)

    doc.save(ignore_permissions=True)

    result = f"{success} item(s) processed successfully."
    if errors:
        result += f"\nErrors:\n" + "\n".join(errors)

    return result
