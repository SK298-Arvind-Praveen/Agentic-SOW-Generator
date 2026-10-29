"""Shared author/reviewer contracts for user-selected section presentation."""

SUCCESS_CRITERIA = '''Use a minimal Markdown bullet list (normally 3-5 bullets; fewer when evidence supports fewer). Include quantifiable success targets explicitly stated in the BRD/user inputs, preserving the supplied target, unit, baseline and period. Also include descriptive success criteria grounded in explicitly stated functional requirements or required outcomes; when no numerical targets exist, use these observable functional outcomes instead. Each bullet is one short, factual sentence describing what successful delivery demonstrates, not an implementation task or a general benefit. Every criterion must be traceable to the BRD/user inputs; never derive commitments from proposed architecture, templates, industry norms or assumptions. Do not infer targets from workload volumes or architecture sizing. Do not invent percentages, baselines, SLAs, test counts, performance guarantees, acceptance processes or X% placeholders. Preserve conditions, exclusions and phase boundaries; do not turn optional/future requirements into current commitments. Deduplicate outcomes and do not repeat a descriptive equivalent of the same quantitative criterion. No tables, paragraphs, introductory labels or source/meta commentary. If neither quantitative targets nor supported functional outcomes exist, leave the section body blank without commentary.'''

TIMELINE_TABLE = '''Return only one concise milestone table: Timeframe | Milestone | Outcome. Group related activities; do not repeat module details. Preserve supplied dates and durations; leave unsupported timing blank. Do not add narrative or another table.'''

TIMELINE_GANTT = '''Return only one Markdown Gantt grid, not Mermaid, code, an image request or a prose timeline. Columns: S.No | Activity | chronological periods. Use W1, W2, ... for a supplied schedule in weeks or M1, M2, ... for months; use the input's actual granularity and duration, never assume an eight-month project from the example. Rows are concise project activities/phases, grouped rather than one per scope bullet. Put ■ in active delivery-period cells and ◆ in explicitly included hypercare/post-go-live support cells; leave inactive cells empty. The document renderer colours ■ light green and ◆ blue, with grey column headers. Preserve overlaps only where the schedule supports them. Do not invent start/end dates, durations or phase allocation. If dates/period allocation are not supported, leave timing cells blank; if no horizon exists use a single blank Timeframe column rather than inventing periods. No separate outcomes/deliverables table, legend or commentary.'''


def timeline_format(value):
    value = str(value or 'table').strip().lower()
    if value not in {'table', 'gantt'}:
        raise ValueError('timeline_format must be table or gantt')
    return value


def sequence_gantt_rows(rows):
    """Anchor post-go-live support to the deployment milestone, not project W1.

    Preserve the existing marked duration; extend period columns if necessary
    rather than shortening support to fit the build horizon. Without a dated
    deployment milestone, leave support timing unallocated.
    """
    import re
    rows = [list(row) for row in rows]
    if not rows or len(rows[0]) < 3 or rows[0][1].strip().lower() != 'activity':
        return rows
    periods = rows[0][2:]
    if not all(re.fullmatch(r'[WM]\d+', p.strip(), re.I) for p in periods):
        return rows
    prefix = periods[0].strip()[0].upper()
    if [p.strip().upper() for p in periods] != [f'{prefix}{i}' for i in range(1, len(periods) + 1)]:
        return rows
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        return rows
    support = lambda name: bool(re.search(r'hypercare|post[\s-]*go[\s-]*live', name, re.I))
    deployments = [i for row in rows[1:] if not support(row[1])
                   and re.search(r'cutover|deployment to production|production deployment|go[\s-]*live', row[1], re.I)
                   and (not re.search(r'readiness|planning|design', row[1], re.I)
                        or re.search(r'cutover|deployment', row[1], re.I))
                   for i, cell in enumerate(row[2:]) if cell.strip() in {'■', '◆'}]
    anchor = max(deployments) if deployments else None
    for row in rows[1:]:
        if not support(row[1]):
            continue
        active = [i for i, cell in enumerate(row[2:]) if cell.strip() in {'■', '◆'}]
        if not active:
            continue
        if anchor is not None and min(active) >= anchor:
            continue
        for i in active:
            row[i + 2] = ''
        if anchor is None:
            continue
        required = anchor + len(active) + 2
        while len(rows[0]) < required:
            rows[0].append(f'{prefix}{len(rows[0]) - 1}')
            for other in rows[1:]:
                other.append('')
        for i in range(anchor, anchor + len(active)):
            row[i + 2] = '◆'
    return rows


def sequence_gantt_markdown(text):
    """Shared post-review check so preview and exported document agree."""
    lines = str(text).splitlines()
    if not lines or any(not line.strip().startswith('|') for line in lines if line.strip()):
        return text
    rows = [[c.strip() for c in line.strip().strip('|').split('|')] for line in lines if line.strip()]
    if len(rows) < 3:
        return text
    corrected = sequence_gantt_rows([rows[0]] + rows[2:])
    if corrected == [rows[0]] + rows[2:]:
        return text
    print('[TIMELINE] Corrected post-go-live sequencing; preserved marked support duration', flush=True)
    corrected.insert(1, ['---'] * len(corrected[0]))
    return '\n'.join('| ' + ' | '.join(row) + ' |' for row in corrected)


TIMELINE_GANTT += ''' All week/month columns use one project-wide clock: never restart W1 for a support deliverable. Hypercare/post-go-live support starts only after deployment/cutover, in the same labelled week only when go-live precedes support within that week. Do not start it before UAT or production deployment. Keep build duration distinct from the subsequent support term; include later periods when supported rather than squeezing or truncating support. Check these dependencies before returning the grid.'''


def presentation_contract(category, metadata):
    if category == 'success_criteria':
        return SUCCESS_CRITERIA
    if category == 'timelines_deliverables':
        return TIMELINE_GANTT if timeline_format(metadata.get('timeline_format')) == 'gantt' else TIMELINE_TABLE
    return ''
