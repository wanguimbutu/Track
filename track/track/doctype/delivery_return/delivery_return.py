# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt
 
import frappe
from frappe.model.document import Document
from frappe.utils import today, nowtime

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
                
                # Copy other essential fields
                fields_to_copy = [
                    'currency', 'conversion_rate', 'selling_price_list',
                    'price_list_currency', 'plc_conversion_rate', 'ignore_pricing_rule',
                    'set_warehouse', 'target_warehouse', 'tc_name', 'terms',
                    'customer_address', 'shipping_address_name', 'contact_person'
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
                    
                    # Add return item
                    return_doc.append("items", {
                        "item_code": item_code,
                        "item_name": original_item.item_name,
                        "description": original_item.description,
                        "qty": item_data['qty'],  # Positive quantity for returns
                        "uom": original_item.uom,
                        "rate": original_item.rate,
                        "warehouse": original_item.warehouse,
                        "expense_account": getattr(original_item, 'expense_account', None),
                        "cost_center": getattr(original_item, 'cost_center', None),
                        "against_delivery_note": dn_name,
                        "dn_detail": original_item.name,
                        "against_sales_order": getattr(original_item, 'against_sales_order', None),
                        "so_detail": getattr(original_item, 'so_detail', None)
                    })
                
                # Add custom QR codes tracking
                if hasattr(return_doc, 'custom_returned_qr_codes'):
                    for item_code, item_data in items_data.items():
                        for qr_code in item_data['qr_codes']:
                            return_doc.append("custom_returned_qr_codes", {
                                "qr_code": qr_code,
                                "qr_return_reference": delivery_return.name
                            })
                
                # Save the return document
                return_doc.insert(ignore_permissions=True)
                
                # Submit if auto-submit is enabled
                if delivery_return.get('auto_submit_returns'):
                    return_doc.submit()
                
                created_notes.append(return_doc.name)
                
            except Exception as e:
                frappe.log_error(f"Error creating return for {dn_name}: {str(e)}")
                frappe.throw(f"Error creating return for Delivery Note {dn_name}: {str(e)}")

        if created_notes:
            frappe.msgprint(f"Created Delivery Note Returns:<br><b>{'<br>'.join(created_notes)}</b>")
        else:
            frappe.msgprint("No Delivery Note Returns were created")
            
        return created_notes
        
    except Exception as e:
        frappe.log_error(f"Error in create_delivery_note_returns: {str(e)}")
        frappe.throw(f"Error creating delivery note returns: {str(e)}")