// One button on the company form, and only when there is something to do.

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "UAE Peppol Seller Company",
				filters: { company: frm.doc.name, parenttype: "UAE Peppol Seller Profile" },
				fieldname: ["parent", "mode"],
			},
			callback: (reply) => {
				const bound = reply.message && reply.message.parent;
				if (bound) {
					frm.dashboard.set_headline_alert(
						__("e-Invoicing: {0}, under {1}", [__(reply.message.mode), reply.message.parent]),
						reply.message.mode === "Live" ? "green" : "blue"
					);
					return;
				}
				frm.add_custom_button(__("Set up e-Invoicing"), () => {
					frappe.confirm(
						__(
							"This puts {0} into Preparation. It will collect and check invoices and send nothing. Going live is a separate decision.",
							[frm.doc.name]
						),
						() => {
							frappe.call({
								method: "uae_compliance.services.party_entry.set_up_company",
								args: { company: frm.doc.name },
								freeze: true,
								callback: () => frm.reload_doc(),
							});
						}
					);
				});
			},
		});
	},
});
