// What the invoice form shows about e-invoicing.
//
// It stays out of the way. On a company that is switched off there is nothing
// here at all: no button, no indicator, no extra field. On a company that is
// switched on there is one indicator and one button, both native.
//
// The checks themselves live on the server. This asks and displays. It does
// not decide anything, because a second set of rules in the browser is a
// second set of rules to keep right.

frappe.ui.form.on("Sales Invoice", {
	// Changing the company, the party or the address makes any earlier answer
	// say nothing about the invoice in front of us. The server marks the
	// record stale when the invoice is saved and the form redraws then, so
	// there is nothing for the browser to work out on its own.
	refresh(frm) {
		uae_compliance.invoice.show(frm);
	},
});

window.uae_compliance = window.uae_compliance || {};

uae_compliance.invoice = {
	// Readiness words and the native indicator colour each one takes.
	colours: {
		"Not checked": "gray",
		Stale: "orange",
		"Further checks required": "blue",
		"Needs details": "red",
		"Ready locally": "green",
		Unavailable: "orange",
		"Out of scope": "gray",
	},

	show(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "uae_compliance.services.api.get_readiness_batch",
			args: { source_names: JSON.stringify([frm.doc.name]) },
			callback: (reply) => {
				const state = (reply.message || {})[frm.doc.name];
				if (!state) return;
				this.draw(frm, state);
			},
		});
	},

	draw(frm, state) {
		// The native headline notice, which is the same one ERPNext uses for
		// its own messages. No new artwork and nothing bolted onto the form.
		const label =
			state.mode === "Preparation"
				? __("e-Invoicing: {0}. Preparation, so nothing is sent.", [__(state.readiness)])
				: __("e-Invoicing: {0}", [__(state.readiness)]);
		frm.dashboard.set_headline_alert(label, this.colours[state.readiness] || "gray");

		frm.add_custom_button(__("UAE e-Invoicing"), () => this.open(frm, state));
	},

	open(frm, state) {
		frappe.call({
			method: "uae_compliance.services.api.check_and_record",
			args: { source_name: frm.doc.name, level: "Full" },
			freeze: true,
			freeze_message: __("Checking"),
			callback: (reply) => this.dialog(frm, reply.message, state),
		});
	},

	dialog(frm, result, state) {
		const editable = frm.doc.docstatus === 0;
		const dialog = new frappe.ui.Dialog({
			title: __("UAE e-Invoicing"),
			size: "large",
			fields: this.fields(frm, result),
			// A submitted invoice has nothing to edit, so it gets no button
			// rather than one that would refuse.
			primary_action_label: editable ? __("Save details") : null,
			primary_action: editable ? (values) => this.save(frm, dialog, values, state) : null,
		});
		if (editable) this.fill(dialog, state);
		this.offer_item_fix(frm, dialog, result);
		dialog.show();
	},

	// One dialog for every item that needs the same thing, rather than the
	// same fix repeated once per row. Deduplicated by item, because an item
	// on three rows is one thing to fix.
	offer_item_fix(frm, dialog, result) {
		const rows = (result.findings || [])
			.filter((finding) => finding.row)
			.map((finding) => finding.row);
		if (!rows.length) return;

		const items = {};
		frm.doc.items.forEach((row) => {
			if (rows.indexOf(row.name) !== -1 && row.item_code) {
				items[row.item_code] = items[row.item_code] || [];
				items[row.item_code].push(row.idx);
			}
		});
		const codes = Object.keys(items);
		if (!codes.length) return;

		dialog.set_secondary_action_label(__("Fix {0} items", [codes.length]));
		dialog.set_secondary_action(() => this.item_dialog(frm, codes, items));
	},

	item_dialog(frm, codes, items) {
		const lines = codes
			.map((code) => {
				const where = __("row {0}", [items[code].join(", ")]);
				return `<li>${frappe.utils.escape_html(code)} <span class="text-muted small">${where}</span></li>`;
			})
			.join("");

		const fix = new frappe.ui.Dialog({
			title: __("Fix these items"),
			fields: [
				{ fieldtype: "HTML", options: `<ul>${lines}</ul>` },
				{
					fieldtype: "Select",
					fieldname: "item_type",
					label: __("These are"),
					options: ["", "Goods", "Services", "Both"],
					reqd: 1,
					description: __("Saved on the items themselves, so it applies everywhere they are used."),
				},
			],
			primary_action_label: __("Save on the items"),
			primary_action: (values) => {
				frappe.call({
					method: "uae_compliance.services.party_entry.set_item_type",
					args: { items: JSON.stringify(codes), item_type: values.item_type },
					freeze: true,
					callback: (reply) => {
						frappe.show_alert(__("Updated {0} items.", [reply.message || 0]));
						fix.hide();
					},
				});
			},
		});
		fix.show();
	},

	fill(dialog, state) {
		// What is already saved, so the dialog opens showing the current
		// answers rather than blank ones.
		frappe.db
			.get_doc("UAE Peppol Invoice", state.sales_invoice)
			.then((doc) => {
				Object.keys(dialog.fields_dict).forEach((fieldname) => {
					if (doc[fieldname] !== undefined) dialog.set_value(fieldname, doc[fieldname]);
				});
			})
			.catch(() => {});
	},

	fields(frm, result) {
		const fields = [
			{
				fieldtype: "HTML",
				fieldname: "summary",
				options: this.summary(result),
			},
		];

		if (frm.doc.docstatus !== 0) return fields;

		if (frm.doc.is_return) {
			fields.push(
				{ fieldtype: "Section Break", label: __("Why this credit note was issued") },
				{
					fieldtype: "Select",
					fieldname: "credit_reason_code",
					label: __("Reason"),
					options: ["", "DL8.61.1.A", "DL8.61.1.B", "DL8.61.1.C", "DL8.61.1.D", "DL8.61.1.E", "VD"],
					description: __("VD is the volume discount case, which needs no reference to the original invoice."),
				},
				{ fieldtype: "Data", fieldname: "credit_reason", label: __("Reason in words") }
			);
		}

		fields.push({ fieldtype: "Section Break", label: __("What kind of supply this is") });
		[
			["free_zone", __("Free zone")],
			["deemed_supply", __("Deemed supply")],
			["margin_scheme", __("Margin scheme")],
			["summary", __("Summary invoice")],
			["continuous_supply", __("Continuous supply")],
			["agent_billing", __("Billed by an agent")],
			["ecommerce", __("E-commerce")],
			["export", __("Export")],
		].forEach(([fieldname, label], index) => {
			if (index === 4) fields.push({ fieldtype: "Column Break" });
			fields.push({ fieldtype: "Check", fieldname, label });
		});
		return fields;
	},

	summary(result) {
		if (!result) return `<p>${__("Nothing to show yet.")}</p>`;
		const findings = result.findings || [];
		if (!findings.length) {
			return `<p>${__("Nothing needs attention. Checked {0}.", [result.checked_at])}</p>`;
		}

		// Grouped by where the fix is, so somebody can work through one place
		// at a time instead of jumping around the form.
		const groups = {};
		findings.forEach((finding) => {
			const where = this.place(finding);
			groups[where] = groups[where] || [];
			groups[where].push(finding);
		});

		let html = "";
		Object.keys(groups)
			.sort()
			.forEach((where) => {
				html += `<h5>${frappe.utils.escape_html(where)}</h5><ul>`;
				groups[where].forEach((finding) => {
					const colour = finding.severity === "Error" ? "red" : "orange";
					html += `<li><span class="indicator ${colour}">${frappe.utils.escape_html(finding.message)}</span>`;
					if (finding.repair) {
						html += `<br><span class="text-muted small">${frappe.utils.escape_html(finding.repair)}</span>`;
					}
					html += "</li>";
				});
				html += "</ul>";
			});
		return html;
	},

	place(finding) {
		const path = finding.path || "";
		if (path.startsWith("parties.seller")) return __("Your company");
		if (path.startsWith("parties.buyer")) return __("The customer");
		if (path.indexOf("address") !== -1) return __("Addresses");
		if (path.startsWith("lines")) return __("Items");
		return __("This invoice");
	},

	save(frm, dialog, values, state) {
		frappe.call({
			method: "uae_compliance.services.api.save_invoice_inputs",
			args: {
				source_name: frm.doc.name,
				expected_revision: state.input_revision || 0,
				inputs: JSON.stringify(values),
			},
			callback: () => {
				dialog.hide();
				frm.reload_doc();
			},
		});
	},
};
