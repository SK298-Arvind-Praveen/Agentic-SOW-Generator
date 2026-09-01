# WordprocessingML compatibility guideline

This is the formatting contract for generated SOW documents. It targets the
common rendering subset shared by Microsoft Word desktop, Word Online in
SharePoint, LibreOffice pagination, and document-preview interfaces.

## Typography

- Set `DM Sans` explicitly in `w:rFonts` for `ascii`, `hAnsi`, `eastAsia`, and
  `cs`; do not rely on the document theme or font substitution.
- Embed the regular and bold DM Sans OpenType resources and declare them in
  `word/fontTable.xml` and its relationships.
- Body text and every table cell use 11 pt (`w:sz="22"`).
- Heading 1 through Heading 4 use 20 pt (`w:sz="40"`) and bold formatting.
- Apply the font and size to the paragraph style and to generated heading runs.

## Layout

- Use paragraphs, inline drawings (`wp:inline`), and fixed tables for layout.
- Do not use floating or page-relative drawings, VML text boxes, grouped shapes,
  `wp:anchor`, `behindDoc`, or absolute coordinates.
- Preserve the approved `sow_coverpage_template.docx` composition by flattening
  its background artwork, logo, and dynamic labels into one full-page inline
  image. This avoids renderer-specific shape/text-box anchoring while keeping
  the same cover in Word desktop and SharePoint.
- Express page size, margins, header distance, and footer distance explicitly in
  each `w:sectPr`.
- Size the inline A4 cover image to 11.66 inches high so the paragraph mark and
  following section break remain on page 1; a full 11.68-inch image can create a
  renderer-dependent blank page before the TOC.

## Headings and sections

- Use Word heading styles rather than bold Normal paragraphs.
- Emit explicit `w:keepNext` and widow control for headings.
- Do not depend on section breaks to reset list state.
- Use unique bookmarks of no more than 40 characters for TOC targets.

## Lists

- SOW body lists are bullets only. Ordered Markdown is normalised to bullets.
- Use one dedicated bullet abstract numbering definition and one stable `numId`.
- Set `w:ilvl` and `w:numId` explicitly on every list paragraph.
- Do not create decimal numbering definitions or reuse numbering imported from
  the cover template.

## Tables

- Use `w:tblLayout w:type="fixed"`, explicit `w:tblW`, `w:tblGrid`, and `w:tcW`.
- Set cell margins, borders, vertical alignment, and paragraph alignment
  explicitly.
- Assign the named `SOW Table` style, based on `Table Grid`, with a `firstRow`
  style rule for purple shading and bold white text. Keep equivalent direct cell
  formatting as a fallback.
- Use `w:shd` with `w:val="clear"`, `w:color="auto"`, and an explicit fill.
- Mark header rows with `w:tblHeader` and all rows with `w:cantSplit`.
- Put 11 pt DM Sans direct formatting on every table run.
- Use semantic column-width profiles for known schemas, and reserve at least
  2,450 DXA for `Module/Area` so words do not wrap one character per line.
- Insert a 5 pt spacing paragraph after each table and at least 8 pt after each
  diagram or diagram-edit link.

## Alignment

- Justify narrative body paragraphs (`w:jc w:val="both"`).
- Keep headings, bullets, table-cell text, and table headers left-aligned.
- Render unknown standalone values as blank editable fields/cells. Do not print
  `Not specified`, `Not provided`, `TBD`, `N/A`, or `To be confirmed` as filler.

## Table of contents and fields

- Use `PAGEREF ... \\h` fields pointing to real bookmarks.
- Keep fields dirty and set package-level `w:updateFields` to true when no
  pagination engine is available. Viewers may calculate those fields on open,
  but cached page numbers are the only renderer-independent presentation.
- Optionally calculate page references after final pagination and store numeric
  cached results in the field result runs. This optimisation must never be a
  document-generation requirement.
- Mark precomputed PAGEREF fields as not dirty.
- Set package-level `w:updateFields` to false only after caching. Desktop Word can
  otherwise replace valid cached results before its layout pass and show page 1
  for every entry.
- Prefer an existing Microsoft Word installation on Windows; use the free
  LibreOffice engine as an optional fallback. Neither belongs in Python
  `requirements.txt`, because both are operating-system applications.
- Keep `PAGE` and `NUMPAGES` footer fields dynamic; they do not require the
  package-wide update-on-open flag.

## Validation

For every representative generated DOCX, inspect the package and assert:

- no `wp:anchor`, `behindDoc`, `relativeFrom="page"`, or VML text boxes;
- no decimal list numbering definition;
- all body/table runs resolve to DM Sans 11 pt;
- all heading styles and generated heading runs resolve to DM Sans 20 pt;
- every PAGEREF target has a matching bookmark and numeric cached result;
- `w:updateFields` is true for dynamic fields, or false after optional caching;
- each selected static section appears once, particularly `About ShellKode`.
