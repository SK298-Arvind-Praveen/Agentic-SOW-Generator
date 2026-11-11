import React from 'react';

export default function DiagramWarning({ asset }: { asset: Record<string, unknown> }) {
  const reasons = Array.from(new Set([
    ...(Array.isArray(asset.quality_warnings) ? asset.quality_warnings : []),
    ...(Array.isArray(asset.validation_warnings) ? asset.validation_warnings : []),
    ...(asset.text_alignment && typeof asset.text_alignment === 'object' &&
      'error' in asset.text_alignment ? [(asset.text_alignment as { error: unknown }).error] : []),
  ].filter((reason): reason is string => typeof reason === 'string' && !!reason.trim())));
  if (!reasons.length && !asset.review_warning && asset.status !== 'review_required') return null;
  if (!reasons.length && typeof asset.diagnostic === 'string') reasons.push(asset.diagnostic);
  return <div className="diagram-review-warning" role="alert">
    <strong>Diagram needs review</strong>
    <p>{asset.image_base64
      ? 'The available diagram is shown and included in the download. Some generation or validation checks did not succeed.'
      : 'The diagram could not be rendered. Your SOW text is preserved.'}</p>
    {reasons.length > 0 && <><span>Reason{reasons.length > 1 ? 's' : ''}:</span>
      <ul>{reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></>}
  </div>;
}
