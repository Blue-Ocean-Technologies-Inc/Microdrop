import sys
import random
import copy
from PySide6.QtWidgets import QPushButton, QFileDialog, QVBoxLayout, QWidget, QMainWindow, QApplication
from protocol_grid.widget import PGCWidget
from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.state.device_state import DeviceState
from protocol_grid.consts import protocol_grid_fields, step_defaults, ROW_TYPE_ROLE, STEP_TYPE, GROUP_TYPE

def make_random_device_state():
    total = 120
    active = random.sample([str(i) for i in range(total)], random.randint(0, 10))
    paths = []
    for _ in range(random.randint(0, 3)):
        path_len = random.randint(2, 8)
        paths.append(random.sample([str(i) for i in range(total)], path_len))
    return DeviceState({k: (k in active) for k in [str(i) for i in range(total)]}, paths)

def make_random_protocol(num_steps=400, max_depth=4, group_prob=0.3, cur_depth=0):
    steps_left = [num_steps]
    sequence = []
    group_counter = [1]
    step_counter = [1]

    def make_group(name, cur_depth):
        group_size = random.randint(2, min(steps_left[0], 10))
        group_elements = []
        used = 0
        while used < group_size and steps_left[0] > 0:
            if cur_depth < max_depth and random.random() < group_prob and steps_left[0] - used > 2:
                subgroup = make_group(f"{name}_{group_counter[0]}", cur_depth + 1)
                group_elements.append(subgroup)
                group_counter[0] += 1
            else:
                step_params = dict(step_defaults)
                step_params["Description"] = f"Step {step_counter[0]}"
                step_params["ID"] = str(step_counter[0])
                step = ProtocolStep(
                    parameters=step_params,
                    name=f"Step {step_counter[0]}"
                )
                step.device_state = make_random_device_state()
                group_elements.append(step)
                step_counter[0] += 1
                used += 1
                steps_left[0] -= 1
        group = ProtocolGroup(
            parameters={"Description": f"Group {name}"},
            name=f"Group {name}",
            elements=group_elements
        )
        print(f"Created group '{name}' with {len(group_elements)} elements at depth {cur_depth}")
        return group

    while steps_left[0] > 0:
        if cur_depth < max_depth and random.random() < group_prob and steps_left[0] > 2:
            group = make_group(f"Root_{group_counter[0]}", cur_depth + 1)
            sequence.append(group)
            group_counter[0] += 1
        else:
            step_params = dict(step_defaults)
            step_params["Description"] = f"Step {step_counter[0]}"
            step_params["ID"] = str(step_counter[0])
            step = ProtocolStep(
                parameters=step_params,
                name=f"Step {step_counter[0]}"
            )
            step.device_state = make_random_device_state()
            sequence.append(step)
            step_counter[0] += 1
            steps_left[0] -= 1
    print(f"Top-level sequence has {len(sequence)} elements")
    return sequence

class LargeProtocolMainWindow(QMainWindow):
    def __init__(self, protocol_state):
        super().__init__()
        self.setWindowTitle("Large Protocol Test")
        grid_widget = PGCWidget(state=protocol_state)
        btn = QPushButton("Export Flat Steps JSON")
        btn.clicked.connect(self.export_flat_steps_json)
        layout = QVBoxLayout()
        layout.addWidget(btn)
        layout.addWidget(grid_widget)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.resize(1400, 700)

    def export_flat_steps_json(self):
        self.sync_model_to_steps()
        def flatten_steps(seq):
            steps = []
            for obj in seq:
                if isinstance(obj, ProtocolStep):
                    step_dict = obj.to_dict() if hasattr(obj, "to_dict") else {}
                    params = step_dict.get("parameters", {})
                    flat = dict(params)
                    steps.append(flat)
                elif isinstance(obj, ProtocolGroup):
                    steps.extend(flatten_steps(obj.elements))
            return steps

        steps = flatten_steps(self.centralWidget().layout().itemAt(1).widget().state.sequence)
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Flat Steps JSON", "", "JSON Files (*.json)")
        if file_name:
            import json
            with open(file_name, "w") as f:
                json.dump(steps, f, indent=2)
            print(f"Exported {len(steps)} steps to {file_name}")

    def sync_model_to_steps(self):
        grid_widget = self.centralWidget().layout().itemAt(1).widget()
        model = grid_widget.model
        state = grid_widget.state

        def sync_recursive(parent, elements):
            for row in range(parent.rowCount()):
                item = parent.child(row, 0)
                if item is None:
                    continue
                row_type = item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    step = elements[row]
                    for col, field in enumerate(protocol_grid_fields):
                        value = parent.child(row, col).text()
                        step.parameters[field] = value
                elif row_type == GROUP_TYPE:
                    group = elements[row]
                    sync_recursive(item, group.elements)

        sync_recursive(model.invisibleRootItem(), state.sequence)

def main():
    app = QApplication(sys.argv)
    sequence = make_random_protocol(num_steps=400)
    protocol_state = ProtocolState(sequence=sequence)
    protocol_state.fields = list(protocol_grid_fields)
    print(f"ProtocolState.sequence length: {len(protocol_state.sequence)}")
    window = LargeProtocolMainWindow(protocol_state)
    print("Window created, showing...")
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()