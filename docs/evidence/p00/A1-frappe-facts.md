# A1 Frappe framework facts

Checked 17-09-2026 against the pinned checkout `apps/frappe` at tag v16.22.0, commit 567c05b6b7b736b52f08c372a620bd19cba168d1. All paths are repository relative. Status labels: Verified means read in the pinned source at the cited line. Proposed means a design choice that follows from verified facts. Unresolved means not established here.

---

## 1. Document lifecycle

### 1.1 Order of calls

| Action | Order of controller methods | Evidence | Status |
| --- | --- | --- | --- |
| Insert, draft | `before_insert`, `before_validate`, `validate`, `before_save`, DB insert of parent then children, `after_insert`, `on_update`, `on_change` | apps/frappe/frappe/model/document.py:460, 466, 477, 482, 485, 493 with apps/frappe/frappe/model/document.py:1347, 1353, 1396 | Verified |
| Save, existing draft | `before_validate`, `validate`, `before_save`, DB update, `on_update`, `on_change` | apps/frappe/frappe/model/document.py:568, 585, 588 with apps/frappe/frappe/model/document.py:1347, 1353, 1396 | Verified |
| Submit | `before_validate`, `validate`, `before_submit`, DB update, `on_update`, `on_submit`, `on_change` | apps/frappe/frappe/model/document.py:1347, 1356, 1398 | Verified |
| Cancel | `before_cancel`, DB update, `on_cancel`, `check_no_back_links_exist`, `on_change` | apps/frappe/frappe/model/document.py:1359, 1401 | Verified |
| Update after submit | `before_update_after_submit`, `validate_update_after_submit`, DB update, `on_update_after_submit`, `on_change` | apps/frappe/frappe/model/document.py:1361, 578, 1404 | Verified |

Exact insert sequence, with line numbers, at apps/frappe/frappe/model/document.py:455 to 494: `set_user_and_timestamp`, `set_docstatus`, `check_permission("create")`, `check_if_latest`, `_validate_links`, `before_insert`, `set_new_name`, `set_parent_in_children`, `validate_higher_perm_levels`, `run_before_save_methods`, `_validate`, `set_docstatus`, parent insert, child inserts, `after_insert`, `run_post_save_methods`. Status: Verified.

### 1.2 Individual facts

| Fact | Evidence | Status |
| --- | --- | --- |
| `before_insert` runs before `before_validate` and `validate`, not after | apps/frappe/frappe/model/document.py:460 (before) and :466 (run_before_save_methods) | Verified |
| `before_validate` fires only for actions save and submit. It does NOT fire on cancel or update after submit | apps/frappe/frappe/model/document.py:1347 | Verified |
| `before_validate` still fires when `flags.ignore_validate` is set. Everything after it in `run_before_save_methods` is skipped | apps/frappe/frappe/model/document.py:1346 to 1351 | Verified |
| `on_update` DOES fire during insert. The action for a new draft resolves to save | apps/frappe/frappe/model/document.py:1045, 1050, 1396 | Verified |
| `on_update` DOES fire during submit, immediately before `on_submit` | apps/frappe/frappe/model/document.py:1396 to 1399 | Verified |
| `on_update` does NOT fire on update after submit or on cancel | apps/frappe/frappe/model/document.py:1396 to 1404 | Verified |
| Inserting a document that already carries docstatus 1 resolves the action to submit, so a single `insert()` runs validate, `before_submit`, `on_update` and `on_submit` | apps/frappe/frappe/model/document.py:1066 to 1079 with :466 and :493 | Verified |
| `doc.flags.in_insert` is True during `before_validate`, `validate`, `before_save` and during `on_update`, `on_submit`, `on_change`. It is False during `after_insert` | apps/frappe/frappe/model/document.py:465, 469, 486, 494 | Verified |
| `on_change` runs last for every action, after `save_version` and after `notify_update` | apps/frappe/frappe/model/document.py:1407 to 1417 | Verified |
| `_action` is derived from the previous docstatus in the database, not from the method called | apps/frappe/frappe/model/document.py:1065 to 1100 | Verified |
| `check_if_latest` raises `TimestampMismatchError` when the stored `modified` differs from the one loaded. This is the built in optimistic concurrency check | apps/frappe/frappe/model/document.py:1055 to 1060 | Verified |
| `load_doc_before_save` reads the previous row with `for_update=True`, so a row lock on the source is taken at the start of every save | apps/frappe/frappe/model/document.py:1378 | Verified |
| `submit()` and `cancel()` are whitelisted on Document, so a generic REST call can reach them | apps/frappe/frappe/model/document.py:1289, 1294 | Verified |

### 1.3 Hook dispatch through doc_events

| Fact | Evidence | Status |
| --- | --- | --- |
| `run_method` wraps the controller method in `Document.hook` and then runs Notifications, Webhooks and Server Scripts | apps/frappe/frappe/model/document.py:1191 to 1209 | Verified |
| A hooked `doc_events` handler runs AFTER the controller method of the same name. `compose` calls `fn` first, then iterates the hook list | apps/frappe/frappe/model/document.py:1578 to 1586 | Verified |
| Hook order within a method is the order of the app list, doctype specific handlers first, then the `"*"` wildcard handlers | apps/frappe/frappe/model/document.py:1598 to 1601 | Verified |
| The `"*"` wildcard key in `doc_events` is supported and applies to every doctype | apps/frappe/frappe/model/document.py:1598 | Verified |
| A tuple of doctype names is accepted as a `doc_events` key and is expanded | apps/frappe/frappe/__init__.py:933 to 938 | Verified |
| A handler may be declared as `handler(doc)` or `handler(doc, method)`. The framework inspects the signature | apps/frappe/frappe/model/document.py:1583 to 1586 | Verified |
| While a `doc_events` handler runs, `frappe.db._disable_transaction_control` is raised, so `frappe.db.commit()` and full `frappe.db.rollback()` inside the handler become no ops that only emit a warning | apps/frappe/frappe/model/document.py:1581, 1588 with apps/frappe/frappe/database/database.py:1178 to 1180 and :1201 to 1216 | Verified |
| Savepoints still work inside a hook. `rollback(save_point=...)` bypasses the disable check | apps/frappe/frappe/database/database.py:1197 to 1200 | Verified |
| Hook return values are merged into `_return_value`, dict returns are merged key by key, a non dict return replaces the accumulated value | apps/frappe/frappe/model/document.py:1563 to 1574 | Verified |

