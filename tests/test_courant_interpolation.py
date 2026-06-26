import pytest
import rthym_moc as m

def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node

def _make_pipe(pipe_id, from_node, to_node, length_ft, diameter_in=12.0, roughness=130.0, flow_gpm=0.0):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = diameter_in
    pipe.roughness = roughness
    pipe.flow_gpm = flow_gpm
    return pipe

def test_interpolation_mode_getter_setter():
    solver = m.MOCSolver()
    assert solver.get_interpolation_mode() is False
    
    solver.set_interpolation_mode(True)
    assert solver.get_interpolation_mode() is True
    
    solver.set_interpolation_mode(False)
    assert solver.get_interpolation_mode() is False

def test_zero_distortion_arbitrary_lengths():
    """Verify that enabling interpolation mode eliminates wave-speed distortion."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    
    # Pipe length 103.0 ft does not align with default dt=0.01 s and a=4000 ft/s (dx_target = 40.0 ft)
    # 103 / 40 = 2.575, which rounds to 3 segments (dx = 34.33 ft, a_wave = 3433.3 ft/s -> 14.1% distortion)
    solver.add_pipe(_make_pipe("P1", "R1", "R2", length_ft=103.0))
    
    # Without interpolation, check that there is distortion
    solver.set_max_wave_speed_distortion(0.01) # 1% limit
    solver.set_wave_speed_distortion_action("warn")
    
    # Verify that get_grid_report shows warning / distortion without interpolation
    report_rigid = solver.get_grid_report(dt=0.01)
    assert report_rigid["pipe_distortion_pct"]["P1"] > 10.0
    
    # Enable interpolation mode and check that distortion becomes zero
    solver.set_interpolation_mode(True)
    report_interp = solver.get_grid_report(dt=0.01)
    assert report_interp["pipe_distortion_pct"]["P1"] < 1e-6
    assert report_interp["pipe_courant_number"]["P1"] < 1.0
    assert not report_interp["distortion_warning"]

def test_interpolation_accuracy_and_stability():
    """Compare simple valve closure on exact segment length (rigid MOC) vs slightly offset length (interp MOC)."""
    # Case A: Rigid MOC (Exact length = 400.0 ft, N = 10 segments, Cr = 1.0)
    solver_rigid = m.MOCSolver()
    solver_rigid.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver_rigid.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver_rigid.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    solver_rigid.add_pipe(_make_pipe("P1", "R1", "V1", length_ft=400.0, flow_gpm=100.0))
    solver_rigid.add_pipe(_make_pipe("P2", "V1", "R2", length_ft=400.0, flow_gpm=100.0))
    
    solver_rigid.set_valve_schedule("V1", [(0.0, 100.0), (0.1, 100.0), (0.2, 0.0)])
    res_rigid = solver_rigid.run(total_time=1.5, dt=0.01)
    max_h_rigid = max(res_rigid["node_head"]["V1"])
    
    # Case B: Interpolated MOC (Slightly offset length = 412.0 ft, N = 10 segments, Cr = 0.97)
    solver_interp = m.MOCSolver()
    solver_interp.set_interpolation_mode(True)
    solver_interp.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver_interp.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver_interp.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    solver_interp.add_pipe(_make_pipe("P1", "R1", "V1", length_ft=412.0, flow_gpm=100.0))
    solver_interp.add_pipe(_make_pipe("P2", "V1", "R2", length_ft=412.0, flow_gpm=100.0))
    
    solver_interp.set_valve_schedule("V1", [(0.0, 100.0), (0.1, 100.0), (0.2, 0.0)])
    res_interp = solver_interp.run(total_time=1.5, dt=0.01)
    max_h_interp = max(res_interp["node_head"]["V1"])
    
    # Verify that Case B is stable and yields very similar peak head
    # (should be within 12% due to minor numerical damping of linear interpolation)
    assert max_h_interp > 100.0
    assert abs(max_h_interp - max_h_rigid) / max_h_rigid < 0.12

def test_hybrid_mode_very_short_pipes():
    """Verify that a pipe shorter than a*dt gets wave speed adjusted to match Cr = 1.0 (N=1) in interpolation mode."""
    solver = m.MOCSolver()
    solver.set_interpolation_mode(True)
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    
    # L = 5 ft, a = 4000 ft/s, dt = 0.01 s.
    # a*dt = 40 ft. Since L = 5 ft < 40 ft, it must adjust wave speed to 5 / 0.01 = 500 ft/s.
    solver.add_pipe(_make_pipe("P1", "R1", "R2", length_ft=5.0))
    
    report = solver.get_grid_report(dt=0.01)
    assert report["pipe_num_segments"]["P1"] == 1
    assert abs(report["pipe_wave_speed_adjusted_fps"]["P1"] - 500.0) < 1e-6
    assert abs(report["pipe_courant_number"]["P1"] - 1.0) < 1e-6
