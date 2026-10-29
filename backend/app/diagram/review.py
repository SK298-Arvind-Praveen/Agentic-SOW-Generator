"""Shared routing measurements and architecture review guidance."""
from itertools import combinations
import heapq
import time

ARCHITECTURE_REVIEW_RULES = """
During planning anticipate connector crossings, lines through icons/text, unreadable
labels, crowding, unnecessary boundaries and dense fan-out. Do not claim to have
visually reviewed a rendered image when only the specification is available.
Retain every supported component and flow: improve ordering, grouping and spacing,
never invent infrastructure or delete nodes/flows just to make the view look clean.
Apply common AWS architecture conventions only when supported by the design:
- An ALB belongs to one VPC across availability-zone subnets, not between two VPCs.
  Place it centrally above its targets; do not put an internet-facing ALB in a private-subnet box.
- Account contains Region; VPC contains subnets/AZ workloads. A subnet belongs to one AZ.
- S3, Bedrock and other regional managed services are outside private-subnet boxes;
  VPC endpoints are access paths, not evidence that the managed service lives in the subnet.
- Users, SaaS and on-premise systems stay outside AWS account boundaries.
- Separate public ingress from private compute and data; do not imply public database access.
- Multi-AZ redundancy must come from the design, not from drawing different services in two AZs.
- IAM, KMS and monitoring are supporting controls, not sequential application-processing hops.
- Queues/buses decouple asynchronous consumers; databases are not arbitrary orchestration hubs.
- WAF protects supported ingress resources; NAT is outbound connectivity, not inbound routing.
- Show intended request/data direction and meaningful decision outcomes; distinguish replication
  from user traffic. Keep AWS icons only in architecture_overview; other views are flowcharts.
Few-shot corrections: S3 drawn inside a private subnet -> regional managed-service rail;
two target groups with ingress on far left -> centre ingress above the target groups;
crossing integration edges -> reorder peer nodes along their connected flow;
many monitoring lines -> keep the required flows, move controls together rather than deleting them.
Do not force a load balancer, VPC, second AZ or any other resource into a design that does not use it.
"""


def crosses(a, b, c, d):
    """Count proper orthogonal intersections, not shared endpoints."""
    if a[0] == b[0] and c[1] == d[1]:
        return min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1])
    if a[1] == b[1] and c[0] == d[0]:
        return crosses(c, d, a, b)
    return False


def hits_box(a, b, box):
    x, y, w, h = box
    if a[0] == b[0]:
        return x < a[0] < x+w and max(min(a[1], b[1]), y) < min(max(a[1], b[1]), y+h)
    return y < a[1] < y+h and max(min(a[0], b[0]), x) < min(max(a[0], b[0]), x+w)


def routes(spec, positions):
    """Choose obstacle-aware orthogonal lanes without changing graph semantics."""
    result = []
    for edge in spec.edges:
        sx, sy, sw, sh = positions[edge.source]
        tx, ty, tw, th = positions[edge.target]
        if ty >= sy+sh:
            start, end = (sx+sw/2, sy+sh), (tx+tw/2, ty)
        elif sy >= ty+th:
            start, end = (sx+sw/2, sy), (tx+tw/2, ty+th)
        elif tx >= sx+sw:
            start, end = (sx+sw, sy+sh/2), (tx, ty+th/2)
        else:
            start, end = (sx, sy+sh/2), (tx+tw, ty+th/2)
        ys = {(start[1]+end[1])/2}
        xs = {(start[0]+end[0])/2}
        for x,y,w,h in positions.values():
            xs.update((max(2,x-14), x+w+14))
            ys.update((max(2,y-14), y+h+14))
        candidates = [[start,(x,start[1]),(x,end[1]),end] for x in sorted(xs)]
        candidates += [[start,(start[0],y),(end[0],y),end] for y in sorted(ys)]
        obstacles = [box for key,box in positions.items() if key not in {edge.source,edge.target}]
        def cost(points):
            segments = list(zip(points,points[1:]))
            collisions = sum(hits_box(a,b,box) for a,b in segments for box in obstacles)
            intersections = sum(crosses(a,b,c,d) for a,b in segments for path in result for c,d in zip(path,path[1:]))
            length = sum(abs(a[0]-b[0])+abs(a[1]-b[1]) for a,b in segments)
            return collisions*100000 + intersections*500 + length
        chosen = min(candidates,key=cost)
        # Zero-length terminal segments would hide arrowheads.
        result.append([p for i,p in enumerate(chosen) if not i or p != chosen[i-1]])
    return result


