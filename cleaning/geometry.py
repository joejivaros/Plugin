# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""Clean-up operations on one :class:`core.mesh.Mesh`.

Each function changes the mesh in place and returns how many items it
removed. None of them keeps undo records: :mod:`.command` snapshots every
mesh it touches before running them, as IngeTrazo's own repairs do.

``faces`` / ``edges``, when given, restrict an operation to those entities
(the Selection scope); ``None`` means the whole mesh.
"""
from __future__ import annotations

import math

from PySide6.QtGui import QVector3D

#: Face attributes two faces must share to become one face, always: a layer
#: and a BIM tag are information a merge must not lose.
IDENTITY_KEYS = ("layer", "ifc")
#: The paint of a face (``core.mesh.PAINT_KEYS`` plus its back side).
PAINT_KEYS = ("color", "mat", "texture", "opacity", "back")

#: A face whose area is below this fraction of its squared perimeter has
#: no surface to speak of (a 1 m sliver under a micrometre wide).
DEGENERATE_RATIO = 1e-9
#: The smallest coplanar angle used, so a tolerance of 0 still merges faces
#: whose normals differ by float noise only.
MIN_ANGLE_DEG = 0.001
MAX_ANGLE_DEG = 5.0


def _edge_alive(edge) -> bool:
    return edge in edge.v0.edges


def remove_edges(mesh, edges) -> int:
    """``Mesh.remove_edge`` for many edges at once: one pass over the
    mesh's edge list instead of one per edge (quadratic on big meshes)."""
    doomed = {id(e): e for e in edges if _edge_alive(e)}
    if not doomed:
        return 0
    if len(doomed) < 64:
        for e in doomed.values():
            mesh.remove_edge(e)
        return len(doomed)
    for e in doomed.values():
        e.v0.edges.discard(e)
        e.v1.edges.discard(e)
    mesh.edges[:] = [e for e in mesh.edges if id(e) not in doomed]
    # The same signals the mesh primitives give the viewport's caches.
    mesh._chunk_dirty = True
    mesh._mut_serial = getattr(mesh, "_mut_serial", 0) + 1
    return len(doomed)


def _loop_pairs(face):
    for loop in (face.loop, *face.hole_loops):
        n = len(loop)
        for i in range(n):
            yield loop[i], loop[(i + 1) % n]


def face_edges(mesh, face) -> list:
    """The edges bounding ``face`` (outer loop and holes)."""
    out = []
    for a, b in _loop_pairs(face):
        e = mesh.find_edge(a, b)
        if e is not None:
            out.append(e)
    return out


# ---- Degenerate faces --------------------------------------------------------

def is_degenerate(face) -> bool:
    """A face with fewer than three distinct corners, or no area."""
    if len({id(v) for v in face.loop}) < 3:
        return True
    perimeter = sum((b.position - a.position).length()
                    for a, b in zip(face.loop, face.loop[1:] + face.loop[:1]))
    return face.area() <= DEGENERATE_RATIO * perimeter * perimeter


def _edges_around(face) -> list:
    """Every edge at a corner of ``face`` (a superset of its sides, which
    also reaches the self-loop edges a repeated corner made)."""
    seen: dict = {}
    for loop in (face.loop, *face.hole_loops):
        for v in loop:
            for e in v.edges:
                seen[id(e)] = e
    return list(seen.values())


def _forget_face(face, edges) -> None:
    """Take ``face`` off the radial lists of ``edges``, every occurrence:
    ``Mesh.remove_face`` misses some on a loop that repeats a corner."""
    for e in edges:
        if face in e.faces:
            e.faces[:] = [f for f in e.faces if f is not face]


def erase_degenerate_faces(mesh, faces=None) -> int:
    """Remove faces with no surface, and the edges only they used."""
    pool = list(mesh.faces) if faces is None else list(faces)
    alive = set(mesh.faces)
    doomed = [f for f in pool if f in alive and is_degenerate(f)]
    bare = []
    for face in doomed:
        edges = _edges_around(face)
        sides = {id(e) for e in face_edges(mesh, face)}
        mesh.remove_face(face)
        _forget_face(face, edges)
        bare += [e for e in edges if id(e) in sides and not e.faces]
    remove_edges(mesh, bare)
    return len(doomed)


def erase_zero_length_edges(mesh, edges=None) -> int:
    """Remove edges that start and end on the same vertex. No face side
    can use one (a repaired loop no longer does), so any face still listed
    on it is dropped from its list first."""
    pool = list(mesh.edges) if edges is None else list(edges)
    doomed = [e for e in pool if e.v0 is e.v1 and _edge_alive(e)]
    for e in doomed:
        e.faces.clear()
    return remove_edges(mesh, doomed)


