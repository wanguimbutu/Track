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
	- Mark returned QR codes as Returned
	- For invalid_items, destroy the original QR (if found)
	- Create replacement QR code if provided
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

		# Mark as returned
		frappe.db.set_value("Scan Log", scan_log_name, {
			"status": "Returned",
			"return_reference": doc.name,
			"return_date": doc.date
		})

	# --- 2. Process invalid_items (damaged/unreadable)
	if hasattr(doc, 'invalid_items'):
		frappe.msgprint(f"🟡 Found {len(doc.invalid_items)} invalid item(s)")

		for i, invalid in enumerate(doc.invalid_items):
			frappe.msgprint(f"🔁 Processing invalid item {i+1}")

			delivery_note = getattr(invalid, 'delivery_note', None)
			if not delivery_note:
				frappe.msgprint(f"❌ Missing Delivery Note in invalid item {i+1}. Skipping.")
				continue

			dispatch_sheet = frappe.db.get_value("Delivery Note", delivery_note, "custom_dispatch_sheet")
			if not dispatch_sheet:
				frappe.msgprint(f"❌ No Dispatch Sheet for Delivery Note {delivery_note}. Skipping.")
				continue

			# Look for any dispatched QR under the same dispatch reference
			dispatched_log = frappe.db.get_value(
				"Scan Log",
				{
					"dispatch_reference": dispatch_sheet,
					"status": "Dispatched"
				},
				["name", "qr_code", "item_code"],
				as_dict=True
			)

			if not dispatched_log:
				frappe.msgprint(f"❌ No dispatched QR found for Dispatch Sheet: {dispatch_sheet}. Skipping.")
				continue

			# Step 1: Mark old QR as Destroyed
			try:
				frappe.db.set_value("Scan Log", dispatched_log.name, {
					"status": "Destroyed",
					"return_reference": doc.name,
					"return_date": doc.date,
					"comments": f"Unreadable QR returned via {doc.name}"
				})
				frappe.msgprint(f"✅ Marked old QR ({dispatched_log.qr_code}) as Destroyed.")
			except Exception as e:
				frappe.msgprint(f"❌ Error marking QR as destroyed: {e}")
				continue

			# Step 2: Create Destruction Log
			try:
				frappe.get_doc({
					"doctype": "Destruction Log",
					"qr_code": dispatched_log.qr_code,
					"item_code": dispatched_log.item_code,
					"dispatch_reference": dispatch_sheet,
					"reason": f"Unreadable QR returned via {doc.name}",
					"return_reference": doc.name,
					"return_date": doc.date,
					"destroyed_by": frappe.session.user,
					"destruction_time": now_datetime()
				}).insert(ignore_permissions=True)
				frappe.msgprint("✅ Destruction Log created.")
			except Exception as e:
				frappe.msgprint(f"❌ Error creating Destruction Log: {e}")

			# Step 3: If replacement QR code is given
			replacement_qr_code = getattr(invalid, 'replacement_qr_code', None)
			if replacement_qr_code:
				replacement_qr = replacement_qr_code.strip()
				if frappe.db.exists("Scan Log", {"qr_code": replacement_qr}):
					frappe.msgprint(f"❌ Replacement QR Code {replacement_qr} already exists.")
					continue

				try:
					frappe.get_doc({
						"doctype": "Scan Log",
						"qr_code": replacement_qr,
						"item_code": dispatched_log.item_code,
						"status": "Returned",
						"return_reference": doc.name,
						"return_date": doc.date,
						"dispatch_reference": dispatch_sheet
					}).insert(ignore_permissions=True)
					frappe.msgprint(f"✅ Replacement QR Code {replacement_qr} created and marked as Returned.")
				except Exception as e:
					frappe.msgprint(f"❌ Error creating replacement QR Code {replacement_qr}: {e}")
			else:
				frappe.msgprint(f"ℹ️ No replacement QR Code provided. Only original was destroyed.")

	else:
		frappe.msgprint("⚠️ No invalid_items field found on the document.")

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

def create_inward_sbb(item_code, batch_no=None, serial_nos=None):
	if not item_code:
		return None
	doc = frappe.get_doc({
		"doctype": "Serial and Batch Bundle",
		"item_code": item_code,
		"batch_no": batch_no,
		"serial_nos": "\n".join(serial_nos or []),
		"type_of_transaction": "Inward"
	})
	doc.insert(ignore_permissions=True)
	return doc.name