---

## 2. Background jobs

### 2.1 enqueue

`frappe.enqueue` signature at apps/frappe/frappe/utils/background_jobs.py:76 to 93. Status: Verified.

Parameters: `method`, `queue="default"`, `timeout=None`, `event=None`, `is_async=True`, `job_name=None`, `now=False`, `enqueue_after_commit=False`, and keyword only `on_success`, `on_failure`, `at_front`, `job_id`, `deduplicate`, `at_front_when_starved`, plus `**kwargs` passed to the target method.

| Fact | Evidence | Status |
| --- | --- | --- |
| `deduplicate=True` requires `job_id` and skips the enqueue when a job with that id is QUEUED or STARTED. A finished job with the same id is deleted first | apps/frappe/frappe/utils/background_jobs.py:118 to 130 | Verified |
| `job_id` is namespaced per site by `create_job_id` | apps/frappe/frappe/utils/background_jobs.py:133, 655 | Verified |
| Default timeout when none is given is the queue default, falling back to 300 seconds | apps/frappe/frappe/utils/background_jobs.py:168 to 169 | Verified |
| `now=True` calls `frappe.call` in the current process and returns the result, not a Job | apps/frappe/frappe/utils/background_jobs.py:153 to 155 | Verified |
| Enqueue raises if Redis is unreachable, except during a migrate where it falls back to a direct call | apps/frappe/frappe/utils/background_jobs.py:157 to 165 | Verified |
| A queue over the size cap throws before the job is created | apps/frappe/frappe/utils/background_jobs.py:166, 723 to 730 | Verified |

### 2.2 enqueue_after_commit

| Fact | Evidence | Status |
| --- | --- | --- |
| The deferred call is registered as a closure on `frappe.db.after_commit`, a `CallbackManager` | apps/frappe/frappe/utils/background_jobs.py:205 to 207 | Verified |
| `enqueue(..., enqueue_after_commit=True)` returns `None`, never a Job handle | apps/frappe/frappe/utils/background_jobs.py:207 | Verified |
| The callback list is executed by `Database.commit()` AFTER the SQL `COMMIT` has already been issued and a new transaction begun | apps/frappe/frappe/database/database.py:1190, 1191, 1194 | Verified |
| `CallbackManager.run` pops each callback and calls it. An exception from one callback aborts the remaining callbacks and propagates to the caller of `commit()` | apps/frappe/frappe/utils/__init__.py:1160 to 1164 | Verified |
| `after_commit` and `before_commit` are reset when a rollback happens, so a rolled back transaction never enqueues | apps/frappe/frappe/database/database.py:1202 to 1203 | Verified |
| `before_rollback` and `after_rollback` are reset at the start of a commit | apps/frappe/frappe/database/database.py:1182 to 1183 | Verified |
| **If the enqueue fails after commit**, the database work is already durable, the job never reaches Redis, and the exception escapes. In a web request `sync_database()` is called from the `else` branch outside the try and except block, so the failure is not converted into a normal error response | apps/frappe/frappe/app.py:144 to 150, :430 | Verified |
| A commit inside a `doc_events` hook is suppressed, so `after_commit` callbacks registered inside a hook do not run there. They run at the request boundary commit | apps/frappe/frappe/model/document.py:1581 with apps/frappe/frappe/database/database.py:1178 to 1180 | Verified |
| `frappe.db.after_commit`, `before_commit`, `after_rollback`, `before_rollback` are `CallbackManager` instances on the Database object, added with `.add(fn)` or by calling the manager | apps/frappe/frappe/database/database.py:129 to 132 with apps/frappe/frappe/utils/__init__.py:1153 to 1158 | Verified |
| `sql_ddl` force commits and temporarily clears the transaction control guard. Any DDL in application code silently ends the current transaction | apps/frappe/frappe/database/database.py:451 to 458 | Verified |

### 2.3 Serialisation and size

| Fact | Evidence | Status |
| --- | --- | --- |
| Job arguments are wrapped into a dict holding `site`, `user`, `method`, `event`, `job_name`, `is_async` and `kwargs`, then handed to `q.enqueue_call` | apps/frappe/frappe/utils/background_jobs.py:177 to 199 | Verified |
| No serializer is passed to the RQ `Queue`, so RQ's `DefaultSerializer` applies, which is `pickle.dumps` at the highest protocol | apps/frappe/frappe/utils/background_jobs.py:547 with rq 2.6.1 serializers.py:16 to 18 and :43 to 44 | Verified |
| Every argument must therefore be picklable and is stored in full inside the Redis job hash. There is no framework side size cap on job arguments | apps/frappe/frappe/utils/background_jobs.py:192 to 203 | Verified |
| Pass identifiers, not documents. Passing a Document or a large payload puts the whole object in Redis and reads a stale copy in the worker | derived from the two rows above | Proposed |
| The worker commits on success and rolls back then commits on failure, all with `chain=True` | apps/frappe/frappe/utils/background_jobs.py:296 to 306 | Verified |
| A deadlock, a lock wait timeout, or an explicit `frappe.RetryBackgroundJobError` makes the framework re run the job up to 5 times with a growing sleep, inside the same worker process | apps/frappe/frappe/utils/background_jobs.py:274 to 291 | Verified |
| `before_job` and `after_job` hooks run around every job, and `frappe.local.job.after_job` is a per job `CallbackManager` | apps/frappe/frappe/utils/background_jobs.py:261 to 271, :308 to 315 | Verified |
| HTTP method validation on whitelisted functions is skipped inside a background job | apps/frappe/frappe/handler.py:102 to 104 | Verified |

---

