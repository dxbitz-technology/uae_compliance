# Testing P02 by hand

Nineteen cases covering the configuration and master records. They take about
forty minutes. Everything is on the development site and nothing here sends
anything anywhere.

Each case says what to do and what you should see. Where a case is about
something being refused, the refusal is the pass.

## Before you start

The site needs one line in your hosts file, which needs your password:

```bash
echo "127.0.0.1 uae.local" | sudo tee -a /etc/hosts
```

Then start the bench and open the site:

```bash
cd /Users/aslam/frappe-local/loc16 && bench start
```

Go to `http://uae.local:8002` and sign in as Administrator. Everything below is
reached from the search bar at the top by typing the record name.

## A. A fresh site does nothing

| # | Do this | You should see |
| --- | --- | --- |
| A1 | Open a sales invoice, any one, or make a draft | Nothing about e-invoicing anywhere on the form. No new tab, no notice, no extra fields. The app is installed and the invoice is untouched. |
| A2 | Open UAE Peppol Settings | Pause outbound is off. Five attempts, first delay 30 seconds, maximum 900. |
| A3 | Look at the Installed Rules section | It names PINT AE Billing 1.0.4 and cannot be edited. Rules ship with the release and are never fetched at runtime. |
| A4 | Search for UAE Peppol Seller Profile | The list is empty. Nothing is switched on until somebody sets it up. |

## B. The settings refuse what cannot work

| # | Do this | You should see |
| --- | --- | --- |
| B1 | Set maximum attempts to 0 and save | Refused. There must be at least one attempt. |
| B2 | Set the maximum delay to 10 and the first delay to 30, then save | Refused. The maximum cannot be shorter than the first. |
| B3 | Tick pause outbound and save without a reason | Refused. A pause has to say why, so somebody finding it later knows. |
| B4 | Add a reason and save | Saves. Untick it again afterwards. |

## C. The provider connection

| # | Do this | You should see |
| --- | --- | --- |
| C1 | Create a UAE Peppol ASP. Label "Test Provider", provider "example", environment Simulation | Saves. Enabled is off and the connection state says Not checked. Nothing was contacted. |
| C2 | Add a credential row: key `client_secret`, secret `hello-secret`. Save | Saves. Reopen the form: the secret shows as dots, never as text. |
| C3 | Add a second row with the same key `client_secret`. Save | Refused. The same key twice would make it ambiguous which one is used. |
| C4 | Change the environment to Sandbox and save | Saves. Nothing has gone through it yet, so it is still free to change. |

## D. A connection settles once it has been used

This is the one worth taking slowly. Marking it as used by hand stands in for
the app having sent something through it.

| # | Do this | You should see |
| --- | --- | --- |
| D1 | In the terminal, mark the connection used: see the command below | It reports the update. |
| D2 | Reload the form and change the environment to Production. Save | Refused, saying the connection has been used and a new one is needed. |
| D3 | Change the provider instead. Save | Refused for the same reason. |
| D4 | Change the secret on the existing credential row. Save | Saves. Rotating a credential is expected; changing who is on the other end is not. |

```bash
cd /Users/aslam/frappe-local/loc16 && bench --site uae.local execute frappe.db.set_value --args '["UAE Peppol ASP", "Test Provider", "has_been_used", 1]'
```

Why this matters: old submissions stay bound to the connection that carried
them. Repointing one at a different provider, or from sandbox to production,
would quietly change what those records mean.

## E. Credentials do not outlive their record

| # | Do this | You should see |
| --- | --- | --- |
| E1 | Add a second credential, key `client_id`, secret `hello-id`. Save | Saves. |
| E2 | Run the credential count command below | It reports 2. |
| E3 | Delete the `client_id` row from the table. Save | Saves. |
| E4 | Run the count again | It reports 1. The stored secret went with the row. |
| E5 | Delete the whole connection | Deletes. |
| E6 | Run the count again | It reports 0. Nothing was left behind. |

