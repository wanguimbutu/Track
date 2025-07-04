// Copyright (c) 2025, wanguimbutu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Delivery Return', {
    refresh(frm) {
        
        if (!frm.is_new() && frm.doc.docstatus === 1) {
            frm.add_custom_button('Create Delivery Note Return', () => {
                frappe.call({
                    method: 'track.track.doctype.delivery_return.delivery_return.create_delivery_note_returns',
                    args: {
                        docname: frm.doc.name
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint(__('Delivery Note Return(s) created in draft.'));
                            frappe.reload_doc();
                        }
                    }
                });
            });
        }
    },
     onload: function(frm) {
    if (frm.is_new() && !frm.doc.date) {
      frm.set_value('date', frappe.datetime.get_today());
    }
  }
});
