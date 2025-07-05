# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

class StockTake(Document):
    def on_submit(self):
        self.create_stock_variance()

    def create_stock_variance(self):
        item_qty_map = {}
        stock_take_qr_codes = set()

        # Step 1: Collect data from stock take
        for row in self.stock_take_details:
            if row.item_code:
                item_qty_map.setdefault(row.item_code, 0)
                item_qty_map[row.item_code] += 1

            if row.qr_code:
                stock_take_qr_codes.add(row.qr_code)

        # Step 2: Get relevant QR codes from Scan Log (status: FG Store, Returned, Manufactured)
        valid_statuses = ["FG Store", "Returned", "Manufactured"]
        scan_qr_entries = frappe.get_all("Scan Log",
            filters={"status": ["in", valid_statuses]},
            fields=["qr_code", "status"]
        )

        scan_qr_code_map = {entry.qr_code: entry.status for entry in scan_qr_entries}

        # Step 3: Identify missing QR codes
        all_valid_qr_codes = set(scan_qr_code_map.keys())
        missing_qr_codes = all_valid_qr_codes - stock_take_qr_codes

        # Step 4: Create Stock Variance document
        variance_doc = frappe.new_doc("Stock Variance")
        variance_doc.date = self.date
        variance_doc.stock_take = self.name

        for item_code, stock_take_qty in item_qty_map.items():
            system_qty = get_current_stock_qty(item_code)
            variance = flt(stock_take_qty) - flt(system_qty)

            variance_doc.append("stock_variance_details", {
                "item_code": item_code,
                "stock_take_qty": stock_take_qty,
                "system_qty": system_qty,
                "variance": variance
            })

        for qr_code in missing_qr_codes:
            variance_doc.append("qr_code_variance_details", {
                "qr_code": qr_code,
                "status": scan_qr_code_map.get(qr_code, "Missing")
            })

        variance_doc.insert(ignore_permissions=True)
        frappe.msgprint(f" Stock Variance <a href='/app/stock-variance/{variance_doc.name}'><b>{variance_doc.name}</b></a> created.")

def get_current_stock_qty(item_code):
    qty = frappe.db.get_value("Bin", {"item_code": item_code}, "actual_qty")
    return qty or 0


@frappe.whitelist()
def update_stock_take_details(docname):
    doc = frappe.get_doc("Stock Take", docname)
    updated = False
    messages = []

    for row in doc.get("stock_take_details", []):
        if row.qr_code:
            scan_log = frappe.get_value("Scan Log", {"qr_code": row.qr_code}, ["item_code", "status"], as_dict=True)
            if scan_log:
                row.set("item_code", scan_log.item_code)
                row.set("status", scan_log.status)
                updated = True
        else:
            messages.append("Empty QR Code found in one row")

    if updated:
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        messages.append("Stock Take updated and saved.")
    else:
        messages.append("No updates made.")

    frappe.msgprint("<br>".join(messages))

    return True