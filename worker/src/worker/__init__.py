"""C3 · worker — the orchestrator.

Depends on contracts, db and the agent *registry*. It never imports an agent by name:
agents are discovered through the `gp.agents` entry point group.
"""
