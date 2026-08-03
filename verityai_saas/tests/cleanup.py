import frappe


SAAS_WORKSPACE_DOCTYPES = (
	"VerityAI Email Delivery Log",
	"VerityAI Integration Status",
	"VerityAI WhatsApp Setup",
	"VerityAI Notification Setting",
	"VerityAI Onboarding Checklist",
	"VerityAI Billing Event",
	"VerityAI Usage Transaction",
	"VerityAI Usage Wallet",
	"VerityAI Subscription",
	"VerityAI Workspace Member",
)

ENGINE_TENANT_DOCTYPES = (
	"AI Knowledge Chunk",
	"AI Knowledge Source",
	"AI Lead",
	"AI Usage Log",
	"AI Monitoring Alert",
	"AI Action Approval",
	"AI Quotation Request",
	"AI Tool Call Log",
	"AI Chat Session",
	"AI Configuration",
)


def cleanup_test_workspace(workspace_name, users=None, commit=True, engine_tenant=None):
	frappe.set_user("Administrator")
	workspace = frappe.db.get_value(
		"VerityAI Workspace",
		workspace_name,
		["account", "engine_tenant"],
		as_dict=True,
	)
	if workspace:
		engine_tenant = engine_tenant or workspace.engine_tenant
		for doctype in SAAS_WORKSPACE_DOCTYPES:
			frappe.db.delete(doctype, {"workspace": workspace_name})
		frappe.db.delete("VerityAI Workspace", {"name": workspace_name})
	if engine_tenant:
		frappe.db.delete("AI Allowed Domain", {"parent": engine_tenant})
		for doctype in ENGINE_TENANT_DOCTYPES:
			frappe.db.delete(doctype, {"tenant": engine_tenant})
		frappe.db.delete("AI Tenant", {"name": engine_tenant})
	if workspace and workspace.account and not frappe.db.exists("VerityAI Workspace", {"account": workspace.account}):
		frappe.db.delete("VerityAI Account", {"name": workspace.account})
	for user in users or []:
		if user not in {"Administrator", "Guest"} and frappe.db.exists("User", user):
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
	cleanup_orphan_test_tenants(commit=False)
	if commit:
		frappe.db.commit()

def cleanup_all_test_fixtures():
	patterns = ("owner-%@example.com", "portal-%@example.com", "quote-owner-%@example.com", "health-owner-%@example.com")
	workspaces = []
	for pattern in patterns:
		workspaces.extend(
			frappe.get_all("VerityAI Workspace", filters={"owner_user": ["like", pattern]}, pluck="name")
		)
	for workspace_name in sorted(set(workspaces)):
		users = frappe.get_all(
			"VerityAI Workspace Member",
			filters={"workspace": workspace_name},
			pluck="user",
		)
		cleanup_test_workspace(workspace_name, users=users, commit=False)
	for pattern in ("other-%@example.com", "quote-other-%@example.com", "health-other-%@example.com"):
		for user in frappe.get_all("User", filters={"name": ["like", pattern]}, pluck="name"):
			frappe.delete_doc("User", user, ignore_permissions=True, force=True)
	cleanup_orphan_test_tenants(commit=False)
	frappe.db.commit()
	return len(set(workspaces))


def cleanup_orphan_test_tenants(commit=True):
	tenant_names = set(
		frappe.get_all(
			"AI Tenant",
			filters={"name": ["like", "other-%"], "assistant_name": "Other"},
			pluck="name",
		)
	)
	tenant_names.update(
		frappe.get_all(
			"AI Tenant",
			filters={"tenant_name": ["like", "Test Tenant %"], "assistant_name": "Verity AI"},
			pluck="name",
		)
	)
	for tenant in tenant_names:
		frappe.db.delete("AI Allowed Domain", {"parent": tenant})
		for doctype in ENGINE_TENANT_DOCTYPES:
			frappe.db.delete(doctype, {"tenant": tenant})
		frappe.db.delete("AI Tenant", {"name": tenant})
	if commit:
		frappe.db.commit()
