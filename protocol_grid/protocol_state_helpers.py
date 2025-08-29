def flatten_protocol_for_run(protocol_state):
    """
    Returns a list of dicts:
    {
        "step": ProtocolStep,
        "path": [int, ..],  # path in the tree
        "rep_idx": int,      # current repetition (1-based)
        "rep_total": int     # total repetitions for this step
    }
    """
    run_order = []

    def recurse(elements, path_prefix, group_reps=1):
        for idx, element in enumerate(elements):
            path = path_prefix + [idx]
            if hasattr(element, "parameters"):
                reps = int(element.parameters.get("Repetitions", 1) or 1)
            else:
                reps = 1
            if hasattr(element, "elements"):
                for g_rep in range(reps):
                    recurse(element.elements, path, group_reps * reps)
            else:
                # repetitions are handled internally by PathExecutionService class
                run_order.append({
                    "step": element,
                    "path": path,
                    "rep_idx": 1,
                    "rep_total": reps
                })
    recurse(protocol_state.sequence, [])
    return run_order