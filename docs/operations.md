# Running this app

Short and practical. It covers the things that are easy to get wrong and
expensive when you do.

## Turning production sending on

Sending real invoices needs one line in the site's own configuration file.
It is not a field, and it is not in the database, because a database can be
restored somewhere else and a configuration file is not.

```bash
bench --site your-site.com set-config uae_peppol_production_send your-site.com
```

The value is the site name. A key granted for one site does not work on
another, so copying the file does not carry the permission with it.

Without this, a company can be set to Live and still send nothing. It will
collect, check and freeze, and the work will sit waiting.

## Restoring a backup, or making a copy

Do these in order.

1. Restore the database and the private files.
2. Start with the workers stopped, or with outbound paused.
3. On a copy that is not production, do not set the configuration key above.
   Without it the copy cannot send, whatever the database says.
4. On the real site moving to a new machine, sign in as a manager and
   confirm the move. Until somebody does, outbound work stays paused.

The app notices a move by itself. It records which machine it last sent from
and pauses everything when that changes, saying so in the pause reason. That
is deliberately a hold rather than a refusal: a genuine move should be a
minute of somebody's attention, not a silent failure.

A restored site also holds until it has caught up with what the provider
thinks. Anything that was in flight when the backup was taken has an unknown
outcome, and reconciliation settles those before new work goes out.

## Pausing

```bash
bench --site your-site.com execute frappe.client.set_value --args '["UAE Peppol Settings", "UAE Peppol Settings", {"pause_outbound": 1, "pause_reason": "why"}]'
```

A pause stops new sends and retries. It does not change what validation
says, throw queued work away, or stop the app finding out what happened to
something already sent. A pause always has to say why, so whoever finds it
later knows whether to lift it.

## What to watch

Two reports, both under the UAE e-Invoicing workspace.

**Readiness** lists invoices and what each one is missing. Filter by company,
readiness and date.

**Reconciliation** is the one to open when you want to know whether anything
has been forgotten. It finds work that fell between steps: an invoice
submitted with nothing watching it, a submission nobody approved, a request
that went out and never came back.

Managers also get one message a day when anything needs attention, and
nothing at all when nothing does.

## When a request has no answer

This is the case worth understanding. A request that went out and never came
back is not a failure. Something may be sitting at the provider with your
document in it.

The app never sends it again to find out. It asks the provider, and where
the provider offers no way to ask, it holds the work and tells somebody.
Duplicate invoices are a worse problem than a late one.

## Uninstalling

Do not, on a site that has sent anything. The submissions and their evidence
are the only record tying a document that left the system to the invoice it
came from. Export first, and keep the export for as long as the records have
to be kept.
