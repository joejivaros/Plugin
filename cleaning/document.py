# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Clean-up of what the document holds besides geometry: identical
materials, unused materials and layers, empty groups.

These always look at the whole document: a material or a layer is
"unused" only if nothing anywhere wears it. The traversal is IngeTrazo's
own (``core.purge``), which descends into nested groups and the component
definitions kept in the file.
"""
from __future__ import annotations

import json
import re

#: A name the material registry made unique: "Wood (2)".
_SUFFIXED = re.compile(r".+ \(\d+\)$")


def document_groups(scene) -> list:
    """Top-level groups plus the kept component definitions."""
    return (list(getattr(scene, "groups", None) or ())
            + list(getattr(scene, "kept_components", None) or ()))


def all_meshes(scene) -> list:
    """Every distinct mesh of the document, the one being edited included
    (a component instance open for editing works on a copy)."""
    from core.purge import iter_meshes
    out = list(iter_meshes(scene))
    if all(m is not scene.mesh for m in out):
        out.append(scene.mesh)
    return out


# ---- Identical materials -----------------------------------------------------

def _recipe(material) -> tuple:
    texture = material.texture
    return (tuple(material.color) if material.color is not None else None,
            json.dumps(texture, sort_keys=True, default=str)
            if texture else None,
            material.opacity, material.finish)


def duplicate_materials(scene) -> dict[str, str]:
    """``{duplicate name: kept name}`` for materials with the same recipe
    (colour, texture, opacity and finish). The kept one is the first in
    the registry whose name was not made unique by a " (n)" suffix."""
    by_recipe: dict[tuple, list[str]] = {}
    for name, material in (getattr(scene, "materials", None) or {}).items():
        by_recipe.setdefault(_recipe(material), []).append(name)
    mapping: dict[str, str] = {}
    for names in by_recipe.values():
        if len(names) < 2:
            continue
        keep = next((n for n in names if not _SUFFIXED.match(n)), names[0])
        for name in names:
            if name != keep:
                mapping[name] = keep
    return mapping


def meshes_wearing(scene, names) -> list:
    """The meshes with a face whose front or back wears one of ``names``."""
    names = set(names)
    out = []
    for mesh in all_meshes(scene):
        for f in mesh.faces:
            back = f.attrs.get("back")
            if (f.attrs.get("mat") in names
                    or (isinstance(back, dict) and back.get("mat") in names)):
                out.append(mesh)
                break
    return out


def merge_materials(scene, mapping: dict[str, str]) -> int:
    """Repoint every face and group painted with a duplicate to the kept
    material, then drop the duplicates from the registry. The baked
    colours and textures are identical by definition, so nothing changes
    on screen. Returns how many materials went."""
    if not mapping:
        return 0
    from core.group import iter_placements
    for mesh in all_meshes(scene):
        for f in mesh.faces:
            name = f.attrs.get("mat")
            if name in mapping:
                f.attrs["mat"] = mapping[name]
            back = f.attrs.get("back")
            if isinstance(back, dict) and back.get("mat") in mapping:
                f.attrs["back"] = {**back, "mat": mapping[back["mat"]]}
    for top in document_groups(scene):
        for g, _m in iter_placements(top):
            paint = getattr(g, "material", None)
            if paint and paint.get("mat") in mapping:
                g.material = {**paint, "mat": mapping[paint["mat"]]}
    for name in mapping:
        scene.materials.pop(name, None)
    return len(mapping)


# ---- Unused materials and layers ----------------------------------------------

def purge_unused_materials(scene) -> int:
    from core.purge import unused_materials
    names = unused_materials(scene)
    for name in names:
        scene.materials.pop(name, None)
    return len(names)


def purge_unused_layers(scene) -> int:
    """Remove the layers nothing carries. Layers a saved scene hides stay:
    the scene was built around them (``core.purge``)."""
    from core.purge import unused_layers
    doomed = unused_layers(scene)
    for layer in doomed:
        if layer in scene.layers:
            scene.layers.remove(layer)
    return len(doomed)


# ---- Empty groups ----------------------------------------------------------------

def _is_empty(group) -> bool:
    mesh = group.mesh
    if mesh.faces or mesh.edges:
        return False
    return all(_is_empty(c) for c in getattr(group, "children", None) or ())


def _open_groups(scene) -> set:
    """The groups open for editing, innermost and outer ones: never erased
    from under the user."""
    out = {id(e.get("group")) for e in getattr(scene, "_edit_stack", None) or ()
           if isinstance(e, dict)}
    if getattr(scene, "edit_group", None) is not None:
        out.add(id(scene.edit_group))
    return out


def empty_groups(scene) -> list[tuple[list, object]]:
    """``(owner list, group)`` for every outermost group with nothing in
    it, nested ones included. Locked and open groups are kept, and so are
    kept component definitions (the user asked to keep them)."""
    keep = _open_groups(scene)
    found: list[tuple[list, object]] = []

    def walk(owner) -> None:
        for g in owner:
            if getattr(g, "locked", False) or id(g) in keep:
                continue
            if _is_empty(g):
                found.append((owner, g))
            elif getattr(g, "children", None):
                walk(g.children)

    walk(getattr(scene, "groups", None) or [])
    return found


def erase_groups(found) -> list[tuple[list, int, object]]:
    """Remove the groups ``found`` by :func:`empty_groups`; returns
    ``(owner, index, group)`` records, in removal order, for undo."""
    records = []
    for owner, g in found:
        if g in owner:
            index = owner.index(g)
            owner.pop(index)
            records.append((owner, index, g))
    return records
