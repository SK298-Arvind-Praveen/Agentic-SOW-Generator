"""Cheap graph-preserving placement candidates before expensive wire routing."""
from itertools import permutations, islice


def nearby_rows(rows, edges):
    keys = [key for row in rows for key in row]
    if len(keys) < 3:
        return rows
    links = [(e.source, e.target) for e in edges if e.source in keys and e.target in keys]
    if not links:
        return rows
    widths = [len(row) for row in rows]
    def unpack(order):
        result, start = [], 0
        for width in widths:
            result.append(list(order[start:start + width]))
            start += width
        return result
    def score(order):
        positions = {key: (c, r) for r, row in enumerate(unpack(order)) for c, key in enumerate(row)}
        # Short neighbouring relationships first. Penalise reverse progression
        # mildly, allowing genuine feedback loops without inventing a DAG.
        return sum(abs(positions[a][0]-positions[b][0]) + abs(positions[a][1]-positions[b][1])
                   + .25 * (positions[b][1] < positions[a][1]) for a, b in links)
    best, best_score = keys, score(keys)
    # Bounded CPU only; this introduces no calls, routing retries or edge edits.
    for order in islice(permutations(keys), 720):
        value = score(order)
        if value < best_score:
            best, best_score = order, value
    return unpack(best)
