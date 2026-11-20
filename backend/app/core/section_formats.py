"""Shared author/reviewer contracts for user-selected section presentation."""

import re
from collections import Counter

SUCCESS_CRITERIA = '''Use a minimal Markdown bullet list (normally 3-5 bullets; fewer when evidence supports fewer). Include quantifiable success targets explicitly stated in the BRD/user inputs, preserving the supplied target, unit, baseline and period. Also include descriptive success criteria grounded in explicitly stated functional requirements or required outcomes; when no numerical targets exist, use these observable functional outcomes instead. Each bullet is one short, factual sentence describing what successful delivery demonstrates, not an implementation task or a general benefit. Every criterion must be traceable to the BRD/user inputs; never derive commitments from proposed architecture, templates, industry norms or assumptions. Do not infer targets from workload volumes or architecture sizing. Do not invent percentages, baselines, SLAs, test counts, performance guarantees, acceptance processes or X% placeholders. Preserve conditions, exclusions and phase boundaries; do not turn optional/future requirements into current commitments. Deduplicate outcomes and do not repeat a descriptive equivalent of the same quantitative criterion. No tables, paragraphs, introductory labels or source/meta commentary. If neither quantitative targets nor supported functional outcomes exist, leave the section body blank without commentary.'''

TIMELINE_TABLE = '''Return only one concise milestone table: Timeframe | Milestone | Outcome. Group related activities; do not repeat module details. Preserve supplied dates and durations; leave unsupported timing blank. Do not add narrative or another table.'''

TIMELINE_GANTT = '''Return only one Markdown Gantt grid, not Mermaid, code, an image request or a prose timeline. Columns: S.No | Activity | chronological periods. Use W1, W2, ... for a supplied schedule in weeks or M1, M2, ... for months; use the input's actual granularity and duration, never assume an eight-month project from the example. Rows are concise project activities/phases, grouped rather than one per scope bullet. Put ■ in active delivery-period cells and ◆ in explicitly included hypercare/post-go-live support cells; leave inactive cells empty. The document renderer colours ■ light green and ◆ blue, with grey column headers. Preserve overlaps only where the schedule supports them. Do not invent start/end dates, durations or phase allocation. If dates/period allocation are not supported, leave timing cells blank; if no horizon exists use a single blank Timeframe column rather than inventing periods. No separate outcomes/deliverables table, legend or commentary.'''

GANTT_MARKERS = {'■': 'delivery activity', '◆': 'support activity'}


def timeline_format(value):
    value = str(value or 'table').strip().lower()
    if value not in {'table', 'gantt'}:
        raise ValueError('timeline_format must be table or gantt')
    return value


def sequence_gantt_rows(rows):
    """Anchor post-go-live support to the deployment milestone, not project W1.

    Preserve the existing marked duration; extend period columns if necessary
    rather than shortening support to fit the build horizon. Without a dated
    deployment milestone, preserve the supplied allocation.
    """
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
    support = lambda name: bool(re.search(r'hypercare|post[\s-]*go[\s-]*live|go[\s-]*live\s+support', name, re.I))
    deployments = [i for row in rows[1:] if not support(row[1])
                   and re.search(r'cutover|deployment to production|production deployment|go[\s-]*live', row[1], re.I)
                   and (not re.search(r'readiness|planning|design', row[1], re.I)
                        or re.search(r'cutover|deployment', row[1], re.I))
                   for i, cell in enumerate(row[2:]) if cell.strip() in GANTT_MARKERS]
    anchor = max(deployments) if deployments else None
    if anchor is None:
        return rows
    for row in rows[1:]:
        if not support(row[1]):
            continue
        active = [i for i, cell in enumerate(row[2:]) if cell.strip() in GANTT_MARKERS]
        if not active or min(active) >= anchor:
            continue
        for i in active:
            row[i + 2] = ''
        required = anchor + len(active) + 2
        while len(rows[0]) < required:
            rows[0].append(f'{prefix}{len(rows[0]) - 1}')
            for other in rows[1:]:
                other.append('')
        for i in range(anchor, anchor + len(active)):
            row[i + 2] = '◆'
    return rows


