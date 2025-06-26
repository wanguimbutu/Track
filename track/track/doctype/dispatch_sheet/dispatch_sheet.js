// Copyright (c) 2025, wanguimbutu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Dispatch Sheet', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button('Fetch QR Code Details', () => {
                frappe.call({
                    method: 'track.track.doctype.dispatch_sheet.dispatch_sheet.fetch_qr_details_for_dispatch',
                    args: {
                        docname: frm.doc.name
                    },
                    freeze: true,
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint('QR Code details fetched successfully');
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
    }
});
