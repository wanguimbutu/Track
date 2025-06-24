# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StockVariance(Document):
    def on_submit(self):
        self.create_stock_reconciliation()
        self.reconcile_missing_qr_codes()

    def create_stock_reconciliation(self):
        if not self.stock_variance_details:
            frappe.msgprint("No variance details to reconcile.")
            return

        reconciliation = frappe.new_doc("Stock Reconciliation")
        reconciliation.purpose = "Stock Reconciliation"
        reconciliation.posting_date = self.date
        reconciliation.company = frappe.defaults.get_user_default("Company")
        reconciliation.set_posting_time = 1
        reconciliation.stock_variance = self.name  # optional custom field in Stock Reconciliation

        for row in self.stock_variance_details:
            if not row.item_code:
                continue

            reconciliation.append("items", {
                "item_code": row.item_code,
                "qty": row.stock_take_qty,
                "warehouse": row.warehouse,  
            })

        reconciliation.insert(ignore_permissions=True)
        # reconciliation.submit()  # Optional auto-submit

        frappe.msgprint(
            f"Stock Reconciliation <a href='/app/stock-reconciliation/{reconciliation.name}'><b>{reconciliation.name}</b></a> created."
        )

    def reconcile_missing_qr_codes(self):
        reconciled = []
        already_exists = []

        for row in self.qr_code_variance_details:
            qr_code = row.qr_code
            if not qr_code:
                continue

            if not frappe.db.exists("QR Codes", qr_code):
                continue

            # Prevent duplicates: check if Scan Log already has an entry for this qr_code and status = Reconciled
            existing = frappe.db.exists("Scan Log", {"qr_code": qr_code, "status": "Reconciled"})
            if existing:
                already_exists.append(qr_code)
                continue

            # Fetch item_code from QR Codes
            item_code = frappe.db.get_value("QR Codes", qr_code, "item_code")

            # Create Scan Log entry marking this QR code as Reconciled
            scan_log = frappe.new_doc("Scan Log")
            scan_log.qr_code = qr_code
            scan_log.item_code = item_code
            scan_log.status = "Reconciled"
            scan_log.save(ignore_permissions=True)

            reconciled.append(qr_code)

        if reconciled:
            frappe.msgprint(f"{len(reconciled)} QR Code(s) marked as <b>Reconciled</b> in Scan Log:<br>{', '.join(reconciled)}")
        if already_exists:
            frappe.msgprint(f"These QR Code(s) were already marked as Reconciled:<br>{', '.join(already_exists)}")
