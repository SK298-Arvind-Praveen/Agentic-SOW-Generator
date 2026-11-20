// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
const { extractInputFields } = require('./aws-client');

// Catalog examples describe one template, not every product variant. Select
// among templates that contain the supplied inputs, using the catalog only
// to resolve ambiguity (for example, shared Cognito tier fields).
function selectTemplate(definition, config, hint) {
  const templates = (definition.templates || []).map(template => ({
    id: typeof template === 'string' ? template : template.id,
    fields: new Set(extractInputFields({ templates: [template] }).map(field => field.id)),
  }));
  if (!templates.length) return { templateId: 'template', incompatible: false };
  const known = new Set(templates.flatMap(template => [...template.fields]));
  const supplied = Object.keys(config).filter(id => known.has(id));
  const compatible = templates.filter(template => supplied.every(id => template.fields.has(id)));
  const candidates = compatible.length ? compatible : templates;
  const selected = candidates.find(template => template.id === hint) || candidates[0];
  return { templateId: selected.id, incompatible: compatible.length === 0 };
}

function catalogForTemplate(entry, templateId) {
  return entry && (!entry.templateId || entry.templateId === templateId) ? entry : undefined;
}

module.exports = { selectTemplate, catalogForTemplate };