## 3. Password fieldtype storage

### 3.1 Table and key

| Fact | Evidence | Status |
| --- | --- | --- |
| Encrypted values live in the site table `__Auth`, which is outside the doctype tables | apps/frappe/frappe/utils/password.py:13, :24 to 33 | Verified |
| Schema is `doctype VARCHAR(140)`, `name VARCHAR(255)`, `fieldname VARCHAR(140)`, `password TEXT`, `encrypted TINYINT`, with `PRIMARY KEY (doctype, name, fieldname)` | apps/frappe/frappe/database/mariadb/database.py:294 to 304 | Verified |
| The key is the triple `(doctype, name, fieldname)` and the `encrypted` flag must be 1 for the read path | apps/frappe/frappe/utils/password.py:27 to 31 | Verified |
| Write is an upsert. On MariaDB it is INSERT with ON DUPLICATE KEY UPDATE | apps/frappe/frappe/utils/password.py:51 to 68 | Verified |
| **Credential rotation works.** The update clause is `Values(Auth.password)`, which renders as SQL `VALUES(password)`, meaning the value that would have been inserted. Re-saving a changed secret overwrites the stored one rather than keeping the old row | apps/frappe/frappe/utils/password.py:57 to 59 with pypika 0.48.9 terms.py:565 to 571 | Verified |
| A write longer than the column allows is converted into a readable throw about password length | apps/frappe/frappe/utils/password.py:70 to 76 | Verified |
| The doctype column in the doctype table itself is typed `text`, and after save it holds only asterisks | apps/frappe/frappe/database/mariadb/database.py:191 with apps/frappe/frappe/model/base_document.py:1360 to 1361 | Verified |

### 3.2 Child table rows: this works

| Fact | Evidence | Status |
| --- | --- | --- |
| **A Password field on a child row IS persisted.** `_validate` iterates `get_all_children()` and calls `d._save_passwords()` on each child row | apps/frappe/frappe/model/document.py:817, :830 | Verified |
| The key used is the CHILD doctype and the CHILD ROW NAME, because `_save_passwords` uses `self.doctype` and `self.name` on the child row object | apps/frappe/frappe/model/base_document.py:1358, :1361 | Verified |
| Child rows are full controller class instances, subclasses of `Document`, so `get_password` is available on a child row | apps/frappe/frappe/model/base_document.py:449 to 453 with apps/frappe/frappe/model/document.py:194 | Verified |
| `get_password(fieldname)` on a child row reads `__Auth` with the child doctype and child row name | apps/frappe/frappe/model/base_document.py:1363 to 1369 | Verified |
| Child row names are stable. `set_name_in_children` only names rows that have no name yet, so a re-save does not re-key the stored password | apps/frappe/frappe/model/document.py:1111 to 1114 | Verified |
| Child row names default to a hash when the child doctype has no autoname rule | apps/frappe/frappe/model/naming.py:194 to 196 | Verified |
| Password values are masked in place after save, the field is replaced with `"*" * len(value)`, so the stored column and the REST payload leak only the length | apps/frappe/frappe/model/base_document.py:1360 to 1361 | Verified |
| An empty value removes the `__Auth` row for that field | apps/frappe/frappe/model/base_document.py:1353 to 1354 | Verified |
| `flags.ignore_save_passwords` set to True skips all Password fields, or set to a list of fieldnames skips those fields | apps/frappe/frappe/model/base_document.py:1345 to 1351 | Verified |

### 3.3 Child table rows: the three gaps

| Gap | Evidence | Status |
| --- | --- | --- |
| **Removing a child row leaks its secret.** `update_child_table` deletes orphan rows with a direct query builder DELETE. It never calls `delete_all_passwords_for`, so the `__Auth` row survives the removal | apps/frappe/frappe/model/document.py:645 to 662 | Verified |
| **Deleting the parent leaks child secrets.** `delete_doc` calls `delete_all_passwords_for(doctype, name)` for the PARENT only, then deletes child rows with a plain DELETE by `parent` | apps/frappe/frappe/model/delete_doc.py:201 to 202 with :266 to 267 | Verified |
| **Renaming the parent does not touch child secrets, and does not need to.** `rename_password` remaps only rows keyed by the parent doctype and old parent name. Child row names do not change on a parent rename, so the child secret is still reachable | apps/frappe/frappe/model/rename_doc.py:200 to 201 with apps/frappe/frappe/utils/password.py:171 to 176 | Verified |
| The app must delete child credential rows explicitly, on child row removal and on parent delete, via `remove_encrypted_password(child_doctype, row_name, fieldname)` | apps/frappe/frappe/utils/password.py:79 to 80 | Proposed |
| **Fixture export breaks child secrets.** `export_json` strips `name` from every child row, so a re-imported child row gets a new name and the old `__Auth` key becomes unreachable. Never fixture export a doctype holding child Password fields | apps/frappe/frappe/core/doctype/data_import/data_import.py:350 to 362 | Verified |

### 3.4 Encryption and key source

| Fact | Evidence | Status |
| --- | --- | --- |
| Encryption is Fernet from the `cryptography` package, applied to the UTF-8 encoded value | apps/frappe/frappe/utils/password.py:4, :189 to 198 | Verified |
| The key is read from the site config under the key name `encryption_key`. If absent, a new Fernet key is generated and written into the site config on first use | apps/frappe/frappe/utils/password.py:223 to 231 | Verified |
| There is one site wide key. Nothing is scoped per company, per doctype or per field | apps/frappe/frappe/utils/password.py:190, :203 | Verified |
| An invalid or rotated key produces a thrown `ValidationError`, not silent corruption | apps/frappe/frappe/utils/password.py:201 to 220 | Verified |
| `get_decrypted_password(..., raise_exception=False)` returns None rather than throwing on a decrypt failure, but still throws when no row is found | apps/frappe/frappe/utils/password.py:35 to 47 | Verified |
| Restoring a site database without carrying the matching `encryption_key` makes every stored credential unreadable | apps/frappe/frappe/utils/password.py:211 to 216 | Verified |

