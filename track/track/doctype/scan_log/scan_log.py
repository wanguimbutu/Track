# Copyright (c) 2025, wanguimbutu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from frappe import _
import os

class ScanLog(Document):
	pass


def validate_qr_code_exists(doc, method):
    qr_code_value = doc.qr_code

    # Securely load from config or environment
    api_key = frappe.conf.get("site_b_api_key") or os.getenv("SITE_B_API_KEY")
    api_secret = frappe.conf.get("site_b_api_secret") or os.getenv("SITE_B_API_SECRET")

    url = "https://site-b.example.com/api/method/code_tracking.code_tracking.doctype.qr_codes.qr_codes.check_qr_exists"
    response = requests.get(
        url,
        params={"qr_code": qr_code_value},
        headers={"Authorization": f"token {api_key}:{api_secret}"}
    )

    if response.status_code != 200 or not response.json().get("message"):
        frappe.throw(_("Invalid QR Code: {0}").format(qr_code_value))
