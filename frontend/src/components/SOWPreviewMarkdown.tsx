import React from 'react';

export type PreviewContent = Record<string, unknown>;

export interface EditableMarkdownSection {
  key: string;
  label: string;
}

const NON_BODY_KEYS = new Set([
  'cover_page',
  'toc_structure',
  'table_of_contents',
  'tableofcontents',
  'table_contents',
  'generation_quality_summary',
  'architecture_diagram_asset',
  'architecture_diagram_assets',
]);

const SECTION_LABELS: Record<string, string> = {
  document_control_and_basis: 'Document Version Control',
  about_shellkode: 'About Shellkode',
  about_company: 'About Client',
  about_client: 'About Client',
  project_overview: 'Objective',
  current_state_and_business_context: 'Current State and Business Context',
  scope_of_work: 'Scope of Work',
  architecture_diagram: 'Architecture Diagram',
  customer_dependencies: 'Customer Dependencies',
  assumptions: 'Assumptions',
  out_of_scope: 'Out of Scope',
  timelines_and_deliverables: 'Timelines and Deliverables',
  aws_pricing: 'AWS Pricing',
  customer_responsibilities: 'Customer Responsibilities',
  project_team_effort: 'Project Team Effort',
  open_clarifications: 'Open Clarifications',
  success_criteria: 'Success Criteria',
  project_plan_termination: 'Project Plan Termination',
  contacts_and_reporting: 'Contacts and Reporting',
  terms_and_conditions: 'Terms and Conditions',
  acceptance_and_signatories_to_statement_of_work: 'Acceptance and Signatories',
};

export const previewSectionLabel = (key: string): string =>
  SECTION_LABELS[key] || key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, character => character.toUpperCase());

export const isPreviewBodyKey = (key: string): boolean => !NON_BODY_KEYS.has(key);

export const getEffectivePreviewContent = (previewData: any): unknown => {
  const updated = previewData?.updated_content;
  if (updated && typeof updated === 'object' && Object.keys(updated).length > 0) {
    return updated;
  }
  return previewData?.content;
};

export const serializePreviewContent = (content: PreviewContent): {
  markdown: string;
  sections: EditableMarkdownSection[];
} => {
  const sections = Object.entries(content)
    .filter(([key, value]) => isPreviewBodyKey(key) && typeof value === 'string')
    .map(([key]) => ({ key, label: previewSectionLabel(key) }));

  const markdown = sections.map(section => {
    const value = String(content[section.key] ?? '').trim();
    return `## ${section.label}\n\n${value}`.trimEnd();
  }).join('\n\n');

  return { markdown, sections };
};

export const parsePreviewContentMarkdown = (
  markdown: string,
  sections: EditableMarkdownSection[],
): Record<string, string> => {
  const recognisedLabels = new Map(sections.map(section => [section.label, section.key]));
  const occurrences: Array<{ key: string; label: string; start: number; bodyStart: number }> = [];
  const counts = new Map<string, number>();
  const headingPattern = /^##\s+(.+?)\s*$/gm;
  let match: RegExpExecArray | null;

  while ((match = headingPattern.exec(markdown)) !== null) {
    const label = match[1].trim();
    const key = recognisedLabels.get(label);
    if (!key) continue;
    occurrences.push({ key, label, start: match.index, bodyStart: headingPattern.lastIndex });
    counts.set(key, (counts.get(key) || 0) + 1);
  }

  const missing = sections.filter(section => !counts.has(section.key));
  const duplicated = sections.filter(section => (counts.get(section.key) || 0) > 1);
  if (missing.length || duplicated.length) {
    const details = [
      missing.length ? `missing: ${missing.map(section => section.label).join(', ')}` : '',
      duplicated.length ? `duplicated: ${duplicated.map(section => section.label).join(', ')}` : '',
    ].filter(Boolean).join('; ');
    throw new Error(`Keep each generated ## section heading exactly once (${details}).`);
  }

  occurrences.sort((left, right) => left.start - right.start);
  const parsed: Record<string, string> = {};
  occurrences.forEach((occurrence, index) => {
    const nextStart = occurrences[index + 1]?.start ?? markdown.length;
    parsed[occurrence.key] = markdown.slice(occurrence.bodyStart, nextStart).trim();
  });
  return parsed;
};

const safeLink = (href: string): string | null => {
  const trimmed = href.trim();
  return /^(https?:\/\/|mailto:)/i.test(trimmed) ? trimmed : null;
};

