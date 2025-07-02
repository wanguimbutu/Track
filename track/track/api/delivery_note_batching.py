import frappe
from frappe import _
from frappe.utils import cint
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import get_auto_batch_nos

def auto_select_batches_on_submit(doc, method=None):
    """Assign serial and batch bundle after submission (safely)."""
    for item in doc.items:
        try:
            if item.serial_and_batch_bundle or not item.qty or item.qty <= 0:
                continue

            item_doc = frappe.get_cached_doc('Item', item.item_code)
            if not item_doc.has_batch_no:
                continue

            # Get batches
            batches = get_auto_batch_nos(frappe._dict({
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'qty': item.qty,
                'based_on': 'FIFO'
            }))

            if not batches:
                frappe.msgprint(f"No batches available for item {item.item_code} in warehouse {item.warehouse}")
                continue

            # Create bundle
            bundle_doc = frappe.get_doc({
                'doctype': 'Serial and Batch Bundle',
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'type_of_transaction': 'Outward',
                'voucher_type': 'Delivery Note',
                'reference_doctype': 'Delivery Note',
                'reference_name': doc.name,
                'entries': [
                    {
                        'batch_no': batch.get('batch_no'),
                        'qty': batch.get('qty'),
                        'warehouse': item.warehouse
                    } for batch in batches
                ]
            })

            bundle_doc.insert(ignore_permissions=True)

            # Update the item manually after submission via DB set
            frappe.db.set_value('Delivery Note Item', item.name, 'serial_and_batch_bundle', bundle_doc.name)

        except Exception as e:
            frappe.log_error(f"[Batch Hook - On Submit] Failed for item {item.item_code}:\n{str(e)}")
