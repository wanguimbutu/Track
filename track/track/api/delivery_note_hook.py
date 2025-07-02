import frappe
from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import get_auto_batch_nos

def auto_select_batches(doc, method=None):
    """Automatically select batches for items in delivery note using FIFO method"""
    if doc.doctype != 'Delivery Note' or doc.docstatus != 0:
        return

    for item in doc.items:
        try:
            if item.serial_and_batch_bundle or not item.qty or item.qty <= 0:
                continue

            item_doc = frappe.get_cached_doc('Item', item.item_code)
            if not item_doc.has_batch_no:
                continue

            frappe.logger().info(f"Processing {item.item_code} in {item.warehouse} for qty {item.qty}")

            batches = get_auto_batch_nos({
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'qty': item.qty,
                'based_on': 'FIFO'
            })

            if not batches:
                frappe.msgprint(f"No batches available for item {item.item_code} in warehouse {item.warehouse}")
                continue

            bundle_doc = frappe.get_doc({
                'doctype': 'Serial and Batch Bundle',
                'item_code': item.item_code,
                'warehouse': item.warehouse,
                'type_of_transaction': 'Outward',
                'voucher_type': 'Delivery Note',
                'reference_doctype': 'Delivery Note',
                'reference_name': doc.get('name') or 'TEMP',
                'entries': [
                    {
                        'batch_no': batch.get('batch_no'),
                        'qty': batch.get('qty'),
                        'warehouse': item.warehouse
                    } for batch in batches
                ]
            })

            bundle_doc.insert(ignore_permissions=True)
            item.serial_and_batch_bundle = bundle_doc.name

            frappe.msgprint(f"✔️ Batch bundle created for {item.item_code}: {bundle_doc.name}")

        except Exception as e:
            frappe.log_error(f"Auto batch selection failed for {item.item_code}: {str(e)}")

    doc.save()  # Save all changes after processing