const renderInline = (text: string, keyPrefix: string): React.ReactNode[] => {
  const tokenPattern = /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\[[^\]\n]+\]\([^)\n]+\)|\*[^*\n]+\*|_[^_\n]+_)/g;
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  let token: RegExpExecArray | null;
  let tokenIndex = 0;

  while ((token = tokenPattern.exec(text)) !== null) {
    if (token.index > cursor) nodes.push(text.slice(cursor, token.index));
    const value = token[0];
    const key = `${keyPrefix}-${tokenIndex++}`;
    if ((value.startsWith('**') && value.endsWith('**')) || (value.startsWith('__') && value.endsWith('__'))) {
      nodes.push(<strong key={key}>{value.slice(2, -2)}</strong>);
    } else if (value.startsWith('`')) {
      nodes.push(<code key={key}>{value.slice(1, -1)}</code>);
    } else if (value.startsWith('[')) {
      const linkMatch = value.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      const href = linkMatch ? safeLink(linkMatch[2]) : null;
      nodes.push(href
        ? <a key={key} href={href} target="_blank" rel="noreferrer">{linkMatch![1]}</a>
        : value);
    } else {
      nodes.push(<em key={key}>{value.slice(1, -1)}</em>);
    }
    cursor = token.index + value.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
};

const splitTableRow = (line: string): string[] => line
  .trim()
  .replace(/^\|/, '')
  .replace(/\|$/, '')
  .split('|')
  .map(cell => cell.trim());

const isTableDivider = (line: string): boolean => {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
};

const startsBlock = (lines: string[], index: number): boolean => {
  const line = lines[index] || '';
  if (!line.trim()) return true;
  if (/^#{1,6}\s+/.test(line) || /^```/.test(line) || /^>\s?/.test(line)) return true;
  if (/^\s*(?:[-+*]|\d+\.)\s+/.test(line) || /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) return true;
  return line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1]);
};

export const MarkdownRenderer: React.FC<{ markdown: string; className?: string }> = ({ markdown, className = '' }) => {
  const lines = String(markdown || '').replace(/\r\n?/g, '\n').split('\n');
  const blocks: React.ReactNode[] = [];
  let index = 0;
  let blockIndex = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (/^```/.test(line)) {
      const language = line.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index])) code.push(lines[index++]);
      if (index < lines.length) index += 1;
      const codeKey = blockIndex++;
      blocks.push(<pre key={`block-${codeKey}`}><code data-language={language}>{code.join('\n')}</code></pre>);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const headingKey = blockIndex++;
      blocks.push(React.createElement(
        `h${level}`,
        { key: `block-${headingKey}` },
        renderInline(heading[2], `heading-${headingKey}`),
      ));
      index += 1;
      continue;
    }

    if (line.includes('|') && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const header = splitTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        rows.push(splitTableRow(lines[index++]));
      }
      const tableKey = blockIndex++;
      blocks.push(
        <div className="markdown-table-wrap" key={`block-${tableKey}`}>
          <table>
            <thead><tr>{header.map((cell, cellIndex) => <th key={cellIndex}>{renderInline(cell, `th-${tableKey}-${cellIndex}`)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => (
              <tr key={rowIndex}>{header.map((_, cellIndex) => <td key={cellIndex}>{renderInline(row[cellIndex] || '', `td-${tableKey}-${rowIndex}-${cellIndex}`)}</td>)}</tr>
            ))}</tbody>
          </table>
        </div>
      );
      continue;
    }

    const listMatch = line.match(/^(\s*)([-+*]|\d+\.)\s+(.+)$/);
    if (listMatch) {
      const ordered = /\d+\./.test(listMatch[2]);
      const items: Array<{ text: string; indent: number }> = [];
      while (index < lines.length) {
        const item = lines[index].match(/^(\s*)([-+*]|\d+\.)\s+(.+)$/);
        if (!item || /\d+\./.test(item[2]) !== ordered) break;
        items.push({ text: item[3], indent: Math.floor(item[1].replace(/\t/g, '  ').length / 2) });
        index += 1;
      }
      const ListTag = ordered ? 'ol' : 'ul';
      const listKey = blockIndex++;
      blocks.push(
        <ListTag key={`block-${listKey}`}>
          {items.map((item, itemIndex) => (
            <li key={itemIndex} style={{ marginLeft: `${item.indent * 1.1}rem` }}>
              {renderInline(item.text, `li-${listKey}-${itemIndex}`)}
            </li>
          ))}
        </ListTag>
      );
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^>\s?/, ''));
      const quoteKey = blockIndex++;
      blocks.push(<blockquote key={`block-${quoteKey}`}>{renderInline(quote.join(' '), `quote-${quoteKey}`)}</blockquote>);
      continue;
    }

    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={`block-${blockIndex++}`} />);
      index += 1;
      continue;
    }

    const paragraph: string[] = [line.trim()];
    index += 1;
    while (index < lines.length && !startsBlock(lines, index)) paragraph.push(lines[index++].trim());
    const paragraphKey = blockIndex++;
    blocks.push(<p key={`block-${paragraphKey}`}>{renderInline(paragraph.join(' '), `paragraph-${paragraphKey}`)}</p>);
  }

  return <div className={`markdown-rendered-content ${className}`.trim()}>{blocks}</div>;
};
