"""Content-preserving layout checks shared by authoring, review and export."""
import re
from collections import Counter


_BOX_EDGE = re.compile(r'^\s*[+┌└├┬┼╔╚╠][\s+|\-─━═┐┘┤┴┬┼╗╝╣]+\s*$')


def strip_text_diagrams(text):
    """Remove ASCII box drawings, not genuine Markdown comparison tables.

    The architecture image is supplied by the diagram pipeline. Require multiple
    box borders so ordinary prose, bullets and Markdown separators are untouched.
    """
    lines = text.splitlines()
    result = []
    index = 0
    while index < len(lines):
        if not _BOX_EDGE.match(lines[index]):
            result.append(lines[index])
            index += 1
            continue
        end = index
        borders = 0
        while end < len(lines):
            line = lines[end].strip()
            if _BOX_EDGE.match(line):
                borders += 1
            elif not (not line or line.startswith(('|', '│', '║')) or
                      re.fullmatch(r'[\s|vV^<>↓↑→←+\-]+', line)):
                break
            end += 1
        if borders >= 2:
            # Remove the fence enclosing only this drawing as well.
            if result and re.fullmatch(r'\s*```(?:text|ascii)?\s*', result[-1]):
                result.pop()
            if end < len(lines) and lines[end].strip() == '```':
                end += 1
            index = end
        else:
            result.append(lines[index])
            index += 1
    return '\n'.join(result).strip()


def presentation_issues(text, category):
    issues = []
    if category == 'architecture_diagram' and strip_text_diagrams(text) != text.strip():
        issues.append('ASCII diagram must not appear in architecture prose')
    if category == 'architecture_diagram':
        if not any(re.match(r'^\s*[-*+]\s+', line) for line in text.splitlines()):
            issues.append('Solution Architecture must use concise bullet points')
        if any(line.strip() and not re.match(r'^\s*[-*+]\s+', line) for line in text.splitlines()):
            issues.append('Solution Architecture must not contain prose paragraphs or catalogue tables')
    if category == 'scope_of_work':
        headings = list(re.finditer(r'(?m)^(#{2,6}) .+$', text))
        depth = max((len(h.group(1)) for h in headings), default=0)
        for index, heading in enumerate(headings):
            if len(heading.group(1)) != depth:
                continue
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            body = text[heading.end():end]
            lines = [line for line in body.splitlines() if line.strip()]
            if not lines or not any(re.match(r'^\s*[-*+]\s+', line) for line in lines):
                issues.append('Every scope module must retain action bullets')
                break
            if any(not re.match(r'^(?:\s*[-*+]\s+|\s*\||\s{2,}\S)', line) for line in lines):
                issues.append('Scope module actions must not be collapsed into prose paragraphs')
                break
    if category in {'scope_of_work', 'architecture_diagram', 'business_benefits', 'customer_responsibilities'}:
        for line in text.splitlines():
            if not re.match(r'^\s*[-*+]\s+', line):
                continue
            sentence = re.sub(r'\b(?:e\.g|i\.e|U\.S|U\.K|Ltd|Inc|Dr|Mr|Ms)\.', '', line)
            if re.search(r'[.!?]\s+(?=(?:\*\*)?[A-Z])', sentence):
                issues.append('Keep one action sentence per bullet, not a paragraph inside a bullet')
                break
    return issues


def has_deliverables_table(text):
    preamble = re.split(r'(?m)^#{2,6} ', text, maxsplit=1)[0]
    return bool(re.search(r'(?im)^\s*\|\s*deliverable\s*\|', preamble))


def regroup_scope_modules(text, groups):
    """Merge headings without letting an LLM rewrite/drop their obligations.

    Each original module must occur exactly once under its original deliverable.
    Only exact duplicate bullet lines within a merged group are removed.
    """
    if not isinstance(groups, list) or not groups:
        raise ValueError('Module groups must be a non-empty list')
    has_deliverables = bool(re.search(r'(?m)^#### ', text))
    parents = list(re.finditer(r'(?m)^### (.+)$', text)) if has_deliverables else []
    depth = '####' if has_deliverables else '###'
    prefix = text[:parents[0].start()] if parents else ''
    blocks = [(p.group(1), text[p.end():parents[i+1].start() if i+1 < len(parents) else len(text)])
              for i, p in enumerate(parents)] if parents else [('', text)]
    parent_names = [name for name, _ in blocks]
    if len(set(parent_names)) != len(parent_names):
        raise ValueError('Ambiguous deliverable names')
    for group in groups:
        if (not isinstance(group, dict) or set(group) != {'deliverable', 'heading', 'modules'}
                or group['deliverable'] not in parent_names or not isinstance(group['heading'], str)
                or not group['heading'].strip() or re.search(r'[\r\n#|]', group['heading'])
                or not isinstance(group['modules'], list) or not group['modules']
                or not all(isinstance(m, str) for m in group['modules'])):
            raise ValueError('Invalid module group')
    output = [prefix.rstrip()] if prefix.strip() else []
    for parent, block in blocks:
        modules = list(re.finditer(rf'(?m)^{depth} (.+)$', block))
        names = [m.group(1) for m in modules]
        selected = [g for g in groups if g['deliverable'] == parent]
        if (not modules or len(set(names)) != len(names)
                or Counter(m for g in selected for m in g['modules']) != Counter(names)
                or len({g['heading'] for g in selected}) != len(selected)):
            raise ValueError('Grouping must preserve every module exactly once within its deliverable')
        bodies = {m.group(1): block[m.end():modules[i+1].start() if i+1 < len(modules) else len(block)].strip()
                  for i, m in enumerate(modules)}
        if parent:
            output.append('### ' + parent)
        if block[:modules[0].start()].strip():
            output.append(block[:modules[0].start()].strip())
        for group in selected:
            output.append(depth + ' ' + group['heading'].strip())
            seen = set()
            lines = []
            for name in group['modules']:
                for line in bodies[name].splitlines():
                    is_bullet = bool(re.match(r'^\s*[-*+]\s+', line))
                    if is_bullet and line.strip() in seen:
                        continue
                    if is_bullet:
                        seen.add(line.strip())
                    lines.append(line)
            output.append('\n'.join(lines).strip())
    return '\n\n'.join(output)
