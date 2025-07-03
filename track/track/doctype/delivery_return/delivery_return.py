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
	- Create replacement Scan Logs using replacement_qr_code field
	"""

	# --- 1. Process normal returned_items
	for row in doc.returned_items:
		if not row.qr_code:
			continue

		qr_code = row.qr_code.strip()
		scan_log_name = frappe.db.get_value("Scan Log", {"qr_code": qr_code})

		if not scan_log_name:
			frappe.msgprint(f"Scan Log not found for QR Code: {qr_code}")
			continue

		# Normal return - always mark as returned
		frappe.db.set_value("Scan Log", scan_log_name, {
			"status": "Returned",
			"return_reference": doc.name,
			"return_date": doc.date
		})

	# --- 2. Handle invalid_items (unreadable or too damaged QR codes) - DEBUG VERSION
	if hasattr(doc, 'invalid_items'):
		frappe.msgprint(f"✓ Found invalid_items field with {len(doc.invalid_items)} items")
		
		for i, invalid in enumerate(doc.invalid_items):
			frappe.msgprint(f"--- Processing invalid item {i+1} ---")
			
			# Debug: Show available fields in the child table
			frappe.msgprint(f"🔍 Child table fields: {list(invalid.__dict__.keys())}")
			
			# Step 1: Check delivery_note
			delivery_note = getattr(invalid, 'delivery_note', None)
			if not delivery_note:
				frappe.msgprint(f"❌ Missing Delivery Note for invalid item {i+1}. Skipping.")
				continue
			
			frappe.msgprint(f"✓ Delivery Note: {delivery_note}")
			
			# Step 2: Get dispatch_sheet
			dispatch_sheet = frappe.db.get_value("Delivery Note", delivery_note, "custom_dispatch_sheet")
			
			if not dispatch_sheet:
				frappe.msgprint(f"❌ No Dispatch Sheet linked to Delivery Note {delivery_note}. Skipping.")
				continue
			
			frappe.msgprint(f"✓ Dispatch Sheet: {dispatch_sheet}")
			
			# Step 3: Try getting item_code + batch_no from existing QR (if present)
			item_code, batch_no = None, None
			qr_code = getattr(invalid, 'qr_code', None)
			if qr_code:
				frappe.msgprint(f"🔍 Checking existing QR: {qr_code.strip()}")
				existing = frappe.db.get_value("Scan Log", {"qr_code": qr_code.strip()}, ["item_code", "batch_no"], as_dict=True)
				if existing:
					item_code = existing.item_code
					batch_no = existing.batch_no
					frappe.msgprint(f"✓ From QR - Item: {item_code}, Batch: {batch_no}")
				else:
					frappe.msgprint(f"❌ No Scan Log found for QR: {qr_code.strip()}")
			
			# Step 4: If not from QR, fallback: get from Delivery Note Item
			if not item_code or not batch_no:
				frappe.msgprint("🔍 Trying to get item_code/batch_no from Delivery Note Item...")
				dn_item = frappe.db.get_value("Delivery Note Item", {"parent": delivery_note}, ["item_code", "batch_no"], as_dict=True)
				if dn_item:
					item_code = dn_item.item_code
					batch_no = dn_item.batch_no
					frappe.msgprint(f"✓ From DN Item - Item: {item_code}, Batch: {batch_no}")
				else:
					frappe.msgprint(f"❌ No Delivery Note Item found for DN: {delivery_note}")
			
			if not item_code or not batch_no:
				frappe.msgprint(f"❌ Could not determine item_code or batch_no for invalid return from {delivery_note}. Skipping.")
				continue
			
			# Step 5: Find a dispatched QR code from that batch
			frappe.msgprint(f"🔍 Looking for dispatched QR code with:")
			frappe.msgprint(f"   - dispatch_reference: {dispatch_sheet}")
			frappe.msgprint(f"   - item_code: {item_code}")
			frappe.msgprint(f"   - batch_no: {batch_no}")
			frappe.msgprint(f"   - status: Dispatched")
			
			# First, let's see what scan logs exist for this dispatch sheet
			all_logs = frappe.db.get_all("Scan Log", 
				filters={"dispatch_reference": dispatch_sheet},
				fields=["name", "qr_code", "item_code", "batch_no", "status"]
			)
			
			frappe.msgprint(f"📋 Found {len(all_logs)} total scan logs for dispatch sheet {dispatch_sheet}")
			for log in all_logs:
				frappe.msgprint(f"   - QR: {log.qr_code}, Item: {log.item_code}, Batch: {log.batch_no}, Status: {log.status}")
			
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
				frappe.msgprint(f"❌ No dispatched QR code found for Dispatch Sheet {dispatch_sheet}, Item {item_code}, Batch {batch_no}.")
				
				# Try without status filter to see if there are any logs
				any_log = frappe.db.get_value(
					"Scan Log",
					{
						"dispatch_reference": dispatch_sheet,
						"item_code": item_code,
						"batch_no": batch_no
					},
					["name", "qr_code", "status"],
					as_dict=True
				)
				
				if any_log:
					frappe.msgprint(f"💡 Found log with different status: {any_log.qr_code} (Status: {any_log.status})")
				else:
					frappe.msgprint(f"💡 No logs found at all for this combination")
				
				continue
			
			frappe.msgprint(f"✓ Found dispatched log: {dispatched_log.qr_code}")
			
			# Step 6: Mark as destroyed
			destruction_comment = f"Unsalvageable and unreadable QR - Returned via {doc.name}"
			frappe.msgprint(f"🔄 Marking {dispatched_log.qr_code} as destroyed...")
			
			try:
				frappe.db.set_value("Scan Log", dispatched_log.name, {
					"status": "Destroyed",
					"return_reference": doc.name,
					"return_date": doc.date,
					"comments": destruction_comment
				})
				frappe.msgprint(f"✓ Marked as destroyed")
			except Exception as e:
				frappe.msgprint(f"❌ Error marking as destroyed: {str(e)}")
				continue
			
			# Step 7: Log to Destruction Log
			try:
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
				frappe.msgprint(f"✓ Created Destruction Log entry")
			except Exception as e:
				frappe.msgprint(f"❌ Error creating Destruction Log: {str(e)}")
			
			# Step 8: Create new Scan Log if replacement QR code is provided
			replacement_qr_code = getattr(invalid, 'replacement_qr_code', None)
			if replacement_qr_code:
				replacement_qr = replacement_qr_code.strip()
				frappe.msgprint(f"🔄 Creating replacement QR: {replacement_qr}")
				
				if frappe.db.exists("Scan Log", {"qr_code": replacement_qr}):
					frappe.msgprint(f"❌ Replacement QR Code {replacement_qr} already exists in Scan Log.")
					continue
				
				try:
					frappe.get_doc({
						"doctype": "Scan Log",
						"qr_code": replacement_qr,
						"item_code": item_code,
						"batch_no": batch_no,
						"status": "Returned",
						"return_reference": doc.name,
						"return_date": doc.date,
						"dispatch_reference": dispatch_sheet
					}).insert(ignore_permissions=True)
					
					frappe.msgprint(f"✓ Replacement QR Code <b>{replacement_qr}</b> created and marked as Returned.")
				except Exception as e:
					frappe.msgprint(f"❌ Error creating replacement QR: {str(e)}")
			else:
				frappe.msgprint(f"✓ QR Code <b>{dispatched_log.qr_code}</b> marked as Destroyed (unreadable, no replacement).")
			
			frappe.msgprint(f"--- Completed invalid item {i+1} ---")
	else:
		frappe.msgprint("❌ No invalid_items field found on document")
		
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