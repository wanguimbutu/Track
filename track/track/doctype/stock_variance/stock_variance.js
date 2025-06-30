// Copyright (c) 2025, wanguimbutu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stock Variance", {
  onload: function(frm) {
    if (frm.is_new() && !frm.doc.date) {
      frm.set_value('date', frappe.datetime.get_today());
    }
  }
});

