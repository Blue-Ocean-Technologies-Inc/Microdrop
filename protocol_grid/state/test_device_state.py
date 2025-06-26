from protocol_grid.state.device_state import DeviceState

if __name__ == "__main__":
    def make_electrode_dict(active_ids, total=120):
        return {str(i): (str(i) in active_ids) for i in range(total)}

    test_cases = [
        {
            "desc": "No electrodes, no paths",
            "activated_electrodes": make_electrode_dict([]),
            "paths": [],
            "step_duration": 2.0,
            "repetitions": 1,
            "repeat_duration": 0.0
        },
        {
            "desc": "Some electrodes active, no paths",
            "activated_electrodes": make_electrode_dict(["5", "10", "50"]),
            "paths": [],
            "step_duration": 3.0,
            "repetitions": 2,
            "repeat_duration": 0.0
        },
        {
            "desc": "No electrodes, one path",
            "activated_electrodes": make_electrode_dict([]),
            "paths": [["1", "2", "3", "4"]],
            "step_duration": 1.5,
            "repetitions": 2,
            "repeat_duration": 0.0
        },
        {
            "desc": "No electrodes, multiple paths, different lengths",
            "activated_electrodes": make_electrode_dict([]),
            "paths": [["10", "11"], ["20", "21", "22", "23", "24"], ["30", "31", "32"]],
            "step_duration": 1.0,
            "repetitions": 3,
            "repeat_duration": 0.0
        },
        {
            "desc": "Electrodes active, multiple paths, repeat_duration overrides",
            "activated_electrodes": make_electrode_dict(["2", "3", "4"]),
            "paths": [["5", "6", "7"], ["8", "9"]],
            "step_duration": 2.0,
            "repetitions": 2,
            "repeat_duration": 20.0
        },
        {
            "desc": "Electrodes active, no paths, repeat_duration overrides",
            "activated_electrodes": make_electrode_dict(["1", "2"]),
            "paths": [],
            "step_duration": 2.0,
            "repetitions": 2,
            "repeat_duration": 10.0
        },
        {
            "desc": "Paths present, but all empty",
            "activated_electrodes": make_electrode_dict([]),
            "paths": [[], []],
            "step_duration": 1.0,
            "repetitions": 1,
            "repeat_duration": 0.0
        },
        {
            "desc": "All electrodes active, no paths",
            "activated_electrodes": make_electrode_dict([str(i) for i in range(120)]),
            "paths": [],
            "step_duration": 1.0,
            "repetitions": 1,
            "repeat_duration": 0.0
        },
    ]

    for i, case in enumerate(test_cases):
        print(f"\nTest case {i+1}: {case['desc']}")
        ds = DeviceState(
            activated_electrodes=case["activated_electrodes"],
            paths=case["paths"]
        )
        print(ds)
        print("  Has paths:", ds.has_paths())
        print("  Has individual electrodes:", ds.has_individual_electrodes())
        print("  Longest path length:", ds.longest_path_length())
        print("  Activated electrode IDs:", ds.get_activated_electrode_ids())
        print("  All path electrodes:", ds.get_all_path_electrodes())
        print("  Calculated duration:",
              ds.calculated_duration(case["step_duration"], case["repetitions"], case["repeat_duration"]))