def sequence_gantt_markdown(text):
    """Normalize the grid and retain supplemental prose for preview and Word."""
    block, rows, notes = _gantt_parts(text)
    if block is None:
        return text
    corrected = sequence_gantt_rows(rows)
    if corrected != rows:
        print('[TIMELINE] Corrected post-go-live sequencing', flush=True)
    grid = ''
    if len(corrected) > 1:
        corrected.insert(1, ['---'] * len(corrected[0]))
        grid = '\n'.join('| ' + ' | '.join(row) + ' |' for row in corrected)
    return '\n\n'.join(part for part in (
        text[:block.start()].strip(), grid, '\n'.join(notes), text[block.end():].strip(),
    ) if part)


TIMELINE_GANTT += ''' All week/month columns use one project-wide clock: never restart W1 for a support deliverable. Hypercare/post-go-live support starts only after deployment/cutover, in the same labelled week only when go-live precedes support within that week. Do not start it before UAT or production deployment. Keep build duration distinct from the subsequent support term; include later periods when supported rather than squeezing or truncating support. State contractual phases without numbered timing as short notes below the grid. Check these dependencies before returning it.'''


def _table_safe_pipes(line):
    # Both the browser and Word decode the entity after splitting cells.
    def escape(match):
        slashes = match[1]
        return slashes[:-1] + '&#124;' if len(slashes) % 2 else match[0]

    return re.sub(r'(\\+)\|', escape, line)


def _gantt_parts(text, *, allow_timeframe=False):
    for block in re.finditer(r'(?m)^[ \t]*\|[^\r\n]*(?:\r?\n[ \t]*\|[^\r\n]*)*', str(text)):
        rows = [[cell.strip() for cell in _table_safe_pipes(line.strip())[1:].removesuffix('|').split('|')]
                for line in block.group().splitlines()]
        header = rows[0]
        width = len(header)
        if (len(rows) < 3 or len(rows[1]) != width
                or not all(re.fullmatch(r':?-+:?', cell) for cell in rows[1])
                or any(len(row) > width for row in rows[2:])):
            continue
        serials = [i for i, name in enumerate(header) if re.fullmatch(r's\.?\s*no\.?', name, re.I)]
        activities = [i for i, name in enumerate(header) if name.casefold() == 'activity']
        periods = [i for i, name in enumerate(header) if re.fullmatch(r'[WM]\d+', name, re.I)]
        if allow_timeframe and not periods:
            periods = [i for i, name in enumerate(header) if name.casefold() == 'timeframe']
        if len(serials) != 1 or len(activities) != 1 or not periods:
            continue
        prefix = header[periods[0]][0].upper()
        labels = [header[i].upper() for i in periods]
        if labels != ['TIMEFRAME'] and labels != [f'{prefix}{i}' for i in range(1, len(periods) + 1)]:
            continue
        serial, activity = serials[0], activities[0]
        extras = [i for i in range(len(header)) if i not in [serial, activity, *periods]]
        grid, notes = [['S.No', 'Activity', *labels]], []
        for row in rows[2:]:
            row = row + [''] * (width - len(row))
            timing = [row[i] for i in periods]
            note_columns = [i for i in extras if row[i]]
            if any(timing) or not note_columns:
                grid.append([row[serial], row[activity], *timing])
            for i in note_columns:
                label = f'{row[serial]}. {row[activity]}' if row[serial] else row[activity]
                notes.append(f'- {label} — {header[i] or "Note"}: {GANTT_MARKERS.get(row[i], row[i])}')
        return block, grid, notes
    return None, [], []


def _gantt_period_rows(text):
    return _gantt_parts(text)[1]


def _has_period_allocation(rows):
    return any(cell in GANTT_MARKERS for row in rows[1:] for cell in row[2:])


def has_gantt_allocation(text):
    return _has_period_allocation(sequence_gantt_rows(_gantt_period_rows(text)))


def has_complete_gantt_allocation(text):
    """A populated pilot must not hide unallocated in-scope rollout rows."""
    rows = _gantt_period_rows(text)
    return len(rows) > 1 and all(
        any(cell in GANTT_MARKERS for cell in row[2:]) for row in rows[1:]
    )


