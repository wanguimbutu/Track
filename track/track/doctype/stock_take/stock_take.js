// Copyright (c) 2025, wanguimbutu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Stock Take', {
    refresh: function(frm) {
        frm.add_custom_button(__('Update from Scan Log'), function() {
            frappe.call({
                method: "track.track.doctype.stock_take.stock_take.update_stock_take_details",
                args: {
                    docname: frm.doc.name
                },
                callback: function(r) {
                    if (!r.exc) {
                        frappe.msgprint("Stock Take Details updated from Scan Log.");
                        frm.reload_doc();
                    }
                }
            });
        });
    }
});
 /*frappe.ui.form.on('Stock Take Table', {
    qr_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.qr_code) return;

        frappe.msgprint(`🔍 Checking QR Code: ${row.qr_code}`);

        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Scan Log",
                filters: {
                    qr_code: row.qr_code
                },
                fieldname: ["item_code", "status"]
            },
            callback: function(r) {
                if (r.message) {
                    const item_code = r.message.item_code;
                    const status = r.message.status;

                    frappe.model.set_value(cdt, cdn, "item_code", item_code);
                    frappe.model.set_value(cdt, cdn, "status", status);

                    frappe.msgprint(`✅ Found in Scan Log: Item - ${item_code || "N/A"}, Status - ${status || "N/A"}`);
                } else {
                    frappe.model.set_value(cdt, cdn, "item_code", "");
                    frappe.model.set_value(cdt, cdn, "status", "");
                    frappe.msgprint(` QR Code ${row.qr_code} not found in Scan Log.`);
                }
            }
        });
    }
});
*/