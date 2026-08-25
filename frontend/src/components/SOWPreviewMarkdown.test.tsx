import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import {
  MarkdownRenderer,
  parsePreviewContentMarkdown,
  serializePreviewContent,
} from './SOWPreviewMarkdown';

describe('SOW preview Markdown', () => {
  it('renders headings, emphasis, lists, and tables instead of raw Markdown', () => {
    const markdown = `### 1.1 Organisation Profile

Shellkode provides **AWS architecture** and *delivery support*.

- Secure delivery
- Auditable controls

| Field | Value |
|---|---|
| Region | Mumbai |`;

    const { container } = render(<MarkdownRenderer markdown={markdown} />);

    expect(screen.getByRole('heading', { name: '1.1 Organisation Profile' })).toBeInTheDocument();
    expect(screen.getByText('AWS architecture').tagName).toBe('STRONG');
    expect(screen.getByText('delivery support').tagName).toBe('EM');
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(container).not.toHaveTextContent('###');
    expect(container).not.toHaveTextContent('**AWS architecture**');
  });

  it('serialises the body into one document and parses reviewer edits back to section keys', () => {
    const content = {
      cover_page: 'System-managed cover',
      toc_structure: 'System-managed TOC',
      about_shellkode: 'Original profile.',
      aws_pricing: '| Item | Basis |\n|---|---|\n| Storage | Open |',
      architecture_diagram_assets: [{ title: 'Diagram' }],
      generation_quality_summary: 'Internal quality notes',
    };
    const serialised = serializePreviewContent(content);

    expect(serialised.sections.map(section => section.key)).toEqual(['about_shellkode', 'aws_pricing']);
    expect(serialised.markdown).toContain('## About Shellkode');
    expect(serialised.markdown).not.toContain('System-managed TOC');
    expect(serialised.markdown).not.toContain('Internal quality notes');

    const edited = serialised.markdown.replace('Original profile.', 'Updated reviewer profile.');
    expect(parsePreviewContentMarkdown(edited, serialised.sections)).toEqual({
      about_shellkode: 'Updated reviewer profile.',
      aws_pricing: '| Item | Basis |\n|---|---|\n| Storage | Open |',
    });
  });

  it('rejects a document when a generated section heading is removed', () => {
    const serialised = serializePreviewContent({
      about_shellkode: 'Profile',
      aws_pricing: 'Pricing',
    });
    const invalid = serialised.markdown.replace('## AWS Pricing', '### AWS Pricing');
    expect(() => parsePreviewContentMarkdown(invalid, serialised.sections)).toThrow('missing: AWS Pricing');
  });
});