---

## 4. Private File access

| Fact | Evidence | Status |
| --- | --- | --- |
| `/private/files/...` is routed to `download_private_file` in the main request dispatcher | apps/frappe/frappe/app.py:126 to 127 | Verified |
| Guest is rejected outright, then `find_file_by_url` resolves the URL to a File record | apps/frappe/frappe/utils/response.py:297 to 303 | Verified |
| `find_file_by_url` looks up every File row with that URL and returns the first one for which `is_downloadable()` is true. A file attached to several documents is served if ANY one of them grants read | apps/frappe/frappe/core/doctype/file/utils.py:457 to 466 | Verified |
| `is_downloadable` is exactly `has_permission(self, "read")` | apps/frappe/frappe/core/doctype/file/file.py:855 to 856 | Verified |
| Every served private file writes an Access Log entry | apps/frappe/frappe/utils/response.py:305 | Verified |
| For a private File with `attached_to_doctype` and `attached_to_name` set, permission delegates to the referenced document. `write`, `create` and `delete` require write on the referenced document, everything else requires read | apps/frappe/frappe/core/doctype/file/file.py:964 to 979 | Verified |
| A missing or non importable referenced doctype returns False, it does not fall open | apps/frappe/frappe/core/doctype/file/file.py:968 to 974 | Verified |
| **The file owner always passes, for every permission type including delete.** `if user != "Guest" and doc.owner == user: return True` sits ahead of the attachment check | apps/frappe/frappe/core/doctype/file/file.py:953 to 954 | Verified |
| Document sharing on the File record itself grants read, write, share and submit independently of the attached document | apps/frappe/frappe/core/doctype/file/file.py:955 to 962 | Verified |
| A non private File is readable by everyone once `ptype` is read or select, with no reference to the attached document | apps/frappe/frappe/core/doctype/file/file.py:950 to 951 | Verified |
| **There is no dedicated whitelisted method that flips private to public.** `is_private` is an ordinary Check field, so any generic write path that passes File write permission can flip it, and `handle_is_private_changed` then physically moves the bytes from the private directory to the public one | apps/frappe/frappe/core/doctype/file/file.py:175 to 177, :312 to 331 | Verified |
| The only whitelisted method on the File controller is `optimize_file` | apps/frappe/frappe/core/doctype/file/file.py:887 to 888 | Verified |
| Making a file public can be restricted site wide by the System Settings flag `only_allow_system_managers_to_upload_public_files` | apps/frappe/frappe/core/doctype/file/file.py:197 to 200 | Verified |
| The list view query condition lets a System user read any File whose `attached_to_doctype` is a doctype they have read on, without a per document check | apps/frappe/frappe/core/doctype/file/file.py:984 to 998 | Verified |
| `upload_file` is whitelisted with `allow_guest=True`, POST only, and requires write on the target document unless guest uploads are enabled in System Settings | apps/frappe/frappe/handler.py:127 to 145, :219 to 232 | Verified |
| Evidence files must not be created with the acting user as owner if that user must not be able to delete them. Create them under a service identity or block delete in a File `on_trash` hook | derived from the owner bypass above | Proposed |

---

## 5. Version tracking

| Fact | Evidence | Status |
| --- | --- | --- |
| `save_version` is called from `run_post_save_methods` for every action, after the state hooks and before `on_change` | apps/frappe/frappe/model/document.py:1415 | Verified |
| A version is skipped when the meta flag `track_changes` is off, when the doctype is Version, when `flags.ignore_version` is set, during install, or during a patch on a new document | apps/frappe/frappe/model/document.py:1535 to 1542 | Verified |
| `flags.ignore_version` defaults to `frappe.in_test` on save, so versions ARE written in normal operation | apps/frappe/frappe/model/document.py:556 | Verified |
| No version is written on a plain insert unless `flags.updater_reference` is set or the document is an amendment | apps/frappe/frappe/model/document.py:1544 to 1551 with apps/frappe/frappe/core/doctype/version/version.py:58 to 72 | Verified |
| The Version record is inserted with `ignore_permissions=True` | apps/frappe/frappe/model/document.py:1554 | Verified |
| A Version stores only three data fields: `ref_doctype` Link, `docname` Data, `data` Code. There is no user, company or timestamp field beyond the standard `owner`, `creation`, `modified` columns | apps/frappe/frappe/core/doctype/version/version.json:18 to 48 | Verified |
| `data` is a compact JSON object with keys `changed`, `added`, `removed`, `row_changed`, `data_import`, `updater_reference` | apps/frappe/frappe/core/doctype/version/version.py:50 to 53, :125 to 133 | Verified |
| `changed` entries are `[fieldname, old, new]` using FORMATTED values, not raw values, for non blacklisted fieldtypes | apps/frappe/frappe/core/doctype/version/version.py:180 to 185 | Verified |
| `added` and `removed` entries carry the whole child row dict | apps/frappe/frappe/core/doctype/version/version.py:169, :177 | Verified |
| `row_changed` entries are `(table_fieldname, row_index, row_name, changed_list)` | apps/frappe/frappe/core/doctype/version/version.py:167 | Verified |
| Text Editor, Markdown Editor, Code and HTML Editor field values skip the formatting pass but are still diffed and stored | apps/frappe/frappe/core/doctype/version/version.py:120, :181 | Verified |
| Fieldtypes with no value are excluded, table fieldtypes are NOT excluded | apps/frappe/frappe/core/doctype/version/version.py:13, :139 to 140 | Verified |
| **Password fields are not excluded from the diff.** Because the stored value is asterisks, a version records a change in mask length, not the secret. A length change is still an information leak in the audit trail | apps/frappe/frappe/core/doctype/version/version.py:13 with apps/frappe/frappe/model/base_document.py:1361 | Verified |
| A session impersonation marker is added to the diff when present | apps/frappe/frappe/core/doctype/version/version.py:38 to 45 | Verified |
| Version is readable only by System Manager and Administrator by default | apps/frappe/frappe/core/doctype/version/version.json:67, :72 | Verified |
| Version is not a substitute for the app evidence trail. It has no company field, no row level filtering and no protection against the parent document being renamed | derived from the rows above | Proposed |

