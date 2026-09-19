# Suntech sandbox: verified contract facts

Read from the live sandbox API reference on 19-09-2026, section by section.
Base: `https://portal-sandbox.taxcomplianceagent.com/api/v1` (§1.3). The
reference is public; the portal itself needs a login. Everything below is
Verified against the published text unless marked Proposed.

## Authentication (§3)

- OAuth2 client credentials at `POST /oauth/token/` (form-encoded
  client_id/client_secret). Access token 600 s, refresh token 7 days,
  refresh at `POST /oauth/token/refresh/` with ROTATION: the old refresh
  token dies on every refresh, reuse fails with `invalid_grant`.
- One API client = one organisation (§4.1). Two TINs therefore means two
  API clients and two connection records.
- Permissions per client: invoice:view, invoice:submit, document:view,
  document:upload, document:delete, document:download. 403 when missing.
- Guidance §3.5: on 401 refresh once and retry; a second 401 means
  deactivated or compromised, surface to an operator.
- Simplest safe client behaviour for a worker that builds its connection
  fresh per operation: client-credentials grant per run, cached in the
  in-memory session for the operation's own requests. Refresh-token
  persistence is an optimisation we do not need (Proposed).

## Submission, XML-first (§5, §8.1)

Three calls: `POST /documents/` reserves a slot (name + extension) and
returns `path` + a presigned S3 `upload_url` (3600 s); `PUT` the XML bytes
to that URL (no auth header, S3 host); `POST /invoices/` with
`{name, invoice_number, issue_date, invoice_type_code, source_file_path}`.

- The presigned upload and download URLs live on an S3 host, not the API
  host. The transport's trusted-host policy must therefore carry the S3
  host for this adapter, or the second call is refused as untrusted.
- 201 means accepted and queued, NOT validated (§5.4). Validation of an
  XML upload is asynchronous; a PINT AE failure appears later as status
  Rejected with the rule id in `internal_validation_error_message`.
- `invoice_number` must be unique per organisation per issue year across
  sent invoices; a duplicate returns 400 at step 3 (§5.5, §13.5).
- BTAE-07 is assigned by the platform; a value in our XML is overridden on
  the wire copy (§5.3). Original XML preserved at `source_file_path`;
  signed wire copy is a separate file at `invoice_xml_location_path`.
- Errors at step 3: 400 duplicate number/path problems, 403 client
  deactivated, missing permission, or organisation not Registered.

## Status model (§4.2, §8.1, §14)

`status`: 1 Processing, 2 Completed, 3 Rejected (internal validation,
fatal rule), 4 Failed (downstream C3/C5). List rows carry only `status`
and `can_resubmit`; the three underlying fields are detail-only.

- `internal_validation_status`: 0 N/A, 1 Processing, 2 Failed, 3 Passed.
- `c3_mls_status` (receiving AP): 0 N/A, 1 Yet to Send, 2 Sending,
  3 Waiting for MLS, 4 Accepted, 5 Rejected, 6 Unable to Deliver.
- `c5_mls_status` (FTA): 0 N/A, 1 Yet to Send, 2 Sending, 3 Waiting,
  4 Accepted, 5 Sending Withdraw Request, 6 Waiting for Withdraw MLS,
  7 Withdraw Accepted. Withdraw is portal-driven; no API endpoint.
- Completed = c3 4 and c5 4, usually within seconds (§5.4).

Mapping onto the app's independent dimensions (Proposed, to be pinned by
adapter tests): platform 201 = ASP receipt Received; internal validation
2 = ASP receipt Rejected with rule findings; c3 4 = exchange Delivered,
c3 5/6 = exchange Rejected, c3 1-3 = Pending; c5 4 = reporting Accepted,
c5 1-3 = Pending, c5 5/6/7 = Unknown and hold for a person (a withdrawal
happened outside our flow).

## Idempotency and retries (§13.4, §13.5)

- NO client-supplied idempotency keys in v1.
- The dedup net is `invoice_number` uniqueness per organisation per issue
  year: a double submission fails the second time with 400.
- Documented recovery pattern is check-then-retry: on a lost response,
  search `GET /invoices/?search=<invoice-number>` and only retry the POST
  when nothing is found. This is exactly the app's reconcile-first rule;
  find_submission maps to that search.
- 429 is reserved; no application-level limit today. If it appears, honour
  Retry-After (the app already does).

## Resubmission (§4.6, §8.1)

`PUT /invoices/{id}/resubmit/` only when `can_resubmit` (Rejected/Failed).
Full replacement, same shape as POST, `invoice_number` immutable and must
be OMITTED (400 if present). ID preserved, previous payload discarded,
lifecycle restarts. Completed is immutable; correct commercially with a
credit note. In app terms: resubmit belongs to the correction path (new
revision, new approval), never to a transport retry.

## Receiving (§11)

- Pull: `GET /invoices/?direction=2&invoice_type_code__in=380,381,480,81`.
- Poll anchor: `after=<last-processed-id>` returns only rows created after
  that id AND at least 60 seconds old (settle window), so a row being
  written can never be skipped past. Cannot combine with created_at
  bounds. IDs are time-sortable UUIDv7, newest first. This anchor is the
  durable inbound cursor.
- List rows carry `invoice_xml_location_path`; the signed XML is the legal
  record to archive (§11.1). Download via `POST /documents/download/`
  with `s3_uri`, then GET the presigned URL (S3 host again).
- Received documents: internal_validation and c3 stay 0 (N/A), status is
  Completed on arrival, c5 advances as the receiving AP's own TDD is
  acknowledged.
- Delivery of a type only happens after the organisation enables it in
  portal Settings (receive_invoice, receive_credit_note): the SMP listing
  is what tells the sender's AP it may deliver. Silence, not an error,
  while off. This is a portal step for the buyer-side TIN.
- Supplier credit notes name the corrected invoice in
  `preceding_invoice_references[]`; match on that, not invoice_number,
  except reason code VD which carries no reference (matches the app's
  pinned volume-discount exception).

## Documents (§8.2)

- `POST /documents/` name 1-255 (letters, digits, `. _ ( ) -`, starting
  alphanumeric), extension whitelist incl. xml. Presigned PUT within
  3600 s, Content-Type must match.
- `POST /documents/download/` takes `id` or `s3_uri` (must belong to the
  organisation), returns presigned GET URL, 3600 s.

## Errors (§13)

- 400 validation: DRF flat dict of field -> list of messages,
  `non_field_errors` for top-level.
- 401/403/404/409/5xx: `{"detail": "..."}`. OAuth endpoints:
  `{"error": "invalid_request|invalid_client|invalid_grant"}`.
- 404 also covers another organisation's resource (no existence leak).

## Webhooks (§12, noted only)

invoice.received / invoice.updated POSTs, configured in the portal, no
API management. The app stays pull-based for P10; the after-anchor poll is
the documented backstop pattern. Event ingestion remains reserved.

## Consequences for the adapter (Proposed, implemented in P10 S2/S3)

- Capability map per spec 9.4 confirmed: authenticate, submit, get_status,
  fetch_artifact, fetch_inbound supported; find_submission via the
  documented search-by-invoice-number; lookup_participant and withdraw
  absent from the API, stay Unsupported.
- The adapter must declare the S3 host as an additional trusted host for
  its transport policy, or uploads and downloads are refused.
- Reconciliation needs the document number available to find_submission,
  so the reconcile call carries it in provider_ids.