@frappe.whitelist()
def create_delivery_note_returns(docname):
	try:
		delivery_return = frappe.get_doc("Delivery Return", docname)
		if not delivery_return.returned_items:
			frappe.throw("No returned items found in Delivery Return")

		created_notes = []
		deliveries = {}

		for row in delivery_return.returned_items:
			if not row.delivery_note:
				frappe.throw(f"Delivery Note missing for QR Code: {row.qr_code}")
			dn = row.delivery_note
			if dn not in deliveries:
				deliveries[dn] = {}
			item_code = row.item_code
			if item_code not in deliveries[dn]:
				deliveries[dn][item_code] = {
					'qty': 0,
					'qr_codes': []
				}
			deliveries[dn][item_code]['qty'] += 1
			deliveries[dn][item_code]['qr_codes'].append(row.qr_code)

		for dn_name, items_data in deliveries.items():
			try:
				original_dn = frappe.get_doc("Delivery Note", dn_name)
				if original_dn.docstatus != 1:
					frappe.throw(f"Delivery Note {dn_name} is not submitted")

				return_doc = frappe.new_doc("Delivery Note")
				return_doc.customer = original_dn.customer
				return_doc.company = original_dn.company
				return_doc.posting_date = delivery_return.date or today()
				return_doc.posting_time = nowtime()
				return_doc.is_return = 1
				return_doc.return_against = dn_name

				for field in [
					'vehicle_no', 'driver_name', 'driver', 'transporter',
					'transporter_name', 'lr_no', 'lr_date', 'currency', 'conversion_rate',
					'selling_price_list', 'price_list_currency', 'plc_conversion_rate',
					'ignore_pricing_rule', 'set_warehouse', 'target_warehouse', 'tc_name',
					'terms', 'customer_address', 'shipping_address_name', 'contact_person',
					'territory', 'sales_team'
				]:
					if hasattr(original_dn, field) and getattr(original_dn, field):
						setattr(return_doc, field, getattr(original_dn, field))

				for item_code, item_data in items_data.items():
					original_item = next((item for item in original_dn.items if item.item_code == item_code), None)
					if not original_item:
						frappe.throw(f"Item {item_code} not found in Delivery Note {dn_name}")

					new_sbb = None
					if getattr(original_item, 'serial_and_batch_bundle', None):
						sbb = frappe.get_doc("Serial and Batch Bundle", original_item.serial_and_batch_bundle)
						if sbb.transaction_type == "Outward":
							new_sbb = create_inward_sbb(
								item_code=item_code,
								batch_no=sbb.batch_no,
								serial_nos=sbb.serial_nos.split("\n") if sbb.serial_nos else []
							)

					return_doc.append("items", {
						"item_code": item_code,
						"item_name": original_item.item_name,
						"description": original_item.description,
						"qty": -abs(item_data['qty']),
						"uom": original_item.uom,
						"rate": original_item.rate,
						"warehouse": original_item.warehouse,
						"expense_account": getattr(original_item, 'expense_account', None),
						"cost_center": getattr(original_item, 'cost_center', None),
						"against_delivery_note": dn_name,
						"dn_detail": original_item.name,
						"against_sales_order": getattr(original_item, 'against_sales_order', None),
						"so_detail": getattr(original_item, 'so_detail', None),
						"serial_and_batch_bundle": new_sbb
					})

				if hasattr(return_doc, 'custom_returned_qr_codes'):
					for item_code, item_data in items_data.items():
						for qr_code in item_data['qr_codes']:
							return_doc.append("custom_returned_qr_codes", {
								"qr_code": qr_code,
								"qr_return_reference": delivery_return.name
							})

				return_doc.flags.ignore_validate_update_after_submit = True
				return_doc.flags.ignore_permissions = True
				return_doc.insert(ignore_permissions=True)

				if delivery_return.get('auto_submit_returns'):
					return_doc.submit()

				created_notes.append(return_doc.name)

			except Exception as e:
				frappe.log_error(str(e), "Delivery Return Creation Error")
				frappe.throw(f"Error creating return for Delivery Note {dn_name}: {e}")

		if created_notes:
			frappe.msgprint(f"Created Delivery Note Returns:<br><b>{'<br>'.join(created_notes)}</b>")
		else:
			frappe.msgprint("No Delivery Note Returns were created")
		return created_notes

	except Exception as e:
		frappe.log_error(str(e), "Delivery Return Function Error")
		frappe.throw(f"Error creating delivery note returns: {e}")