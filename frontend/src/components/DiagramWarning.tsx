import React from 'react';

const usefulReason = (reason: string) => !/^(overview image review found visual issues;?\s*see diagram diagnostics|image review found visual defects)[.!]?$/i.test(reason.trim());

export default function DiagramWarning({ asset }: { asset: Record<string, unknown> }) {
  const reasons = Array.from(new Set([
    ...(Array.isArray(asset.quality_warnings) ? asset.quality_warnings : []),
    ...(Array.isArray(asset.validation_warnings) ? asset.validation_warnings : []),
    ...(asset.text_alignment && typeof asset.text_alignment === 'object' &&
      'error' in asset.text_alignment ? [(asset.text_alignment as { error: unknown }).error] : []),
  ].filter((reason): reason is string => typeof reason === 'string' && !!reason.trim())));
  const advisories = Array.from(new Set((Array.isArray(asset.layout_advisories) ? asset.layout_advisories : [])
    .filter((reason): reason is string => typeof reason === 'string' && !!reason.trim())));
  if (!reasons.length && !asset.review_warning && asset.status !== 'review_required') {
    if (!advisories.length) return null;
    return <div className="diagram-layout-note" role="note"><details>
      <summary>Layout notes ({advisories.length})</summary>
      <ul>{advisories.map(reason => <li key={reason}>{reason}</li>)}</ul></details></div>;
  }
  if (!reasons.length && typeof asset.diagnostic === 'string') reasons.push(asset.diagnostic);
  const specificReasons = reasons.filter(usefulReason);
  return <div className="diagram-review-warning" role="alert">
    <details><summary><strong>Diagram needs review</strong>{specificReasons.length ? ` (${specificReasons.length})` : ''}</summary>
    <p>{asset.image_base64
      ? 'The available diagram is shown and included in the download. Some generation or validation checks did not succeed.'
      : 'The diagram could not be rendered. Your SOW text is preserved.'}</p>
    {specificReasons.length > 0 && <><span>Reason{specificReasons.length > 1 ? 's' : ''}:</span>
      <ul>{specificReasons.map(reason => <li key={reason}>{reason}</li>)}</ul></>}
    </details>
  </div>;
}
