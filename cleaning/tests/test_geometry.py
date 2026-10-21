# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The mesh operations, one by one, on small hand-built meshes."""
from __future__ import annotations

import math

import pytest

from conftest import needs_ingetrazo, two_squares, v

pytestmark = needs_ingetrazo


@pytest.fixture
def mesh(qapp):
    from core.mesh import Mesh
    return Mesh()


def test_stray_edge_goes_and_the_face_stays(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    mesh.add_edge(v(1, 1), v(3, 3))
    assert geo.erase_stray_edges(mesh) == 1
    assert len(mesh.faces) == 1 and len(mesh.edges) == 4


def test_a_drawing_made_only_of_lines_is_not_litter(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_edge(v(0, 0), v(1, 0))
    mesh.add_edge(v(1, 0), v(1, 1))
    assert geo.erase_stray_edges(mesh) == 0
    assert len(mesh.edges) == 2


def test_stray_edges_restricted_to_the_given_ones(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    keep = mesh.add_edge(v(1, 1), v(3, 3))
    drop = mesh.add_edge(v(0, 0), v(-2, 0))
    assert geo.erase_stray_edges(mesh, [drop]) == 1
    assert keep in mesh.edges and drop not in mesh.edges


def test_coplanar_faces_become_one(plugin, mesh):
    geo = plugin["geo"]
    two_squares(mesh)
    assert geo.merge_coplanar_faces(mesh) == 1
    assert len(mesh.faces) == 1
    # The two points left on the long sides are split edges now.
    assert geo.repair_split_edges(mesh) == 2
    assert len(mesh.faces[0].loop) == 4 and len(mesh.edges) == 4
    assert math.isclose(mesh.faces[0].area(), 2.0, rel_tol=1e-6)


def test_differently_painted_faces_stay_apart_unless_asked(plugin, mesh):
    geo = plugin["geo"]
    two_squares(mesh, paint_b={"color": (1.0, 0.0, 0.0)})
    assert geo.merge_coplanar_faces(mesh, same_material=True) == 0
    assert geo.merge_coplanar_faces(mesh, same_material=False) == 1


def test_layers_are_never_merged_away(plugin, mesh):
    geo = plugin["geo"]
    two_squares(mesh, paint_b={"layer": "Walls"})
    assert geo.merge_coplanar_faces(mesh, same_material=False) == 0


def test_the_angle_tolerance_decides(plugin, mesh):
    geo = plugin["geo"]
    two_squares(mesh, tilt=math.radians(0.5))
    assert geo.merge_coplanar_faces(mesh, max_angle_deg=0.05) == 0
    assert geo.merge_coplanar_faces(mesh, max_angle_deg=1.0) == 1


def test_a_real_corner_is_kept(plugin, mesh):
    geo = plugin["geo"]
    two_squares(mesh, tilt=math.radians(90))
    assert geo.merge_coplanar_faces(mesh, max_angle_deg=5.0) == 0


def test_coplanar_merge_restricted_to_the_selection(plugin, mesh):
    geo = plugin["geo"]
    a, _b = two_squares(mesh)
    assert geo.merge_coplanar_faces(mesh, faces=[a]) == 0
    assert geo.merge_coplanar_faces(mesh, faces=list(mesh.faces)) == 1


def test_split_line_is_joined(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_edge(v(0, 0), v(1, 0))
    mesh.add_edge(v(1, 0), v(2, 0))
    mesh.add_edge(v(2, 0), v(3, 0))
    assert geo.repair_split_edges(mesh) == 2
    assert len(mesh.edges) == 1


def test_a_corner_is_not_a_split(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_edge(v(0, 0), v(1, 0))
    mesh.add_edge(v(1, 0), v(1, 1))
    assert geo.repair_split_edges(mesh) == 0


def test_degenerate_face_and_its_edges_go(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    flat = mesh.add_face([v(5, 0), v(6, 0), v(7, 0)])     # all on one line
    assert geo.is_degenerate(flat)
    assert geo.erase_degenerate_faces(mesh) == 1
    assert len(mesh.faces) == 1 and len(mesh.edges) == 4
    assert all(f in mesh.faces for e in mesh.edges for f in e.faces)


def test_repeated_corner_is_repaired_and_the_face_merges(plugin, mesh):
    geo = plugin["geo"]
    a, b = two_squares(mesh)
    # What an importer leaves: the first corner listed twice, and the
    # side from that corner to itself as an edge.
    corner = b.loop[0]
    b.loop.insert(0, corner)
    loop_edge = mesh._link_edge(corner, corner)
    loop_edge.faces.append(b)
    assert mesh.dissolve_edge(mesh.find_edge(a.loop[1], a.loop[2])) is None
    assert geo.repair_repeated_corners(mesh) == 1
    assert geo.erase_zero_length_edges(mesh) == 1
    assert all(e.v0 is not e.v1 for e in mesh.edges)
    assert geo.merge_coplanar_faces(mesh) == 1


def test_duplicate_face_goes(plugin, mesh):
    geo = plugin["geo"]
    pts = [v(0, 0), v(1, 0), v(1, 1), v(0, 1)]
    mesh.add_face(pts)
    twin = mesh.add_face(list(reversed(pts)))
    twin.attrs["color"] = (0.5, 0.5, 0.5)
    assert geo.erase_duplicate_faces(mesh) == 1
    assert len(mesh.faces) == 1
    assert mesh.faces[0].attrs.get("color") == (0.5, 0.5, 0.5)


def test_bulk_edge_removal_matches_the_primitive(plugin, mesh):
    geo = plugin["geo"]
    mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    strays = [mesh.add_edge(v(10 + i, 0), v(10 + i, 1)) for i in range(100)]
    assert geo.remove_edges(mesh, strays) == 100
    assert len(mesh.edges) == 4
    assert all(not s.v0.edges for s in strays)