def check_loops(mesh) -> None:
    """Raise ``ValueError`` if a face's outline or a hole has fewer than
    three points: IngeTrazo 0.5.9's ``.igz`` writer fails on such a face
    ("list index out of range")."""
    for f in mesh.faces:
        if len(f.loop) < 3 or any(len(h) < 3 for h in f.hole_loops):
            raise ValueError("a face was left with fewer than three corners")


def _without_repeats(loop: list) -> list:
    """``loop`` without a corner that repeats the one before it."""
    return [v for k, v in enumerate(loop) if v is not loop[k - 1]] or loop[:1]


def _drop_empty_holes(mesh, face) -> list:
    """Remove the holes of ``face`` with fewer than three distinct corners
    (no area: ``[a, b]`` or ``[a, a, b, b]``). IngeTrazo 0.5.9 cannot save
    a hole of fewer than three points. Returns the edges that bounded only
    such a hole and now bound nothing."""
    empty = [h for h in face.hole_loops if len({id(v) for v in h}) < 3]
    if not empty:
        return []
    hole_edges = {}
    for h in empty:
        for i in range(len(h)):
            e = mesh.find_edge(h[i], h[(i + 1) % len(h)])
            if e is not None:
                hole_edges[id(e)] = e
    face.hole_loops = [h for h in face.hole_loops if not any(h is x for x in empty)]
    sides = {id(e) for e in face_edges(mesh, face)}
    bare = []
    for e in hole_edges.values():
        if id(e) not in sides:
            _forget_face(face, [e])
            if not e.faces:
                bare.append(e)
    return bare


def repair_repeated_corners(mesh, faces=None) -> int:
    """Drop the corners a face loop lists twice in a row (``[a, a, b, c]``,
    a triangle some importers store as a quad), and the holes that have no
    area left. The face keeps its shape, but IngeTrazo cannot merge such a
    face with its neighbour (nor save a two-point hole) until the repeat is
    gone. Returns how many faces changed."""
    pool = list(mesh.faces) if faces is None else list(faces)
    alive = set(mesh.faces)
    fixed = 0
    bare: list = []
    for f in pool:
        if f not in alive:
            continue
        changed = False
        for loop in (f.loop, *f.hole_loops):
            clean = _without_repeats(loop)
            if len(clean) != len(loop):
                loop[:] = clean
                changed = True
        empty = any(len({id(v) for v in h}) < 3 for h in f.hole_loops)
        if not (changed or empty):
            continue
        fixed += 1
        # The repeat was a side from a corner to itself: its self-loop edge
        # no longer bounds this face (found before an empty hole goes).
        loops = [e for e in _edges_around(f) if e.v0 is e.v1]
        bare += _drop_empty_holes(mesh, f)
        _forget_face(f, loops)
    remove_edges(mesh, bare)
    if fixed:
        # Loops edited in place bypass the mesh primitives: say so to the
        # viewport's caches as the primitives do.
        mesh._chunk_dirty = True
        mesh._mut_serial = getattr(mesh, "_mut_serial", 0) + 1
    return fixed


# ---- Duplicate faces ---------------------------------------------------------

def erase_duplicate_faces(mesh, faces=None) -> int:
    """Remove faces lying on the same outer edge cycle as another face.

    The same rule as ``Mesh.dedupe_faces``: the face with more holes is
    kept (it carries the subdivision), and paint goes to the survivor when
    it has none of its own."""
    pool = list(mesh.faces) if faces is None else list(faces)
    alive = set(mesh.faces)
    seen: dict = {}
    removed = 0
    for f in pool:
        if f not in alive:
            continue
        sig = frozenset(frozenset((id(a), id(b))) for a, b in
                        zip(f.loop, f.loop[1:] + f.loop[:1]))
        other = seen.get(sig)
        if other is None:
            seen[sig] = f
            continue
        drop, keep = ((other, f) if len(f.hole_loops) > len(other.hole_loops)
                      else (f, other))
        if drop.attrs and not keep.attrs:
            keep.attrs = dict(drop.attrs)
        mesh.remove_face(drop)
        alive.discard(drop)
        seen[sig] = keep
        removed += 1
    return removed


# ---- Coplanar faces ----------------------------------------------------------

def same_attrs(a, b, keys) -> bool:
    return all(a.attrs.get(k) == b.attrs.get(k) for k in keys)