---

## 6. Uniqueness, indexes and locking

### 6.1 Uniqueness and indexes

| Fact | Evidence | Status |
| --- | --- | --- |
| `unique` is a DocField Check property. It is the only declarative uniqueness in a DocType | apps/frappe/frappe/core/doctype/docfield/docfield.json:300 for unique and :158 for search_index | Verified |
| A unique field is emitted as a column level UNIQUE on create and as `ADD UNIQUE INDEX IF NOT EXISTS` on alter | apps/frappe/frappe/database/schema.py:249 to 250, :258 with apps/frappe/frappe/database/mariadb/schema.py:84 | Verified |
| `unique` is ignored for `text` and `longtext` columns, which means a Password, Long Text, Text or Code field can never be declared unique | apps/frappe/frappe/database/schema.py:249, :289 to 292 | Verified |
| Adding `unique` to a column with existing duplicates throws a clear error during migrate | apps/frappe/frappe/database/mariadb/schema.py:168 to 173 | Verified |
| **A DocType JSON cannot declare a multi column unique constraint or a composite index.** There is no such property on DocType or DocField | apps/frappe/frappe/core/doctype/doctype/doctype.json and apps/frappe/frappe/core/doctype/docfield/docfield.json, searched both field lists, only the per field docfield.json:300 unique and :158 search_index exist | Verified |
| `frappe.db.add_unique(doctype, fields, constraint_name=None)` creates a composite UNIQUE. The default constraint name is `unique_<f1>_<f2>`. It commits first, then runs the ALTER | apps/frappe/frappe/database/mariadb/database.py:438 to 453 | Verified |
| `frappe.db.add_index(doctype, fields, index_name=None)` creates a composite index. The default name is `<f1>_<f2>_index` from `get_index_name` | apps/frappe/frappe/database/mariadb/database.py:413 to 425 with apps/frappe/frappe/database/database.py:1371 to 1375 | Verified |
| A single field `add_index` also writes a `search_index` Property Setter so a later migrate does not drop it. A MULTI field `add_index` writes no Property Setter, so nothing records its intent | apps/frappe/frappe/database/mariadb/database.py:426 to 436 | Verified |
| Both `add_index` and `add_unique` call `self.commit()` before the DDL, so they end the caller's transaction. Never call them inside a document hook | apps/frappe/frappe/database/mariadb/database.py:421, :449 | Verified |
| Composite indexes and composite unique constraints belong in a patch or an `after_migrate` hook, made idempotent by the built in existence checks | derived from the rows above | Proposed |

### 6.2 Row locking

| Fact | Evidence | Status |
| --- | --- | --- |
| `frappe.db.get_value(doctype, filters, fieldname, for_update=True)` issues `SELECT ... FOR UPDATE`. It also accepts keyword only `skip_locked` and `wait` | apps/frappe/frappe/database/database.py:527, :531 to 532, :563 to 579 | Verified |
| `wait=False` maps to SQL `NOWAIT`, `skip_locked=True` maps to SQL `SKIP LOCKED`. Both are supported on MariaDB. When both are set, NOWAIT wins | apps/frappe/frappe/database/query.py:313 to 314 with pypika 0.48.9 dialects.py:117 to 122 and :150 to 158 | Verified |
| **Trap. When `filters` is a LIST, `frappe.db.get_values` hardcodes `wait=True`, so `wait=False` is silently ignored on that branch.** A dict filter or a plain name reaches the correct branch | apps/frappe/frappe/database/database.py:648 to 659 versus :665 to 676 | Verified |
| `frappe.qb.get_query(..., for_update=True, skip_locked=..., wait=...)` is the direct query builder route and has the same mapping | apps/frappe/frappe/database/query.py:224, :230 to 231, :313 to 314 | Verified |
| Raw SQL through `frappe.db.sql("... for update")` works. Nothing in the framework rewrites the statement | apps/frappe/frappe/database/database.py:1176 to 1194 shows only transaction management, no statement rewriting | Verified |
| `frappe.db.get_single_value(doctype, fieldname, for_update=True)` locks the `tabSingles` row and bypasses the value cache | apps/frappe/frappe/database/database.py:885, :900, :904 to 908 | Verified |
| `frappe.get_doc(doctype, name, for_update=True)` is available and is what `load_doc_before_save` uses internally | apps/frappe/frappe/model/document.py:1378 with the `get_doc` overload at apps/frappe/frappe/model/document.py:80 to 82 | Verified |
| Use a dict filter, not a list filter, wherever NOWAIT semantics matter for a lease claim | derived from the trap above | Proposed |

---

## 7. Extension points

