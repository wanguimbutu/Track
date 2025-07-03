# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, today, nowtime

class DeliveryReturn(Document):
	pass

def on_submit_delivery_return(doc, method):
	"""
	On Submit of Delivery Return:
	- Update returned QR codes
	- Handle damaged or unreadable QR returns
	- Mark as Destroyed if needed and log in Destruction Log
	"""

	# Get damaged warehouse (if defined)
	damaged_warehouse = frappe.db.get_single_value("Stock Settings", "default_damaged_warehouse")

	# --- 1. Process normal returned_items
	for row in doc.returned_items:
		if not row.qr_code:
			continue

		qr_code = row.qr_code.strip()
		scan_log_name = frappe.db.get_value("Scan Log", {"qr_code": qr_code})

		if not scan_log_name:
			frappe.msgprint(f"Scan Log not found for QR Code: {qr_code}")
			continue

		# Get return warehouse
		return_to_warehouse = getattr(row, "target_warehouse", None) or getattr(doc, "target_warehouse", None)

		# Get Scan Log info
		scan_log = frappe.db.get_value("Scan Log", scan_log_name, ["item_code", "batch_no", "dispatch_reference"], as_dict=True)

		if damaged_warehouse and return_to_warehouse == damaged_warehouse:
			# Mark as destroyed
			frappe.db.set_value("Scan Log", scan_log_name, {
				"status": "Destroyed",
				"return_reference": doc.name,
				"return_date": doc.date,
				"comments": f"Item damaged on return. Sent to damaged warehouse via {doc.name}"
			})

			# Create Destruction Log
			frappe.get_doc({
				"doctype": "Destruction Log",
				"qr_code": qr_code,
				"item_code": scan_log.item_code,
				"batch_no": scan_log.batch_no,
				"dispatch_reference": scan_log.dispatch_reference,
				"reason": f"Damaged item (QR readable) - Returned via {doc.name}",
				"return_reference": doc.name,
				"return_date": doc.date,
				"destroyed_by": frappe.session.user,
				"destruction_time": now_datetime()
			}).insert(ignore_permissions=True)

			frappe.msgprint(f"QR Code <b>{qr_code}</b> marked as Destroyed due to damaged return.")
		else:
			# Normal return
			frappe.db.set_value("Scan Log", scan_log_name, {
				"status": "Returned",
				"return_reference": doc.name,
				"return_date": doc.date
			})

	# --- 2. Handle invalid_items (unreadable or too damaged QR codes)
	if hasattr(doc, 'invalid_items'):
		for invalid in doc.invalid_items:
			if not invalid.delivery_note:
				frappe.msgprint(f"Missing Delivery Note for invalid item. Skipping.")
				continue

			dispatch_sheet = frappe.db.get_value("Delivery Note", invalid.delivery_note, "custom_dispatch_sheet")

			if not dispatch_sheet:
				frappe.msgprint(f"No Dispatch Sheet linked to Delivery Note {invalid.delivery_note}. Skipping.")
				continue

			# Try getting item_code + batch_no from existing QR (if present)
			item_code, batch_no = None, None
			if invalid.qr_code:
				existing = frappe.db.get_value("Scan Log", {"qr_code": invalid.qr_code.strip()}, ["item_code", "batch_no"], as_dict=True)
				if existing:
					item_code = existing.item_code
					batch_no = existing.batch_no

			# If not from QR, fallback: get from Delivery Note Item
			if not item_code or not batch_no:
				dn_item = frappe.db.get_value("Delivery Note Item", {"parent": invalid.delivery_note}, ["item_code", "batch_no"], as_dict=True)
				if dn_item:
					item_code = dn_item.item_code
					batch_no = dn_item.batch_no

			if not item_code or not batch_no:
				frappe.msgprint(f"Could not determine item_code or batch_no for invalid return. Skipping.")
				continue

			# Find a dispatched QR code from that batch
			dispatched_log = frappe.db.get_value(
				"Scan Log",
				{
					"dispatch_reference": dispatch_sheet,
					"item_code": item_code,
					"batch_no": batch_no,
					"status": "Dispatched"
				},
				["name", "qr_code"],
				as_dict=True
			)

			if not dispatched_log:
				frappe.msgprint(f"No dispatched QR code found for Dispatch Sheet {dispatch_sheet}, Item {item_code}, Batch {batch_no}.")
				continue

			# Mark as destroyed
			destruction_comment = f"Unsalvageable and unreadable QR - Returned via {doc.name}"
			frappe.db.set_value("Scan Log", dispatched_log.name, {
				"status": "Destroyed",
				"return_reference": doc.name,
				"return_date": doc.date,
				"comments": destruction_comment
			})

			# Log to Destruction Log
			frappe.get_doc({
				"doctype": "Destruction Log",
				"qr_code": dispatched_log.qr_code,
				"item_code": item_code,
				"batch_no": batch_no,
				"dispatch_reference": dispatch_sheet,
				"reason": destruction_comment,
				"return_reference": doc.name,
				"return_date": doc.date,
				"destroyed_by": frappe.session.user,
				"destruction_time": now_datetime()
			}).insert(ignore_permissions=True)

			# Create new Scan Log if replacement QR is given
			if invalid.qr_code:
				if frappe.db.exists("Scan Log", {"qr_code": invalid.qr_code.strip()}):
					frappe.throw(f"QR Code {invalid.qr_code} already exists in Scan Log.")

				frappe.get_doc({
					"doctype": "Scan Log",
					"qr_code": invalid.qr_code.strip(),
					"item_code": item_code,
					"batch_no": batch_no,
					"status": "Returned",
					"return_reference": doc.name,
					"return_date": doc.date,
					"dispatch_reference": dispatch_sheet
				}).insert(ignore_permissions=True)

				frappe.msgprint(f"Replacement QR Code <b>{invalid.qr_code}</b> created and marked as Returned.")
			else:
				frappe.msgprint(f"QR Code <b>{dispatched_log.qr_code}</b> marked as Destroyed (unreadable, no replacement).")