def mergeable(a, b, cos_tol: float, same_material: bool,
              normals: dict | None = None) -> bool:
    """Whether two faces sharing an edge can become one face: same layer,
    BIM tag and interior mark, the same paint unless ``same_material`` is
    off, and the same plane and side (normals within the tolerance).
    ``normals`` caches ``Face.normal()`` for a whole pass."""
    if a is b or a.interior != b.interior:
        return False
    if not same_attrs(a, b, IDENTITY_KEYS):
        return False
    if same_material and not same_attrs(a, b, PAINT_KEYS):
        return False
    if normals is None:
        normals = {}
    for f in (a, b):
        if f not in normals:
            normals[f] = f.normal()
    return QVector3D.dotProduct(normals[a], normals[b]) >= cos_tol


def _shared_edges_simple(mesh, a, b) -> bool:
    """Every edge ``a`` and ``b`` share borders only them, so dissolving
    them all cannot cut into a third face."""
    b_edges = set(map(id, face_edges(mesh, b)))
    return all(len(e.faces) == 2 for e in face_edges(mesh, a)
               if id(e) in b_edges)


def merge_coplanar_faces(mesh, max_angle_deg: float = 0.05,
                         same_material: bool = True, faces=None) -> int:
    """Merge faces that share an edge and lie in one plane. Returns how
    many faces went (one per merge)."""
    angle = min(max(float(max_angle_deg), MIN_ANGLE_DEG), MAX_ANGLE_DEG)
    cos_tol = math.cos(math.radians(angle))
    allowed = None if faces is None else set(faces)
    stack = [e for e in mesh.edges if len(e.faces) == 2]
    normals: dict = {}
    merges = 0
    while stack:
        edge = stack.pop()
        if not _edge_alive(edge) or len(edge.faces) != 2:
            continue
        a, b = edge.faces
        if allowed is not None and (a not in allowed or b not in allowed):
            continue
        if not mergeable(a, b, cos_tol, same_material, normals):
            continue
        interior = a.interior
        merged = mesh.dissolve_edge(edge)
        if merged is None and _shared_edges_simple(mesh, a, b):
            try:
                record = mesh.dissolve_coplanar_pair(a, b)
            except IndexError:
                # Two faces whose union has no outline (IngeTrazo 0.5.9
                # indexes the empty list before changing anything).
                record = None
            merged = record["merged"] if record else None
        if merged is None:
            continue
        merged.interior = interior
        merges += 1
        if allowed is not None:
            allowed.add(merged)
        stack.extend(e for e in face_edges(mesh, merged) if len(e.faces) == 2)
    return merges


# ---- Stray edges -------------------------------------------------------------

def erase_stray_edges(mesh, edges=None) -> int:
    """Remove edges that border no face.

    A mesh with no face at all is left alone: it is a drawing made of
    lines (a plan, a profile waiting for Follow Me), not litter."""
    if not mesh.faces:
        return 0
    pool = list(mesh.edges) if edges is None else list(edges)
    return remove_edges(mesh, [e for e in pool if not e.faces])


# ---- Split edges -------------------------------------------------------------

def repair_split_edges(mesh, edges=None) -> int:
    """Join collinear pieces of a line back into one edge (IngeTrazo's own
    Join Segments rules: same faces, same flags, not part of a curve).
    Returns how many intermediate points went.

    Repeated until nothing joins: a join can leave the next point of the
    line joinable (its neighbour edge is a new object)."""
    total = 0
    pool = None if edges is None else list(edges)
    for _round in range(8):
        joined, pool = _join_once(mesh, pool)
        total += joined
        if not joined:
            break
    return total


def _join_once(mesh, edges):
    """One Join Segments pass; returns (points removed, edges now)."""
    from core.edits import join_edges
    pool = mesh.edges if edges is None else edges
    picked = {id(e) for e in pool}
    # Only the edges at a point Join Segments could take away: two edges,
    # both in the pool, roughly collinear and bounding the same faces
    # (``collapsible_vertex`` is looser than Join Segments' own test, so
    # nothing it would join is missed). Handing it every edge of a big
    # mesh is quadratic: it checks each one against the mesh's edge list.
    candidates: dict = {}
    for e in pool:
        if not _edge_alive(e):
            continue
        for v in (e.v0, e.v1):
            if (len(v.edges) == 2 and all(id(x) in picked for x in v.edges)
                    and mesh.collapsible_vertex(v)):
                for x in v.edges:
                    candidates[id(x)] = x
    if not candidates:
        return 0, edges
    verdicts: dict = {}
    result = join_edges(mesh, list(candidates.values()), verdicts)
    joined = sum(1 for reason in verdicts.values() if reason == "join")
    if edges is not None:
        kept = {id(e): e for e in edges if _edge_alive(e)}
        kept.update((id(e), e) for e in result)
        edges = list(kept.values())
    return joined, edges