| Fact | Evidence | Status |
| --- | --- | --- |
| **An app may define any hook name it likes.** `_load_app_hooks` uses `inspect.getmembers` over the app's `hooks.py` and accepts every public member that is not a module, a function or a class | apps/frappe/frappe/__init__.py:960 to 966 | Verified |
| `frappe.get_hooks("my_custom_hook")` therefore works for an app defined name, returning a list or a dict merged across apps | apps/frappe/frappe/__init__.py:993 to 996 | Verified |
| `append_hook` merges a dict hook key by key into lists, and lifts a scalar into a single element list | apps/frappe/frappe/__init__.py:999 to 1015 | Verified |
| **A hook value must not be a callable or a class.** The predicate excludes both. A provider adapter registry must map strings to dotted import paths, resolved later with `frappe.get_attr` | apps/frappe/frappe/__init__.py:960 to 961 with apps/frappe/frappe/__init__.py:1113 | Verified |
| Hooks are cached. In developer mode they are site cached, otherwise they are cached in the client cache under the key `app_hooks` | apps/frappe/frappe/__init__.py:985 to 991 | Verified |
| `frappe.get_hooks(hook, app_name="x")` reads one app's hooks only, bypassing the merge | apps/frappe/frappe/__init__.py:985 to 986 | Verified |
| `doc_events` supports doctype keys, tuple keys and the `"*"` wildcard, per topic 1 above | apps/frappe/frappe/__init__.py:933 to 938 with apps/frappe/frappe/model/document.py:1598 | Verified |
| `override_whitelisted_methods` is a dict of original dotted path to replacement dotted path. The LAST registered override wins | apps/frappe/frappe/__init__.py:1561 to 1564 | Verified |
| `override_doctype_class` is a dict of doctype name to a dotted class path. The LAST override wins and the framework enforces that it be a subclass of the original controller, throwing otherwise | apps/frappe/frappe/model/base_document.py:111, :116 to 126 | Verified |
| `load_doctype_module` deliberately returns the STANDARD module, ignoring `override_doctype_class` | apps/frappe/frappe/modules/utils.py:291 to 296 | Verified |
| `scheduler_events` supports `all`, `hourly`, `hourly_long`, `hourly_maintenance`, `daily`, `daily_long`, `daily_maintenance`, `weekly`, `weekly_long`, `monthly`, `monthly_long`, `cron`, `yearly`, `annual` | apps/frappe/frappe/core/doctype/scheduled_job_type/scheduled_job_type.json frequency options, confirmed by reading the file | Verified |
| A frequency key maps to a list of dotted methods. The `cron` key maps to a dict of cron expression to list of methods | apps/frappe/frappe/core/doctype/scheduled_job_type/scheduled_job_type.py:228 to 255 | Verified |
| Each entry becomes one Scheduled Job Type record, created or updated during sync. Frequency and cron format are updated on an existing record, other fields such as the stopped flag are preserved | apps/frappe/frappe/core/doctype/scheduled_job_type/scheduled_job_type.py:257 to 293 | Verified |
| An entry whose dotted path does not resolve is skipped with a warning, not an error | apps/frappe/frappe/core/doctype/scheduled_job_type/scheduled_job_type.py:259 to 263 | Verified |
| `fixtures` is a list. Each entry is a doctype name, or a dict with `doctype` or `dt`, plus optional `filters`, `or_filters` and `prefix` | apps/frappe/frappe/utils/fixtures.py:71 to 85 | Verified |
| `export_fixtures` writes one JSON file per entry into `<app>/fixtures/<scrubbed name>.json`, ordered by `idx asc, creation asc` | apps/frappe/frappe/utils/fixtures.py:84 to 102 | Verified |
| `fixture_auto_order` prefixes each filename with a zero padded index so files import in declaration order | apps/frappe/frappe/utils/fixtures.py:69, :88 to 93 | Verified |
| `export_json` drops `modified_by`, `creation`, `owner`, `idx`, `lft`, `rgt` from the parent, and additionally drops `docstatus`, `doctype`, `modified`, `name`, `parent`, `parentfield`, `parenttype` from every child row | apps/frappe/frappe/core/doctype/data_import/data_import.py:343 to 362 | Verified |
| `import_fixtures` reads `<app>/fixtures/*.json` in sorted filename order and overwrites the existing records | apps/frappe/frappe/utils/fixtures.py:28 to 43 | Verified |
| Print Format and Letter Head must not be fixtures. A sync overwrites live edits. This is a standing house rule and is consistent with the overwrite behaviour above | apps/frappe/frappe/utils/fixtures.py:40 | Proposed |

---

## 8. Naming

| Fact | Evidence | Status |
| --- | --- | --- |
| A DocType's table name is literally `tab` concatenated with the doctype name, spaces included. `UAE Peppol Connection` becomes `` `tabUAE Peppol Connection` `` | apps/frappe/frappe/utils/__init__.py:1047 to 1053 | Verified |
| A name already starting with a double underscore is used as is, which is how `__Auth` and `__global_search` are addressed | apps/frappe/frappe/utils/__init__.py:1048 | Verified |
| `frappe.scrub` lowercases and replaces both spaces and hyphens with underscores | apps/frappe/frappe/__init__.py:824 to 826 | Verified |
| **Module `UAE e-Invoicing` scrubs to the folder string `uae_e_invoicing`.** The hyphen becomes an underscore, so there is one underscore between `e` and `invoicing` | apps/frappe/frappe/__init__.py:824 to 826, evaluated against that exact string | Verified |
| The module folder sits directly under the app package: `<app>/<scrubbed module>/` | apps/frappe/frappe/__init__.py:838 to 842 | Verified |
| A controller module path is `<scrubbed app>.<scrubbed module>.doctype.<scrubbed doctype>.<scrubbed doctype>` | apps/frappe/frappe/modules/utils.py:313 to 317 | Verified |
| The controller CLASS name is the doctype name with spaces and hyphens removed, not scrubbed. `UAE Peppol Connection` gives class `UAEPeppolConnection` | apps/frappe/frappe/model/base_document.py:113 | Verified |
| The module to app mapping comes from the Module Def record, and an unknown module throws `DoesNotExistError` | apps/frappe/frappe/modules/utils.py:320 to 324 | Verified |
| A Single DocType stores one row per field in `tabSingles`, with columns `doctype`, `field`, `value` | apps/frappe/frappe/model/document.py:759 to 772 | Verified |
| `tabSingles` has only a non unique index on `(doctype, field)`. There is no primary key and no unique constraint | apps/frappe/frappe/database/mariadb/framework_mariadb.sql:266 to 271 | Verified |
| **Saving a Single DELETES every row for that doctype and re-inserts them.** Two concurrent saves can interleave into a mixed or duplicated state | apps/frappe/frappe/model/document.py:764 to 772 | Verified |
| A Single's `name` equals its doctype, so a Password field on a Single is keyed `(doctype, doctype, fieldname)` in `__Auth` | apps/frappe/frappe/model/base_document.py:1358 with the Single handling at apps/frappe/frappe/model/document.py:474 | Verified |
| Do not put per company policy or a submission counter in a Single. Use a normal DocType with a real unique key | derived from the two rows above | Proposed |

---

## 9. Time

