"""Provider adapters, the registry that holds them, and the way out to a provider.

Nothing here imports frappe. The registry takes adapter objects that are
already imported, and the transport takes a recorder that is injected, so the
whole package runs in a test with no site and no database.

The contract these adapters fill in lives in `domain/connector.py`. This
package consumes it and does not extend it.
"""
