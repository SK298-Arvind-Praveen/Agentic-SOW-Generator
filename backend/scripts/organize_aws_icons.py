"""Normalize the official AWS Architecture Icons package for diagram generation.

Keeps one authoritative SVG per semantic icon:
- 64px architecture service and category SVGs
- 48px resource SVGs, using Light variants for white document backgrounds
- non-Dark group/boundary SVGs

The operation stages and validates the complete replacement before removing the
download-package directories.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1] / "assets" / "aws-icons"
SOURCE_DIRS = {
    "groups": ROOT / "Architecture-Group-Icons_07312026",
    "services": ROOT / "Architecture-Service-Icons_07312026",
    "categories": ROOT / "Category-Icons_07312026",
    "resources": ROOT / "Resource-Icons_07312026",
}
EXPECTED_COUNTS = {"groups": 13, "services": 305, "categories": 26, "resources": 466}
SINGULAR_KIND = {"groups": "group", "services": "service", "categories": "category", "resources": "resource"}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def clean_name(stem: str) -> str:
    value = re.sub(r"^(?:Arch_|Arch-Category_|Res_)", "", stem)
    value = re.sub(r"_(?:16|32|48|64)(?:_(?:Light|Dark))?$", "", value)
    return value


def category_name(value: str) -> str:
    return re.sub(r"^(?:Arch_|Res_)", "", value).replace("IoT", "Internet-of-Things")


def label(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("-", " ").replace("_", " ")).strip()


def add_icon(stage: Path, entries: list[dict], kind: str, category: str, source: Path) -> None:
    semantic_name = clean_name(source.stem)
    category_slug = slug(category)
    name_slug = slug(semantic_name)
    destination = stage / kind / category_slug / f"{name_slug}.svg"
    if destination.exists():
        raise RuntimeError(f"Duplicate normalized destination: {destination}")
    ElementTree.parse(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    display_label = label(semantic_name)
    singular_kind = SINGULAR_KIND[kind]
    entries.append({
        "key": f"aws.{singular_kind}.{category_slug}.{name_slug}",
        "label": display_label,
        "kind": singular_kind,
        "category": category_slug,
        "path": destination.relative_to(stage).as_posix(),
        "aliases": sorted({
            name_slug,
            display_label.casefold(),
            re.sub(r"^(?:amazon|aws)\s+", "", display_label.casefold()),
        }),
    })


def collect(stage: Path) -> list[dict]:
    entries: list[dict] = []

    for source in sorted(SOURCE_DIRS["groups"].glob("*.svg")):
        if source.stem.endswith("_Dark"):
            continue
        add_icon(stage, entries, "groups", "boundaries", source)

    for category in sorted(SOURCE_DIRS["services"].iterdir()):
        if not category.is_dir():
            continue
        for source in sorted((category / "64").glob("*.svg")):
            add_icon(stage, entries, "services", category_name(category.name), source)

    category_64 = SOURCE_DIRS["categories"] / "Arch-Category_64"
    for source in sorted(category_64.glob("*.svg")):
        add_icon(stage, entries, "categories", "service-categories", source)

    for category in sorted(SOURCE_DIRS["resources"].iterdir()):
        if not category.is_dir():
            continue
        if category.name == "Res_General-Icons":
            sources = sorted((category / "Res_48_Light").glob("*.svg"))
        else:
            sources = sorted(category.glob("*.svg"))
        for source in sources:
            add_icon(stage, entries, "resources", category_name(category.name), source)

    return entries


def main() -> None:
    root = ROOT.resolve()
    expected_root = (Path(__file__).resolve().parents[1] / "assets" / "aws-icons").resolve()
    if root != expected_root:
        raise RuntimeError(f"Unexpected AWS icon root: {root}")
    if not all(path.is_dir() for path in SOURCE_DIRS.values()):
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Incomplete AWS icon source root: {root}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("icons", []):
            if entry.get("kind") == "categorie":
                entry["kind"] = "category"
                entry["key"] = str(entry.get("key", "")).replace("aws.categorie.", "aws.category.", 1)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"root": str(root), "total": manifest.get("count", 0), "status": "manifest-validated"}))
        return

    stage = root / ".organized-stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    try:
        entries = collect(stage)
        counts = {
            kind: sum(entry["kind"] == SINGULAR_KIND[kind] for entry in entries)
            for kind in EXPECTED_COUNTS
        }
        if counts != EXPECTED_COUNTS:
            raise RuntimeError(f"Icon inventory mismatch: expected {EXPECTED_COUNTS}, got {counts}")
        keys = [entry["key"] for entry in entries]
        if len(keys) != len(set(keys)):
            raise RuntimeError("Normalized manifest contains duplicate keys")

        manifest = {
            "source": "Official AWS Architecture Icons package, 31 July 2026",
            "policy": "Full local catalog; retrieve a relevant shortlist for model context.",
            "count": len(entries),
            "counts": counts,
            "icons": sorted(entries, key=lambda item: item["key"]),
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        for source in SOURCE_DIRS.values():
            shutil.rmtree(source)
        for item in list(stage.iterdir()):
            shutil.move(str(item), root / item.name)
        stage.rmdir()
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise

    print(json.dumps({"root": str(root), "total": len(entries), "counts": counts}))


if __name__ == "__main__":
    main()