| Fact | Evidence | Status |
| --- | --- | --- |
| `frappe.utils.now_datetime()` returns the current time in the SYSTEM timezone, with `tzinfo` stripped. It is naive | apps/frappe/frappe/utils/data.py:371 to 373 | Verified |
| `frappe.utils.now()` is `now_datetime()` formatted as `yyyy-mm-dd hh:mm:ss`. It honours the test override `frappe.flags.current_date` | apps/frappe/frappe/utils/data.py:415 to 424 | Verified |
| `datetime.utcnow()` is unrelated to either. It is UTC, so it differs from `now_datetime()` by the system offset, which is 4 hours for Asia/Dubai | apps/frappe/frappe/utils/data.py:371 to 373 | Verified |
| The system timezone is System Settings `time_zone`, falling back to `Asia/Kolkata` when unset | apps/frappe/frappe/utils/data.py:388 to 390 | Verified |
| `convert_utc_to_system_timezone(utc_dt)` converts a UTC datetime into the system timezone | apps/frappe/frappe/utils/data.py:409 to 412 | Verified |
| `convert_utc_to_timezone(utc_dt, tz)` treats a naive input as UTC and returns an AWARE datetime. An unknown timezone name silently returns the input unchanged | apps/frappe/frappe/utils/data.py:393 to 400 | Verified |
| `get_datetime_in_timezone(tz)` returns the current AWARE time in the named timezone | apps/frappe/frappe/utils/data.py:403 to 406 | Verified |
| **Trap. `now_datetime()` is naive and `convert_utc_to_timezone()` is aware. Subtracting or comparing them raises TypeError.** Strip `tzinfo` before mixing | apps/frappe/frappe/utils/data.py:373 versus :398 | Verified |
| **There is no system timezone to UTC helper in `frappe/utils/data.py`.** The conversion is one way only. An app that needs UTC must attach `ZoneInfo(get_system_timezone())` to the naive value itself and call `astimezone` | apps/frappe/frappe/utils/data.py:388 to 412, searched for the reverse direction and none exists | Verified |
| Every Datetime column written by the framework holds system local naive time. Provider timestamps arriving in UTC or with an offset must be converted before they are stored or compared | apps/frappe/frappe/model/document.py:777 to 779 with apps/frappe/frappe/utils/data.py:415 | Verified |
| Store an explicit UTC copy alongside any local Datetime used for a reporting deadline, and record the offset used | derived from the rows above | Proposed |

---

## 10. Whitelisting and CSRF

| Fact | Evidence | Status |
| --- | --- | --- |
| `frappe.whitelist(methods=[...])` records the allowed HTTP methods in a module level dict at decoration time. The default is `["GET", "POST", "PUT", "DELETE"]` | apps/frappe/frappe/__init__.py:424, :439 to 451 | Verified |
| The methods list is ENFORCED in `is_valid_http_method`, which is a separate check from `is_whitelisted` | apps/frappe/frappe/handler.py:99 to 110 | Verified |
| **The HTTP method check is skipped inside a background job and inside safe exec.** Only the web path enforces it | apps/frappe/frappe/handler.py:100 to 104 | Verified |
| `is_whitelisted` checks membership of the whitelist set and, for Guest, membership of the guest set. It does NOT check HTTP method or permissions | apps/frappe/frappe/__init__.py:464 to 480 | Verified |
| For a Guest calling a method not marked `xss_safe`, every string in `form_dict` is HTML sanitised in place | apps/frappe/frappe/__init__.py:474 to 480 | Verified |
| Argument types are validated for whitelisted functions when a request is present or in test | apps/frappe/frappe/__init__.py:443 | Verified |
| CSRF is checked in `HTTPRequest.__init__` through `validate_csrf_token` | apps/frappe/frappe/auth.py:47 to 48, :81 | Verified |
| The check applies only to unsafe HTTP methods, and is skipped when `frappe.conf.ignore_csrf` is set, when there is no session, when the session has NO stored csrf token, when the supplied header or form field matches, or when the referrer is allowed | apps/frappe/frappe/auth.py:81 to 96 | Verified |
| The token is read from header `X-Frappe-CSRF-Token` or from a `csrf_token` form field | apps/frappe/frappe/auth.py:89 | Verified |
| **A session csrf token is only generated when a desk or billing page is rendered.** No other path calls `get_csrf_token` | apps/frappe/frappe/sessions.py:194 to 204, called only from apps/frappe/frappe/www/desk.py:35 and apps/frappe/frappe/www/billing.py:19 | Verified |
| **CSRF is therefore effectively skipped for API key and token authentication.** `validate_auth` runs at apps/frappe/frappe/app.py:104, AFTER `init_request` has already constructed `HTTPRequest` at apps/frappe/frappe/app.py:206. At CSRF time the session carries no stored token, so the check returns early | apps/frappe/frappe/app.py:104, :206 with apps/frappe/frappe/auth.py:87 | Verified |
| API key and secret are compared with a plain `==`, not a constant time comparison | apps/frappe/frappe/auth.py:730 | Verified |
| The API secret itself is a Password field read through `get_decrypted_password` | apps/frappe/frappe/auth.py:729 | Verified |
| `auth_hooks` lets an app add its own authentication scheme, run after OAuth and API keys | apps/frappe/frappe/auth.py:742 to 744 | Verified |
| `frappe.only_for(roles, message=False)` raises `PermissionError` unless the user holds one of the roles. Administrator always passes | apps/frappe/frappe/__init__.py:532 to 556 | Verified |
| `frappe.has_permission(doctype, ptype, doc=..., user=..., throw=..., parent_doctype=...)` returns a bool, or raises `PermissionError` when `throw` is set. `parent_doctype` is REQUIRED for a child doctype unless `doc` is passed | apps/frappe/frappe/__init__.py:584 to 630 | Verified |
| `ignore_permissions` on `get_doc` is expressed as the keyword `check_permission`, which opts IN to a check. `get_doc` does not check permissions by default | apps/frappe/frappe/model/document.py:80 to 82 | Verified |
| `insert(ignore_permissions=True)` and `save(ignore_permissions=True)` set `self.flags.ignore_permissions`, which makes `Document.has_permission` return True unconditionally for the rest of that document's life in memory | apps/frappe/frappe/model/document.py:443 to 444, :553 to 554, :394 to 395 | Verified |
| `ignore_permissions` suppresses permission checks ONLY. Validation, child validation, hooks, versioning and `_save_passwords` all still run | apps/frappe/frappe/model/document.py:457, :466 to 467, :493 | Verified |
| `flags.ignore_permissions` also suppresses `validate_higher_perm_levels` | apps/frappe/frappe/model/document.py:967 | Verified |
| Scope any elevation to a single `frappe.new_doc(...).insert(ignore_permissions=True)` call on an app owned doctype, never to a fetched source document that later re-enters the service surface | derived from the flag persistence row above | Proposed |