```bash
cd /Users/aslam/frappe-local/loc16 && bench --site uae.local mariadb -e "select count(*) as stored_secrets from __Auth where doctype='UAE Peppol ASP Credential'"
```

## F. A seller profile saves while it is incomplete

| # | Do this | You should see |
| --- | --- | --- |
| F1 | Create a UAE Peppol Seller Profile with only a label | Saves. No tax number, no identifier, nothing. The details arrive later than the first invoice does. |
| F2 | Look at Identity Checked | It says Not checked and cannot be edited. |
| F3 | Add your company to the Companies table and save | Saves. The mode is Off and Review Required is on. |
| F4 | Change that company's mode to Live and save without a date | Refused. Going live is a decision and needs a date it takes effect from. |
| F5 | Add the date and save | Saves. Set it back to Off afterwards. |
| F6 | Create a second seller profile and add the same company | Refused, naming the profile that already has it. A company belongs to one seller. |

## G. Nobody can verify themselves

| # | Do this | You should see |
| --- | --- | --- |
| G1 | On the seller profile, try to set Identity Checked to Verified | The field is read only, so you cannot. |
| G2 | Create a UAE Peppol Party Profile for a customer. Set On the Network to Registered. Save | Saves. That is what somebody told us. |
| G3 | Look at Lookup Result on the same form | Still Not checked. A claim and evidence are two different fields and never touch. |

## H. Party profiles

| # | Do this | You should see |
| --- | --- | --- |
| H1 | Create a party profile for a customer with nothing else filled in | Saves. Context, VAT and network all say Not sure. |
| H2 | Create a second profile for the same customer | Refused, saying that customer already has one. |
| H3 | On a foreign customer, fill in both the VAT number and the Additional UAE Registration | Both save and neither overwrites the other. A foreign party can hold a UAE registration as well as its own. |

## I. Tax mapping

| # | Do this | You should see |
| --- | --- | --- |
| I1 | Create a UAE Peppol Tax Category with a company and a category but no account and no template | Refused. A mapping needs something to match on. |
| I2 | Add a tax account, category S, rate 5. Save | Saves. |
| I3 | Create a second mapping with the same company and the same account | Refused, naming the one that already matches. Picking the first of two would make the tax on an invoice depend on row order. |
| I4 | Open the Tax Category dropdown | Six options: S, E, O, AE, Z, N. There is no M. Margin is the letter N. |
| I5 | Create a mapping with category E and no reason | Refused. An exempt line has to say why. |

## J. Installing again changes nothing

| # | Do this | You should see |
| --- | --- | --- |
| J1 | Run the migrate command below twice | Both finish with no errors. |
| J2 | Check the roles and settings with the command below | Two roles, one settings record. Nothing doubled. |
| J3 | Open any sales invoice again | Still untouched. The app has added no fields to anything it does not own. |

```bash
cd /Users/aslam/frappe-local/loc16 && bench --site uae.local migrate && bench --site uae.local migrate
```

```bash
cd /Users/aslam/frappe-local/loc16 && bench --site uae.local mariadb -e "select (select count(*) from tabRole where role_name like 'UAE Peppol%') as roles, (select count(*) from \`tabCustom Field\` where fieldname like 'uae_peppol%') as our_fields_on_native_doctypes"
```

## What is not covered here

Two things a person cannot easily check from the desk, both covered by the
automated tests instead.

Permissions for a restricted user. Doing it by hand means creating a user,
giving it only the UAE Peppol User role, and signing in as it. Worth doing
once before the phase is accepted, but it is slow and the automated tests
already cover it.

Anything that sends. Nothing in this phase talks to a provider, so there is
nothing to see. That begins at P06 and only against a simulator.

## If something fails

Tell me the case number and what you saw. If it is a refusal that should have
been allowed, the exact message helps. Nothing here writes to any system other
than the development site, so there is nothing to undo.
