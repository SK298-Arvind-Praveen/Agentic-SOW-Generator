"""Select representative overview wires without altering the complete architecture."""
import re


def projection(spec, support):
    nodes={n.id:n for n in spec.nodes}
    # Deployment/configuration and private API plumbing are shown as resources,
    # but are not another runtime flow. Their exact edges remain on the detail page.
    plumbing={n.id for n in spec.nodes if 'interface-endpoint' in n.icon_key or
        re.search(r'interface endpoints?|artifact|package',n.label,re.I)}
    support=support|plumbing
    def family(n):
        if n.placement_role=='compute' and n.availability_zone:
            return (n.icon_key,re.sub(r'\b(?:az|node)\s*[ab12]\b','',n.label.lower()).strip())
        return n.id
    selected={};equivalent={}
    for i,e in enumerate(spec.edges):
        if e.source in support or e.target in support:continue
        a,b=nodes[e.source],nodes[e.target]
        if a.placement_role=='compute' and 'gateway endpoint' in b.label.lower() and any(
                nodes[other.source].placement_role=='integration' and other.target==b.id for other in spec.edges):
            continue  # Show the import path once; runtime object access stays in detail.
        if re.search(r'rollback|apply delta|write ledger',e.label,re.I):
            continue  # Recovery/bookkeeping is documented on Connection detail.
        # Ingress branches show both real AZ targets; subsequent identical
        # runtime interactions are represented once, preferably in the same AZ.
        key=(a.id if a.placement_role=='entry' else family(a),
             b.id if a.placement_role=='entry' else family(b),e.label)
        equivalent.setdefault(key, []).append(i)
        same_az=bool(a.availability_zone and a.availability_zone==b.availability_zone)
        priority=(not same_az,a.availability_zone or '',a.id)
        if b.scope=='external' and a.availability_zone:
            # External output interfaces sit to the right of the AZ lanes.
            # Use the rightmost equivalent caller's real edge, avoiding a wire
            # through its replica. Every replica relationship stays in detail.
            zones=sorted({n.availability_zone for n in spec.nodes if n.availability_zone})
            priority=(False,-zones.index(a.availability_zone),a.id)
        if key not in selected or priority<selected[key][0]:selected[key]=(priority,i)
    ordered=sorted(selected, key=lambda k:selected[k][1])
    indices=sorted(i for k in ordered for i in equivalent[k])
    return [{'edge':spec.edges[selected[k][1]],'paths':[[i] for i in equivalent[k]]} for k in ordered],indices