---

## 11. Locks and rate limiting

| Fact | Evidence | Status |
| --- | --- | --- |
| `frappe.utils.synchronization.filelock(name, timeout=30, is_global=False)` is a context manager over the `filelock` package. This is the STRONG lock | apps/frappe/frappe/utils/synchronization.py:17 to 41 | Verified |
| A site lock file lands at `sites/<site>/locks/<name>.lock`, a global one at `<bench>/config/<name>.lock` | apps/frappe/frappe/utils/synchronization.py:33 to 37 | Verified |
| A timeout logs an error and raises `LockTimeoutError` | apps/frappe/frappe/utils/synchronization.py:42 to 48 | Verified |
| **A file lock is per machine only.** It does not coordinate workers on a second server | apps/frappe/frappe/utils/synchronization.py:18 to 19 | Verified |
| `frappe.utils.file_lock` is a separate, explicitly WEAK lock, documented as prone to race conditions and used only for `queue_action` document locking | apps/frappe/frappe/utils/file_lock.py:4 to 8, :25 to 37 | Verified |
| The weak lock expires by file mtime, with a 600 second default in `check_lock` | apps/frappe/frappe/utils/file_lock.py:50 to 55 | Verified |
| `Document.queue_action` uses the weak lock and `Document.check_if_locked` blocks a save while it is held | apps/frappe/frappe/model/document.py:1814, :1846 to 1860, :509 to 531 | Verified |
| **There is no cache based lock helper in the framework.** `frappe.cache` is a plain subclass of `redis.Redis`, so `SET NX` and redis-py's own `Lock` are reachable directly, but nothing wraps them | apps/frappe/frappe/utils/redis_wrapper.py:38, method list at :52 to 365 shows no lock helper | Verified |
| **There is no database advisory lock helper.** A search for `GET_LOCK`, `RELEASE_LOCK`, `advisory_lock` and `pg_advisory` across the framework returns only file lock code | searched apps/frappe/frappe, only apps/frappe/frappe/utils/file_lock.py matches | Verified |
| The only true database lock available is `SELECT ... FOR UPDATE` on a real row, per topic 6 | apps/frappe/frappe/database/query.py:313 to 314 | Verified |
| `frappe.rate_limiter.rate_limit(key=None, limit=5, seconds=86400, methods="ALL", ip_based=True)` is a decorator that counts requests in Redis, keyed on `rl:<cmd>:<identity>` where identity is IP, a form field, or both | apps/frappe/frappe/rate_limiter.py:104 to 155 | Verified |
| The decorator is a no op when there is no `frappe.request`, so it does not throttle background work | apps/frappe/frappe/rate_limiter.py:136 to 140 | Verified |
| A site wide limiter also exists, driven by `frappe.conf.rate_limit` with `limit` and `window`, measuring request DURATION rather than count, and returning 429 with a `Retry-After` header | apps/frappe/frappe/rate_limiter.py:15 to 19, :69 to 98 | Verified |
| Outbound rate limiting toward a provider is not provided by the framework and must be built in the app | searched frappe/rate_limiter.py, all paths are inbound request scoped | Verified |
| A single active submission rule needs a real row lock plus a lease column, not a file lock and not a Redis key | derived from the rows above | Proposed |

---

## Consequences for the app

- P02. Store provider credentials in child rows as planned. It works, but the app must delete the `__Auth` row itself on child row removal and on parent delete, because the framework does neither.
- P02. Never fixture export any doctype that holds a child Password field. Child row names are stripped on export, which orphans the secret.
- P02. Keep no per company policy or counter in a Single DocType. A Single save deletes and re-inserts all its rows with no unique key, so concurrent saves can interleave.
- P02. Declare composite unique keys and composite indexes in a patch using `frappe.db.add_unique` and `frappe.db.add_index`. A DocType JSON cannot express them, and a multi column index leaves no Property Setter recording its intent.
- P04. Write the working record from `on_update` with a `docstatus` guard and an `doc.flags.in_insert` check, because `on_update` fires on insert and again on submit before `on_submit`.
- P04. Put app logic in controllers, not in `doc_events`, wherever ordering matters. A hooked handler always runs after the controller method of the same name, and cannot commit or roll back while it runs.
- P04. Do not call `frappe.db.add_index`, `add_unique` or any DDL inside a document hook. Each one commits the caller's transaction first.
- P05. Treat `enqueue_after_commit` as best effort delivery only. The SQL COMMIT completes before the callback runs, so a Redis failure loses the job while the data is already durable. The due intent row is the recovery path.
- P05. Pass identifiers to jobs, never documents or payloads. Job arguments are pickled whole into Redis with no size cap.
- P06. Claim leases with `for_update` plus a dict filter. A list filter silently forces `wait=True`, so a NOWAIT claim degrades into a blocking wait. There is no advisory lock and no cache lock helper to fall back on.
- P06. Convert every provider timestamp explicitly. The framework stores naive system local time, offers no system to UTC helper, and raises TypeError when a naive and an aware datetime are mixed.
- P07. Do not rely on File permissions alone to protect evidence. The file owner passes every permission type including delete, and `is_private` is an ordinary writable field with no dedicated flip method to block.
