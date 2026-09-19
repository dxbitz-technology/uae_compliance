frappe.query_reports["UAE e-Invoicing Reconciliation"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "issue" && data) {
			// Only the two that mean something may have gone wrong outside
			// this system are marked red. The rest is ordinary tidying.
			const serious = ["A request with no answer", "Submitted, never looked at"];
			const colour = serious.indexOf(data.issue) !== -1 ? "red" : "orange";
			value = `<span class="indicator ${colour}">${value}</span>`;
		}
		return value;
	},
};
