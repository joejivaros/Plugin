# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 G. Andreotti
"""The clean-up command: one undo step, scopes, materials, layers, groups,
and the preview that never changes the model."""
from __future__ import annotations

import pytest

from conftest import needs_ingetrazo, two_squares, v

pytestmark = needs_ingetrazo


@pytest.fixture
def scene(qapp):
    from core.scene import Scene
    return Scene()


@pytest.fixture
def history(scene):
    from core.history import History
    return History(scene)


def _only(cmd, **flags):
    """Options with every item off but ``flags``."""
    opts = cmd.Options(**{k: False for k in cmd.Options.GEOMETRY
                          + cmd.Options.DOCUMENT})
    for k, value in flags.items():
        setattr(opts, k, value)
    return opts


def _state(scene):
    from core.purge import iter_meshes
    meshes = list(iter_meshes(scene))
    return (sum(len(m.faces) for m in meshes),
            sum(len(m.edges) for m in meshes),
            sorted(scene.materials), [ly.name for ly in scene.layers],
            len(scene.groups))


def _material(name, color):
    from core.materials import Material
    return Material(name, color=color)


def test_options_round_trip_and_reject_bad_data(plugin):
    cmd = plugin["cmd"]
    opts = cmd.Options(stray_edges=False, coplanar_angle=1.5,
                       scope="selection")
    assert cmd.Options.from_dict(opts.to_dict()) == opts
    bad = cmd.Options.from_dict({"stray_edges": "yes", "scope": "planet",
                                 "coplanar_angle": float("nan")})
    assert bad == cmd.Options()
    assert cmd.Options.from_dict({"coplanar_angle": 99}).coplanar_angle == 0.05
    assert cmd.Options.from_dict(None) == cmd.Options()


def test_clean_is_one_undo_step(plugin, scene, history):
    cmd = plugin["cmd"]
    two_squares(scene.mesh)
    scene.mesh.add_edge(v(5, 5), v(6, 6))
    before = _state(scene)
    run = cmd.CleanCommand(cmd.Options())
    history.execute(run)
    assert history.last_error is None and history.last_rejected is None
    assert run.report["coplanar_faces"] == 1
    assert run.report["stray_edges"] == 1
    assert run.report["split_edges"] == 2
    after = _state(scene)
    assert after[:2] == (1, 4)
    assert len(history.undo_stack) == 1
    history.undo()
    assert _state(scene) == before
    history.redo()
    assert _state(scene) == after


def test_nothing_to_clean_leaves_no_undo_step(plugin, scene, history):
    cmd = plugin["cmd"]
    scene.mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    history.execute(cmd.CleanCommand(cmd.Options()))
    assert history.last_rejected == "nothing to clean"
    assert history.undo_stack == []


def test_preview_counts_without_changing_anything(plugin, scene):
    cmd = plugin["cmd"]
    two_squares(scene.mesh)
    edge = scene.mesh.add_edge(v(5, 5), v(6, 6))
    scene.selection.add(edge)
    scene.materials["Unused"] = _material("Unused", (1.0, 0.0, 0.0))
    before, version = _state(scene), scene.version
    report = cmd.preview(scene, cmd.Options())
    assert report["coplanar_faces"] == 1 and report["unused_materials"] == 1
    assert _state(scene) == before and scene.version == version
    assert scene.selection == {edge}
    real = cmd.CleanCommand(cmd.Options())
    real.do(scene)
    assert real.report == report


def test_identical_materials_merge_and_faces_follow(plugin, scene, history):
    cmd = plugin["cmd"]
    a = scene.mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    b = scene.mesh.add_face([v(5, 0), v(6, 0), v(6, 1), v(5, 1)])
    scene.materials["Wood"] = _material("Wood", (0.6, 0.4, 0.2))
    scene.materials["Wood (2)"] = _material("Wood (2)", (0.6, 0.4, 0.2))
    scene.materials["Steel"] = _material("Steel", (0.7, 0.7, 0.7))
    a.attrs.update(scene.materials["Wood (2)"].face_attrs())
    b.attrs.update(scene.materials["Steel"].face_attrs())
    run = cmd.CleanCommand(_only(cmd, duplicate_materials=True))
    history.execute(run)
    assert run.report["duplicate_materials"] == 1
    assert sorted(scene.materials) == ["Steel", "Wood"]
    assert a.attrs["mat"] == "Wood" and b.attrs["mat"] == "Steel"
    history.undo()
    assert a.attrs["mat"] == "Wood (2)" and "Wood (2)" in scene.materials


