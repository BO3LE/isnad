"""C7 · db — the one owner of the schema.

Only `api` and `worker` import this package. No agent, adapter or exporter ever
opens a database connection.
"""