def geometry_report(spec, positions, paths):
    overlaps = sum(
        max(a[0],b[0]) < min(a[0]+a[2],b[0]+b[2]) and max(a[1],b[1]) < min(a[1]+a[3],b[1]+b[3])
        for a,b in combinations(positions.values(),2)
    )
    crossings = sum(crosses(a,b,c,d) for p,q in combinations(paths,2) for a,b in zip(p,p[1:]) for c,d in zip(q,q[1:]))
    collisions = sum(hits_box(a,b,box) for edge,path in zip(spec.edges,paths)
                     for a,b in zip(path,path[1:]) for key,box in positions.items()
                     if key not in {edge.source,edge.target})
    ambiguous = sum(_ambiguous_contact(p, q) for p, q in combinations(paths, 2))
    return {"node_overlaps": overlaps, "connector_node_intersections": collisions,
            "ambiguous_connector_pairs": ambiguous,
            "connector_crossings": crossings, "nodes": len(spec.nodes), "edges": len(spec.edges),
            **connector_report(positions, paths)}


def _ambiguous_contact(p, q):
    """Shared stretches and T junctions are not proper crossings but look connected."""
    for a,b in zip(p,p[1:]):
        for c,d in zip(q,q[1:]):
            if a[0] == b[0] == c[0] == d[0]:
                if min(max(a[1],b[1]),max(c[1],d[1])) > max(min(a[1],b[1]),min(c[1],d[1])):
                    return True
            elif a[1] == b[1] == c[1] == d[1]:
                if min(max(a[0],b[0]),max(c[0],d[0])) > max(min(a[0],b[0]),min(c[0],d[0])):
                    return True
            elif a[0] == b[0] and c[1] == d[1]:
                if (min(c[0],d[0]) <= a[0] <= max(c[0],d[0]) and
                    min(a[1],b[1]) <= c[1] <= max(a[1],b[1]) and not crosses(a,b,c,d)):
                    return True
            elif a[1] == b[1] and c[0] == d[0]:
                if (min(a[0],b[0]) <= c[0] <= max(a[0],b[0]) and
                    min(c[1],d[1]) <= a[1] <= max(c[1],d[1]) and not crosses(a,b,c,d)):
                    return True
    return False


def connector_report(positions, paths):
    """Measure bends and detours independently of crossings; zero crossings is not enough."""
    lengths, detours, bends = [], [], []
    span = max(max(b[0]+b[2] for b in positions.values())-min(b[0] for b in positions.values()),
               max(b[1]+b[3] for b in positions.values())-min(b[1] for b in positions.values()), 1) if positions else 1
    for path in paths:
        points = [p for i, p in enumerate(path) if not i or p != path[i-1]]
        segments = [(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:])]
        length = sum(abs(x)+abs(y) for x, y in segments)
        direct = (abs(points[-1][0]-points[0][0])+abs(points[-1][1]-points[0][1])) if len(points)>1 else 0
        lengths.append(length/span)
        detours.append(length/max(direct, 1))
        bends.append(sum(a[0]*b[1] != a[1]*b[0] for a, b in zip(segments, segments[1:])))
    return {'connector_length_normalized': round(sum(lengths), 3),
            'longest_connector_fraction': round(max(lengths, default=0), 3),
            'max_connector_detour': round(max(detours, default=1), 2),
            'connector_bends': sum(bends),
            'long_connector_count': sum(v > .65 for v in lengths),
            'detouring_connector_count': sum(v > 1.6 for v in detours)}


def layout_quality(metrics):
    """Lower is better. Routing preference only; font size is not a criterion."""
    return (metrics.get('connector_crossings', 0)*4
            + metrics.get('ambiguous_connector_pairs', 0)*24
            + metrics.get('connector_length_normalized', 0)*2
            + metrics.get('connector_bends', 0)*.18
            + metrics.get('long_connector_count', 0)*2
            + max(0, metrics.get('longest_connector_fraction', 0)-.5)**2*8
            # Relative detour alone over-penalises a short branch around an icon
            # caption and can select much longer page-spanning straight routes.
            # Absolute length and longest-path penalties above remain decisive.
            + metrics.get('detouring_connector_count', 0)*.5)


