# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The clean-up as one undoable command, its options and its scope.

:class:`CleanCommand` snapshots every mesh it is going to touch
(``Mesh.capture_state``, which keeps object identity), and the material
registry, the layer list and the groups it erases, so undo and redo put
back exactly what was there — the approach of IngeTrazo's own Solid
Inspector repair. :func:`preview` runs the same command and undoes it,
so the counts it shows can never disagree with a real run.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields

from core.history import Command, CommandRejected

from . import document, geometry

SCOPES = ("model", "context", "selection")

#: The report's keys, in the order the operations run.
REPORT_KEYS = ("repaired_faces", "degenerate_faces", "zero_edges",
               "duplicate_faces", "coplanar_faces", "stray_edges",
               "split_edges", "loose_vertices",
               "duplicate_materials", "unused_materials", "unused_layers",
               "empty_groups")


@dataclass
class Options:
    """What to clean. Every flag defaults to on."""

    degenerate_faces: bool = True
    duplicate_faces: bool = True
    coplanar_faces: bool = True
    coplanar_angle: float = 0.05            # degrees
    coplanar_same_material: bool = True
    stray_edges: bool = True
    split_edges: bool = True
    duplicate_materials: bool = True
    unused_materials: bool = True
    unused_layers: bool = True
    empty_groups: bool = True
    scope: str = "model"

    GEOMETRY = ("degenerate_faces", "duplicate_faces", "coplanar_faces",
                "stray_edges", "split_edges")
    DOCUMENT = ("duplicate_materials", "unused_materials", "unused_layers",
                "empty_groups")

    def any_geometry(self) -> bool:
        return any(getattr(self, k) for k in self.GEOMETRY)

    def any(self) -> bool:
        return self.any_geometry() or any(getattr(self, k)
                                          for k in self.DOCUMENT)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw) -> "Options":
        """Options from saved data; anything of the wrong type or out of
        range keeps its default."""
        out = cls()
        if not isinstance(raw, dict):
            return out
        for f in fields(cls):
            value = raw.get(f.name)
            if f.name == "scope":
                if value in SCOPES:
                    out.scope = value
            elif f.name == "coplanar_angle":
                if (isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(value)
                        and 0.0 <= value <= geometry.MAX_ANGLE_DEG):
                    out.coplanar_angle = float(value)
            elif isinstance(value, bool):
                setattr(out, f.name, value)
        return out


# ---- Scope -------------------------------------------------------------------------

def _locked_meshes(scene) -> set:
    """Meshes of locked groups (or inside one): left untouched."""
    out: set = set()

    def walk(groups, locked: bool) -> None:
        for g in groups or ():
            lk = locked or bool(getattr(g, "locked", False))
            if lk:
                out.add(id(g.mesh))
            walk(getattr(g, "children", None), lk)

    walk(document.document_groups(scene), False)
    return out


def targets(scene, scope: str) -> list[tuple]:
    """``(mesh, faces or None, edges or None)`` for each mesh to clean.

    ``model``: the loose geometry and every group (not while a group is
    open: the edited copy and its definition would disagree);
    ``context``: what is being edited now; ``selection``: the selected
    groups whole, and the selected loose faces and edges."""
    from core.group import Group, iter_placements
    from core.mesh import Edge, Face
    if scope == "context":
        return [(scene.mesh, None, None)]
    locked = _locked_meshes(scene)
    seen: set = set()
    out: list[tuple] = []

    def add(mesh, faces=None, edges=None) -> None:
        if mesh is None or id(mesh) in seen or id(mesh) in locked:
            return
        seen.add(id(mesh))
        out.append((mesh, faces, edges))

    if scope == "model":
        if getattr(scene, "edit_group", None) is not None:
            raise CommandRejected("close the group being edited first")
        from core.purge import iter_meshes
        for mesh in iter_meshes(scene):
            add(mesh)
        return out
    mesh = scene.mesh
    faces = [s for s in scene.selection if isinstance(s, Face)]
    edges = [s for s in scene.selection if isinstance(s, Edge)]
    if faces or edges:
        edge_set = {id(e): e for e in edges}
        for f in faces:
            for e in geometry.face_edges(mesh, f):
                edge_set[id(e)] = e
        out.append((mesh, faces, list(edge_set.values())))
        seen.add(id(mesh))
    for g in [s for s in scene.selection if isinstance(s, Group)]:
        if getattr(g, "locked", False):
            continue
        for pg, _m in iter_placements(g):
            add(pg.mesh)
    return out


# ---- The command -------------------------------------------------------------------

def _clean_mesh(mesh, faces, edges, opts: Options, report: dict) -> None:
    if opts.degenerate_faces:
        report["repaired_faces"] += geometry.repair_repeated_corners(mesh, faces)
        report["degenerate_faces"] += geometry.erase_degenerate_faces(mesh, faces)
        report["zero_edges"] += geometry.erase_zero_length_edges(mesh, edges)
    if opts.duplicate_faces:
        report["duplicate_faces"] += geometry.erase_duplicate_faces(mesh, faces)
    if opts.coplanar_faces:
        report["coplanar_faces"] += geometry.merge_coplanar_faces(
            mesh, opts.coplanar_angle, opts.coplanar_same_material, faces)
    if opts.stray_edges:
        report["stray_edges"] += geometry.erase_stray_edges(mesh, edges)
    if opts.split_edges:
        report["split_edges"] += geometry.repair_split_edges(mesh, edges)
    report["loose_vertices"] += mesh.prune_orphan_vertices()


