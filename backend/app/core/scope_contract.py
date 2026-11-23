"""Shared scope boundaries: customer outputs, not an implementation checklist."""

DELIVERABLE_BOUNDARIES = '''DELIVERABLE SPLIT RULE (takes precedence over generic phase/release heuristics):
- A separate deliverable must be a distinct usable customer outcome or an independently commissioned package. Explain what the customer receives and why it merits its own acceptance in separation_basis.
- Do not split merely because work has multiple phases, dates, environments, services, technical layers, workstreams or sign-off gates. Discovery, setup, migration, reconciliation, testing and handover for one migration outcome are modules of that deliverable.
- A controlled subset of order data migrated into an isolated cloud is one deliverable, with its necessary migration and validation modules.
- A full knowledge base, a claims-assistance chatbot and an automated ticketing system can be three deliverables when each is requested as a distinct usable output. A knowledge base used only internally by a chatbot is normally a module of that chatbot.
- Preserve genuinely explicit customer-authored Deliverable N packages and explicit user instructions. A Phase N, Wave N or Release N label alone is sequencing, not proof of a separate deliverable.
- Use the smallest natural number of deliverables justified by those outcomes; neither force one nor target a fixed count. Preserve all requirements, phase sequence, gates and qualifications inside the appropriate modules.
'''

CONCISE_SCOPE = '''SCOPE BREVITY:
- Group closely related implementation actions; usually 3-5 substantive bullets per module are enough for a simple workstream. This is guidance, never a limit: retain more when distinct source commitments require it.
- Do not expand an action into separate design, configure, implement, test, document and handover bullets unless each adds a material project-specific commitment.
- Remove generic best-practice filler, repeated validation steps and repeated outputs. State each business rule, interface, exception and acceptance condition once, in its owning module.
- Never omit scope to satisfy a length or bullet target. Preserve the existing deliverable/module heading format.
'''