def validate_returned_qr_codes(doc, method):
	"""
	On Save of Delivery Return:
	- Validate returned QR codes:
	  - Must exist in Scan Log with status 'Dispatched'
	  - Auto-populate item_code, item_name, dispatch_reference
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
    Create Delivery Note Returns manually without relying on get_return_doc.
    This approach is more reliable across different ERPNext versions.
    """
    try:
        delivery_return = frappe.get_doc("Delivery Return", docname)
        
        if not delivery_return.returned_items:
            frappe.throw("No returned items found in Delivery Return")
            
        created_notes = []

        # Group items by delivery note and item_code
        deliveries = {}
        for row in delivery_return.returned_items:
            if not row.delivery_note:
                frappe.throw(f"Delivery Note missing for QR Code: {row.qr_code}")
                
            delivery_note = row.delivery_note
            if delivery_note not in deliveries:
                deliveries[delivery_note] = {}
            
            # Group by item_code to aggregate quantities
            item_code = row.item_code
            if item_code not in deliveries[delivery_note]:
                deliveries[delivery_note][item_code] = {
                    'qty': 0,
                    'qr_codes': []
                }
            
            deliveries[delivery_note][item_code]['qty'] += 1  # Each QR = 1 qty
            deliveries[delivery_note][item_code]['qr_codes'].append(row.qr_code)

        # Create return documents for each delivery note
        for dn_name, items_data in deliveries.items():
            try:
                # Get original delivery note
                original_dn = frappe.get_doc("Delivery Note", dn_name)
                if original_dn.docstatus != 1:
                    frappe.throw(f"Delivery Note {dn_name} is not submitted")
                
                # Create return delivery note manually
                return_doc = frappe.new_doc("Delivery Note")
                
                # Copy basic information from original
                return_doc.customer = original_dn.customer
                return_doc.company = original_dn.company
                return_doc.posting_date = delivery_return.date or today()
                return_doc.posting_time = nowtime()
                
                # Set return flags
                return_doc.is_return = 1
                return_doc.return_against = dn_name
                
                # Copy delivery-related fields to avoid validation errors
                if hasattr(original_dn, 'vehicle_no') and original_dn.vehicle_no:
                    return_doc.vehicle_no = original_dn.vehicle_no
                if hasattr(original_dn, 'driver_name') and original_dn.driver_name:
                    return_doc.driver_name = original_dn.driver_name
                if hasattr(original_dn, 'driver') and original_dn.driver:
                    return_doc.driver = original_dn.driver
                if hasattr(original_dn, 'transporter') and original_dn.transporter:
                    return_doc.transporter = original_dn.transporter
                if hasattr(original_dn, 'transporter_name') and original_dn.transporter_name:
                    return_doc.transporter_name = original_dn.transporter_name
                if hasattr(original_dn, 'lr_no') and original_dn.lr_no:
                    return_doc.lr_no = original_dn.lr_no
                if hasattr(original_dn, 'lr_date') and original_dn.lr_date:
                    return_doc.lr_date = original_dn.lr_date
                
                # Copy other essential fields
                fields_to_copy = [
                    'currency', 'conversion_rate', 'selling_price_list',
                    'price_list_currency', 'plc_conversion_rate', 'ignore_pricing_rule',
                    'set_warehouse', 'target_warehouse', 'tc_name', 'terms',
                    'customer_address', 'shipping_address_name', 'contact_person',
                    'territory', 'sales_team'
                ]
                
                for field in fields_to_copy:
                    if hasattr(original_dn, field) and getattr(original_dn, field):
                        setattr(return_doc, field, getattr(original_dn, field))
                
                # Add items based on what's being returned
                for item_code, item_data in items_data.items():
                    # Find the original item in the delivery note
                    original_item = None
                    for item in original_dn.items:
                        if item.item_code == item_code:
                            original_item = item
                            break
                    
                    if not original_item:
                        frappe.throw(f"Item {item_code} not found in Delivery Note {dn_name}")
                    
                    # Add return item with negative quantity for returns
                    return_doc.append("items", {
                        "item_code": item_code,
                        "item_name": original_item.item_name,
                        "description": original_item.description,
                        "qty": -abs(item_data['qty']),  # Negative quantity for returns
                        "uom": original_item.uom,
                        "rate": original_item.rate,
                        "warehouse": original_item.warehouse,
                        "expense_account": getattr(original_item, 'expense_account', None),
                        "cost_center": getattr(original_item, 'cost_center', None),
                        "against_delivery_note": dn_name,
                        "dn_detail": original_item.name,
                        "against_sales_order": getattr(original_item, 'against_sales_order', None),
                        "so_detail": getattr(original_item, 'so_detail', None),
                        "serial_and_batch_bundle": getattr(original_item, 'serial_and_batch_bundle', None)
                    })
                
                # Add custom QR codes tracking
                if hasattr(return_doc, 'custom_returned_qr_codes'):
                    for item_code, item_data in items_data.items():
                        for qr_code in item_data['qr_codes']:
                            return_doc.append("custom_returned_qr_codes", {
                                "qr_code": qr_code,
                                "qr_return_reference": delivery_return.name
                            })
                
                # Set ignore validation flags to bypass some checks during insert
                return_doc.flags.ignore_validate_update_after_submit = True
                return_doc.flags.ignore_permissions = True
                
                # Save the return document
                return_doc.insert(ignore_permissions=True)
                
                # Submit if auto-submit is enabled
                if delivery_return.get('auto_submit_returns'):
                    return_doc.submit()
                
                created_notes.append(return_doc.name)
                
            except Exception as e:
                error_msg = str(e)
                frappe.log_error(f"Error creating return for {dn_name}: {error_msg}", "Delivery Return Creation Error")
                # More specific error handling
                if "vehicle_no" in error_msg or "driver_name" in error_msg:
                    frappe.throw(f"Error creating return for Delivery Note {dn_name}: Missing required delivery fields (vehicle_no, driver_name). Please ensure the original delivery note has these fields filled.")
                else:
                    frappe.throw(f"Error creating return for Delivery Note {dn_name}: {error_msg}")

        if created_notes:
            frappe.msgprint(f"Created Delivery Note Returns:<br><b>{'<br>'.join(created_notes)}</b>")
        else:
            frappe.msgprint("No Delivery Note Returns were created")
            
        return created_notes
        
    except Exception as e:
        error_msg = str(e)
        frappe.log_error(f"Error in create_delivery_note_returns: {error_msg}", "Delivery Return Function Error")
        frappe.throw(f"Error creating delivery note returns: {error_msg}")