def retain_gantt_context(replacement, previous):
    """Keep the preceding intro and subsequent notes when replacing the grid."""
    block, _, notes = _gantt_parts(previous, allow_timeframe=True)
    before = previous[:block.start()] if block else ''
    after = previous[block.end():] if block else previous
    # A repaired estimate can extend its horizon. Do not retain our generated
    # caption for the old, incomplete grid alongside the new caption.
    if re.search(r'(?im)^Indicative\b[^.\n]*(?:schedule|horizon)[^.\n]*\.', replacement):
        before = re.sub(
            r'(?im)^Indicative\b[^.\n]*(?:schedule|horizon)[^.\n]*\.'
            r'(?: Activity timing is a planning estimate subject to approval\.)?\s*', '', before,
        )
    present = Counter(line.strip() for line in replacement.splitlines() if line.strip())

    def missing(fragment):
        lines = []
        for line in fragment.splitlines():
            if present[line.strip()]:
                present[line.strip()] -= 1
            else:
                lines.append(line)
        return '\n'.join(lines)

    return '\n\n'.join(part.strip() for part in (missing(before), replacement, missing('\n'.join(notes)), missing(after))
                       if part.strip())


def finalize_gantt_markdown(text, requirements, authored_text=''):
    """Keep the selected schedule visible without claiming estimates are agreed.

    Review can group phases or correct an allocation, but must not silently erase
    an entire authored planning grid merely because it is not a customer date
    baseline. Recover only a complete grid covering the supplied planning horizon;
    never construct dates or durations from an empty timeline here.
    """
    duration = requirements.get('planning_duration_weeks')
    estimated = not requirements.get('duration_weeks') and bool(duration)
    if estimated and not has_complete_gantt_allocation(text):
        original = _gantt_period_rows(authored_text)
        if (original and original[0][2] == 'W1' and len(original[0]) - 2 >= duration
                and has_complete_gantt_allocation(authored_text)):
            restored = finalize_gantt_markdown(authored_text, requirements)
            text = retain_gantt_context(restored, text)
            print('[TIMELINE] Restored indicative allocation removed during review', flush=True)
    text = sequence_gantt_markdown(text)
    if estimated and has_gantt_allocation(text):
        block, rows, _ = _gantt_parts(text)
        intro = text[:block.start()].strip()
        if not re.search(r'\bindicative\b', intro, re.I):
            horizon = len(rows[0]) - 2 if rows[0][2] == 'W1' else duration
            caption = (f'Indicative {horizon}-week implementation schedule. '
                       'Activity timing is a planning estimate subject to approval.')
            return caption + '\n\n' + text
        if not re.search(r'\bsubject to approval\b', intro, re.I):
            return (intro + '\n\nActivity timing is a planning estimate subject to approval.\n\n'
                    + text[block.start():])
    return text


def presentation_contract(category, metadata, requirements=None):
    if category == 'success_criteria':
        return SUCCESS_CRITERIA
    if category == 'timelines_deliverables':
        contract = TIMELINE_GANTT if timeline_format(metadata.get('timeline_format')) == 'gantt' else TIMELINE_TABLE
        requirements = requirements if isinstance(requirements, dict) else {}
        duration = requirements.get('planning_duration_weeks')
        if duration and not requirements.get('duration_weeks') and timeline_format(metadata.get('timeline_format')) == 'gantt':
            contract += (f' PLANNING SCHEDULE EXCEPTION (takes priority over blank-timing rules): '
                         f'Use the supplied {duration}-week planning horizon as an initial estimate, extending it '
                         'when necessary to allocate ALL in-scope delivery phases, including later rollout phases, '
                         'as an indicative estimate subject to approval, not a customer-agreed date baseline. '
                         'Do not limit the grid to the pilot when scope also includes extension or scale. '
                         'Every in-scope delivery row must have an allocation; do not leave later phases blank '
                         'or replace them with beyond-pilot notes. Use one project-wide clock and label the '
                         'actual total horizon in the caption. Phase gates remain dependencies, not evidence '
                         'that later in-scope work should be unscheduled. '
                         'Keep the selected Gantt populated with delivery markers; do not erase its allocation '
                         'because it is an estimate. Correct dependencies and group related work. '
                         'Preserve explicitly supplied timing over this estimate. Never turn procurement dates '
                         'or the contract term into implementation durations. State the indicative basis in '
                         'one short caption above the table. Do not invent additional support duration.')
        return contract
    return ''
