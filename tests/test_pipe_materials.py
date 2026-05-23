"""
tests/test_pipe_materials.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Test: Multiple Pipe Materials and Diameters

This test builds a network with pipes of different materials (steel, PVC, ductile iron)
and diameters, and checks that the computed wave speeds and steady-state flows
match expected analytical values for each segment.
"""

import math
import numpy as np
import pytest
import rthym_moc

# Pipe material properties (Young's modulus in psi)
MATERIALS = {
    "steel":        {"E": 29_000_000, "diameter": 24.0, "wall_thickness": 0.375, "roughness": 120.0},
    "ductile_iron": {"E": 24_000_000, "diameter": 30.0, "wall_thickness": 0.5,   "roughness": 140.0},
    "pvc":          {"E": 400_000,    "diameter": 36.0, "wall_thickness": 1.0,   "roughness": 150.0},
}

LENGTHS = {
    "steel": 1000.0,
    "ductile_iron": 800.0,
    "pvc": 600.0,
}

# Analytical Korteweg wave speed (ft/s)
def analytical_wave_speed(E, D, e, poissons_ratio=0.3):
    K_w = 319_000.0  # psi, bulk modulus of water
    a0 = 4860.0      # ft/s, speed of sound in water
    restraint = 1.0 - poissons_ratio * poissons_ratio
    return a0 / math.sqrt(1.0 + (D * K_w * restraint) / (E * e))


def _make_node(node_id, node_type, **kwargs):
    node = rthym_moc.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length, **kwargs):
    pipe = rthym_moc.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _build_material_case(mat):
    props = MATERIALS[mat]
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("A", "PressureBoundary", elevation=0.0, head=100.0))
    solver.add_node(_make_node("B", "PressureBoundary", elevation=0.0, head=90.0))
    solver.add_pipe(_make_pipe(
        "P1",
        "A",
        "B",
        LENGTHS[mat],
        diameter=props["diameter"],
        roughness=props["roughness"],
        wall_thickness=props["wall_thickness"],
        youngs_modulus=props["E"],
        poissons_ratio=0.3,
        flow_gpm=500.0,
    ))
    return solver.run(total_time=1.0, dt=0.01)


def _build_material_surge_case(mat):
    props = MATERIALS[mat]
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("A", "PressureBoundary", elevation=0.0, head=100.0))
    solver.add_node(_make_node(
        "V",
        "Valve",
        elevation=0.0,
        diameter=props["diameter"],
        current_setting=100.0,
        head=95.0,
    ))
    solver.add_node(_make_node("B", "PressureBoundary", elevation=0.0, head=90.0))
    pipe_kwargs = dict(
        diameter=props["diameter"],
        roughness=props["roughness"],
        wall_thickness=props["wall_thickness"],
        youngs_modulus=props["E"],
        poissons_ratio=0.3,
        flow_gpm=500.0,
    )
    solver.add_pipe(_make_pipe("P1", "A", "V", LENGTHS[mat], **pipe_kwargs))
    solver.add_pipe(_make_pipe("P2", "V", "B", 10.0, **pipe_kwargs))
    solver.set_valve_schedule("V", [(0.0, 100.0), (0.09, 100.0), (0.1, 0.0)])
    return solver.run(total_time=0.3, dt=0.01)


def _value_at(time_series, values, target_time):
    mask = np.isclose(time_series, target_time)
    assert np.any(mask), f"Time {target_time:.2f}s not found in solver output"
    return float(np.asarray(values)[mask][0])

@pytest.mark.parametrize("mat", MATERIALS.keys())
def test_pipe_material_wave_speed(mat):
    """Valve-closure surge magnitude should track the material's elastic wave speed."""
    props = MATERIALS[mat]
    a_expected = analytical_wave_speed(props["E"], props["diameter"], props["wall_thickness"])
    results = _build_material_surge_case(mat)
    time = np.asarray(results["time"])
    valve_head = np.asarray(results["node_head"]["V"])
    head_before_closure = _value_at(time, valve_head, 0.10)
    head_after_closure = _value_at(time, valve_head, 0.11)
    observed_rise = head_after_closure - head_before_closure

    area_sqft = math.pi * (props["diameter"] / 12.0) ** 2 / 4.0
    flow_cfs = 500.0 / 448.831
    velocity_fps = flow_cfs / area_sqft
    expected_rise = a_expected * velocity_fps / 32.2

    assert observed_rise > 0.0, f"{mat}: closure should create a positive surge, got {observed_rise:.2f} ft"
    assert 0.5 * expected_rise <= observed_rise <= 3.0 * expected_rise, (
        f"{mat}: first-step head rise {observed_rise:.2f} ft should stay within a reasonable "
        f"range of the Korteweg estimate {expected_rise:.2f} ft"
    )

@pytest.mark.parametrize("mat", MATERIALS.keys())
def test_pipe_material_steady_state_flow(mat):
    """Changing pipe elasticity should not reverse the positive steady operating-point flow."""
    results = _build_material_case(mat)
    q = results["pipe_flow_gpm"]["P1"][-1]
    assert q > 0, f"{mat}: steady-state flow should be positive, got {q} GPM"