def local_routes(spec, positions, boxes, parents, width, height, deadline=None, captions=None, iconic=False):
    """Shortest orthogonal visibility-grid routes, with ports chosen by proximity.

    Keep every edge and real boundary. Unrelated containers and all boundary
    headers are obstacles; ancestral boundary sides can be crossed intentionally.
    A bend penalty prevents gratuitous zigzags. No generated executable code.
    """
    icon_nodes = {n.id for n in spec.nodes if getattr(n, 'icon_key', '')} if iconic else set()
    def ports(rect, icon=False, offset=0, gap=16):
        x, y, w, h = rect
        if icon:
            # Route outside the whole label footprint, then join the visible icon.
            return { (x-gap,y+37+offset): (x+w/2-32,y+37+offset),
                     (x+w+gap,y+37+offset): (x+w/2+32,y+37+offset),
                     (x+w/2+offset,y-gap): (x+w/2+offset,y+5) }
        return { (x-gap,y+h/2+offset): (x,y+h/2+offset),
                 (x+w+gap,y+h/2+offset): (x+w,y+h/2+offset),
                 (x+w/2+offset,y-gap): (x+w/2+offset,y),
                 (x+w/2+offset,y+h+gap): (x+w/2+offset,y+h) }
    def ancestors(key):
        result = set()
        while key in parents:
            key = parents[key]
            result.add(key)
        return result
    result = []
    def boundary_parallel_cost(a,b):
        penalty = 0
        for x,y,w,h in boxes.values():
            if a[1] == b[1] and min(abs(a[1]-y),abs(a[1]-y-h)) < 6:
                penalty += max(0,min(max(a[0],b[0]),x+w)-max(min(a[0],b[0]),x))*20
            if a[0] == b[0] and min(abs(a[0]-x),abs(a[0]-x-w)) < 6:
                penalty += max(0,min(max(a[1],b[1]),y+h)-max(min(a[1],b[1]),y))*20
        return penalty
    def crossing_cost(a, b):
        penalty = 0
        for path in result:
            for c, d in zip(path, path[1:]):
                # Grid vertices often land exactly on an existing connector.
                # Strict segment intersection would miss these until simplification.
                if a[0] == b[0] and c[1] == d[1]:
                    penalty += 180 * (min(c[0],d[0]) < a[0] < max(c[0],d[0])
                                      and min(a[1],b[1]) <= c[1] <= max(a[1],b[1]))
                elif a[1] == b[1] and c[0] == d[0]:
                    penalty += 180 * (min(c[1],d[1]) < a[1] < max(c[1],d[1])
                                      and min(a[0],b[0]) <= c[0] <= max(a[0],b[0]))
                elif a[0] == b[0] == c[0] == d[0]:
                    penalty += max(0,min(max(a[1],b[1]),max(c[1],d[1]))-max(min(a[1],b[1]),min(c[1],d[1])))*2
                elif a[1] == b[1] == c[1] == d[1]:
                    penalty += max(0,min(max(a[0],b[0]),max(c[0],d[0]))-max(min(a[0],b[0]),min(c[0],d[0])))*2
                elif a[1] == b[1] and c[1] == d[1] and abs(a[1]-c[1]) < 20:
                    # Parallel tracks a few pixels apart look like a single
                    # wire at document scale, even without a mathematical cross.
                    overlap = max(0,min(max(a[0],b[0]),max(c[0],d[0]))-max(min(a[0],b[0]),min(c[0],d[0])))
                    penalty += overlap * (20-abs(a[1]-c[1])) / 5
                elif a[0] == b[0] and c[0] == d[0] and abs(a[0]-c[0]) < 20:
                    overlap = max(0,min(max(a[1],b[1]),max(c[1],d[1]))-max(min(a[1],b[1]),min(c[1],d[1])))
                    penalty += overlap * (20-abs(a[0]-c[0])) / 5
        return penalty
    incident = {key: [i for i,e in enumerate(spec.edges) if key in (e.source,e.target)] for key in positions}
    for edge_index, edge in enumerate(spec.edges):
        def terminals(key):
            x,y,w,h = positions[key]
            cy = y+37 if key in icon_nodes else y+h/2
            def preferred_side(index):
                connection = spec.edges[index]
                peer = connection.target if connection.source == key else connection.source
                px,py,pw,ph = positions[peer]
                dx,dy = px+pw/2-(x+w/2), py+(37 if peer in icon_nodes else ph/2)-cy
                return ('left' if dx < 0 else 'right') if abs(dx)>=abs(dy) else ('top' if dy<0 else 'bottom')
            result_ports = {}
            for side_index,side in enumerate(('left','right','top','bottom')):
                if key in icon_nodes and side == 'bottom':
                    continue
                peers = [i for i in incident[key] if preferred_side(i) == side or i == edge_index]
                def peer_coordinate(index):
                    connection = spec.edges[index]
                    peer = connection.target if connection.source == key else connection.source
                    px,py,pw,ph = positions[peer]
                    return py+(37 if peer in icon_nodes else ph/2) if side in {'left','right'} else px+pw/2
                # Port order follows destination order, not arbitrary JSON edge
                # order; otherwise fan-out arrows cross immediately beside an icon.
                peers.sort(key=lambda i:(peer_coordinate(i),i))
                # Distinct arrowheads must remain distinguishable at Word size,
                # especially opposite-direction requests to a shared system.
                spread = 44 if key in icon_nodes else max(36, min(w, h)-32)
                step = 22 if key in icon_nodes else 32
                offset = (peers.index(edge_index)-(len(peers)-1)/2)*min(step,spread/max(1,len(peers)-1))
                gap = 16
                if key not in icon_nodes and len(peers) > 1:
                    # Separate the final approach tracks as well as arrowheads.
                    # Otherwise all bends reuse x-16 and create a false T-junction.
                    gap += (len(peers)-1-peers.index(edge_index))*22
                port,anchor = list(ports(positions[key],key in icon_nodes,offset,gap).items())[side_index]
                if not (8 <= port[0] <= width-8 and 8 <= port[1] <= height-8):
                    continue
                result_ports[port] = anchor
            return result_ports
        start_ports, end_ports = terminals(edge.source), terminals(edge.target)
        starts, ends = list(start_ports), list(end_ports)
        allowed = ancestors(edge.source) | ancestors(edge.target)
        # Border-following paths are invisible after the cards are painted and
        # look like connections to unrelated boxes. Keep an explicit clearance.
        obstacles = [(x-8,y-8,w+16,h+16) for x,y,w,h in positions.values()]
        obstacles += [rect if key not in allowed else (rect[0], rect[1],
                      min(rect[2], len((captions or {}).get(key, key))*9+54), 39)
                      for key, rect in boxes.items()]
        xs, ys = {8, width-8}, {8, height-8}
        for x, y, w, h in obstacles:
            xs.update((max(8, x-12), min(width-8, x+w+12)))
            ys.update((max(8, y-12), min(height-8, y+h+12)))
        for x, y in starts+ends:
            xs.add(x)
            ys.add(y)
        xs, ys = sorted(xs), sorted(ys)
        lookup_x, lookup_y = {v:i for i,v in enumerate(xs)}, {v:i for i,v in enumerate(ys)}
        goals = {(lookup_x[x], lookup_y[y]) for x,y in ends}
        def heuristic(i, j):
            return min(abs(xs[i]-x)+abs(ys[j]-y) for x,y in ends)
        queue, costs, previous = [], {}, {}
        for x, y in starts:
            state = (lookup_x[x], lookup_y[y], -1)
            costs[state] = 0
            heapq.heappush(queue, (heuristic(*state[:2]), 0, state))
        segment_costs = {}
        found = None
        while queue:
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError('Local connector routing exceeded layout budget')
            _, cost, state = heapq.heappop(queue)
            if cost != costs.get(state):
                continue
            i, j, direction = state
            if (i, j) in goals:
                found = state
                break
            for ni, nj, nd in ((i-1,j,0),(i+1,j,0),(i,j-1,1),(i,j+1,1)):
                if not (0 <= ni < len(xs) and 0 <= nj < len(ys)):
                    continue
                a, b = (xs[i],ys[j]), (xs[ni],ys[nj])
                key = tuple(sorted((a,b)))
                if key not in segment_costs:
                    segment_costs[key] = (None if any(hits_box(a,b,box) for box in obstacles) else
                        abs(a[0]-b[0])+abs(a[1]-b[1]) + crossing_cost(a,b) + boundary_parallel_cost(a,b))
                step = segment_costs[key]
                if step is None:
                    continue
                candidate = cost+step+(24 if direction != -1 and nd != direction else 0)
                nxt = (ni,nj,nd)
                if candidate < costs.get(nxt, float('inf')):
                    costs[nxt] = candidate
                    previous[nxt] = state
                    heapq.heappush(queue, (candidate+heuristic(ni,nj), candidate, nxt))
        if found is None:
            raise ValueError('No unobstructed local route for '+edge.source+' -> '+edge.target)
        points = []
        while found is not None:
            points.append((xs[found[0]],ys[found[1]]))
            found = previous.get(found)
        points.reverse()
        # Fixed normal stubs ensure arrowheads meet a visible edge perpendicularly,
        # never tangentially along the box border. Simplification preserves them.
        points = [start_ports[points[0]], *points, end_ports[points[-1]]]
        simplified = []
        for point in points:
            while len(simplified)>1 and ((simplified[-2][0] == simplified[-1][0] == point[0])
                    or (simplified[-2][1] == simplified[-1][1] == point[1])):
                simplified.pop()
            simplified.append(point)
        if len(simplified)<2:
            raise ValueError('Invalid zero-length route')
        result.append(simplified)
    return result