def test_group_paint_follows_a_merged_material(plugin, scene, history):
    from core.group import Group
    cmd = plugin["cmd"]
    g = Group()
    g.mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    scene.groups.append(g)
    scene.materials["Red"] = _material("Red", (1.0, 0.0, 0.0))
    scene.materials["Red (2)"] = _material("Red (2)", (1.0, 0.0, 0.0))
    g.material = scene.materials["Red (2)"].face_attrs()
    history.execute(cmd.CleanCommand(_only(cmd, duplicate_materials=True)))
    assert g.material["mat"] == "Red"
    history.undo()
    assert g.material["mat"] == "Red (2)"


def test_unused_materials_and_layers_are_purged(plugin, scene, history):
    from core.layers import Layer
    cmd = plugin["cmd"]
    f = scene.mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    scene.materials["Used"] = _material("Used", (0.1, 0.2, 0.3))
    scene.materials["Spare"] = _material("Spare", (0.9, 0.9, 0.9))
    f.attrs.update(scene.materials["Used"].face_attrs())
    scene.layers.append(Layer("Empty"))
    run = cmd.CleanCommand(_only(cmd, unused_materials=True,
                                 unused_layers=True))
    history.execute(run)
    assert list(scene.materials) == ["Used"]
    assert "Empty" not in [ly.name for ly in scene.layers]
    history.undo()
    assert "Spare" in scene.materials
    assert "Empty" in [ly.name for ly in scene.layers]


def test_empty_groups_go_locked_ones_stay(plugin, scene, history):
    from core.group import Group
    cmd = plugin["cmd"]
    full, empty, locked = Group(), Group(), Group()
    full.mesh.add_face([v(0, 0), v(1, 0), v(1, 1), v(0, 1)])
    locked.locked = True
    nested_empty = Group()
    full.children = [nested_empty]
    scene.groups.extend([full, empty, locked])
    run = cmd.CleanCommand(_only(cmd, empty_groups=True))
    history.execute(run)
    assert run.report["empty_groups"] == 2
    assert scene.groups == [full, locked] and full.children == []
    history.undo()
    assert scene.groups == [full, empty, locked]
    assert full.children == [nested_empty]


def test_whole_model_reaches_groups_but_not_locked_ones(plugin, scene,
                                                         history):
    from core.group import Group
    cmd = plugin["cmd"]
    open_g, locked = Group(), Group()
    two_squares(open_g.mesh)
    two_squares(locked.mesh)
    locked.locked = True
    scene.groups.extend([open_g, locked])
    history.execute(cmd.CleanCommand(_only(cmd, coplanar_faces=True)))
    assert len(open_g.mesh.faces) == 1
    assert len(locked.mesh.faces) == 2
    history.undo()
    assert len(open_g.mesh.faces) == 2


def test_selection_scope_only_touches_the_selection(plugin, scene, history):
    from core.group import Group
    cmd = plugin["cmd"]
    a, b = two_squares(scene.mesh)
    stray = scene.mesh.add_edge(v(5, 5), v(6, 6))
    picked = Group()
    two_squares(picked.mesh)
    other = Group()
    two_squares(other.mesh)
    scene.groups.extend([picked, other])
    scene.selection.update({a, picked})
    opts = _only(cmd, coplanar_faces=True, stray_edges=True)
    opts.scope = "selection"
    run = cmd.CleanCommand(opts)
    history.execute(run)
    assert len(scene.mesh.faces) == 2           # b was not selected
    assert stray in scene.mesh.edges
    assert len(picked.mesh.faces) == 1
    assert len(other.mesh.faces) == 2


def test_whole_model_waits_for_an_open_group(plugin, scene, history):
    from core.group import Group
    cmd = plugin["cmd"]
    g = Group()
    two_squares(g.mesh)
    scene.groups.append(g)
    scene.begin_group_edit(g)
    try:
        history.execute(cmd.CleanCommand(cmd.Options(scope="model")))
        assert "group" in (history.last_rejected or "")
        history.execute(cmd.CleanCommand(cmd.Options(scope="context")))
        assert history.last_rejected is None
        assert len(scene.mesh.faces) == 1
    finally:
        scene.end_group_edit()
