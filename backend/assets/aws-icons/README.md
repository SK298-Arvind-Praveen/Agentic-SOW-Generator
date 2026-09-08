# AWS icon catalog

This directory contains a normalized subset of the official AWS Architecture Icons package dated 31 July 2026.

- `services/`: one 64px SVG per architecture service
- `categories/`: one 64px SVG per AWS service category
- `resources/`: one 48px SVG per resource; general icons use the light-background variant
- `groups/`: AWS boundaries and architecture grouping icons for light backgrounds
- `manifest.json`: stable semantic keys, display labels, aliases, categories, and relative asset paths

The full local catalog is retained so uncommon but valid AWS services remain available. Do not place all manifest entries in an LLM prompt. Retrieve a small candidate set from extracted service names and pass only those candidates to architecture generation; resolve the selected key deterministically afterward.

PNG files from the download package were removed because the package already supplied authoritative SVG equivalents. Raster PNGs were not traced or wrapped as fake vectors.