class CleanCommand(Command):
    """Run the chosen clean-up as ONE undo step (snapshot undo)."""

    def __init__(self, options: Options) -> None:
        self.options = options
        self.report: dict = {k: 0 for k in REPORT_KEYS}
        self._meshes: list = []
        self._before: list = []
        self._after: list = []
        self._doc_before: dict | None = None
        self._doc_after: dict | None = None
        self._erased: list = []          # (owner, index, group)

    @property
    def total(self) -> int:
        return sum(self.report.values())

    # ---- document state -------------------------------------------------------
    @staticmethod
    def _doc_state(scene) -> dict:
        from core.group import iter_placements
        paints = []
        for top in document.document_groups(scene):
            for g, _m in iter_placements(top):
                paints.append((g, getattr(g, "material", None)))
        return {"materials": dict(scene.materials),
                "layers": list(scene.layers), "paints": paints}

    @staticmethod
    def _put_doc(scene, state: dict) -> None:
        scene.materials.clear()
        scene.materials.update(state["materials"])
        scene.layers[:] = state["layers"]
        for g, paint in state["paints"]:
            g.material = paint

    # ---- do / undo ---------------------------------------------------------------
    def do(self, scene) -> None:
        if self._doc_after is not None:          # redo
            self._restore(scene, self._after, self._doc_after)
            for owner, _index, g in self._erased:
                if g in owner:
                    owner.remove(g)
            self._touch(scene)
            return
        opts = self.options
        work = targets(scene, opts.scope) if opts.any_geometry() else []
        mapping = (document.duplicate_materials(scene)
                   if opts.duplicate_materials else {})
        self._meshes = [m for m, _f, _e in work]
        for mesh in document.meshes_wearing(scene, mapping):
            if all(mesh is not m for m in self._meshes):
                self._meshes.append(mesh)
        self._before = [m.capture_state() for m in self._meshes]
        self._doc_before = self._doc_state(scene)
        try:
            self._run(scene, work, mapping)
        except BaseException:
            self._restore(scene, self._before, self._doc_before)
            self._unerase()
            raise
        if not self.total:
            self._restore(scene, self._before, self._doc_before)
            raise CommandRejected("nothing to clean")
        self._after = [m.capture_state() for m in self._meshes]
        self._doc_after = self._doc_state(scene)
        self._touch(scene)

    def _run(self, scene, work, mapping) -> None:
        opts, report = self.options, self.report
        for mesh, faces, edges in work:
            _clean_mesh(mesh, faces, edges, opts, report)
            # Never hand back a model IngeTrazo cannot save: raising here
            # rolls the whole clean-up back.
            geometry.check_loops(mesh)
        if mapping:
            report["duplicate_materials"] = document.merge_materials(
                scene, mapping)
        if opts.unused_materials:
            report["unused_materials"] = document.purge_unused_materials(scene)
        if opts.unused_layers:
            report["unused_layers"] = document.purge_unused_layers(scene)
        if opts.empty_groups:
            self._erased = document.erase_groups(document.empty_groups(scene))
            report["empty_groups"] = len(self._erased)
            for _owner, _index, g in self._erased:
                scene.selection.discard(g)

    def undo(self, scene) -> None:
        if self._doc_before is None:
            return
        self._restore(scene, self._before, self._doc_before)
        self._unerase()
        self._touch(scene)

    def _unerase(self) -> None:
        for owner, index, g in reversed(self._erased):
            if g not in owner:
                owner.insert(min(index, len(owner)), g)

    def _restore(self, scene, snaps, doc_state) -> None:
        for mesh, snap in zip(self._meshes, snaps):
            mesh.restore_state(snap)
            mesh._winding_rev = getattr(mesh, "_winding_rev", 0) + 1
        self._put_doc(scene, doc_state)

    @staticmethod
    def _touch(scene) -> None:
        # Edges and faces the clean-up erased must not stay selected.
        alive = set(scene.mesh.edges) | set(scene.mesh.faces)
        for s in [s for s in scene.selection
                  if (hasattr(s, "v0") or hasattr(s, "loop"))
                  and s not in alive]:
            scene.selection.discard(s)
        from core.history import _dirty_group_chunks
        _dirty_group_chunks(scene)
        scene.version += 1


def preview(scene, options: Options) -> dict:
    """What a clean-up with ``options`` would remove, without changing the
    model: the real command, run and undone. ``scene.version`` and the
    selection come back too, so the document does not turn "modified".
    Raises :class:`CommandRejected` like the command (a group is open)."""
    version = scene.version
    selection = set(scene.selection)
    cmd = CleanCommand(options)
    try:
        cmd.do(scene)
    except CommandRejected as exc:
        if str(exc) == "nothing to clean":
            return dict(cmd.report)
        raise
    finally:
        cmd.undo(scene)
        scene.selection.clear()
        scene.selection.update(selection)
        scene.version = version
    return dict(cmd.report)
