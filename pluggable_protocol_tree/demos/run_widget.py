from pluggable_protocol_tree.models.column import BaseColumnModel
from pluggable_protocol_tree.views.column.base_column_views import StringEditColumnView
from pluggable_protocol_tree.views.column.column import Column
from pluggable_protocol_tree.views.column.default_columns import (
    get_id_column,
    get_duration_column,
)
from pluggable_protocol_tree.views.tree_widget import ProtocolEditorWidget

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow

    # 2. Setup Columns
    test_columns = [
        get_id_column(),
        Column(
            model=BaseColumnModel(col_name="Name", col_id="name"),
            view=StringEditColumnView(),
        ),
        get_duration_column()
    ]

    # 4. Run App
    app = QApplication(sys.argv)

    window = QMainWindow()
    widget = ProtocolEditorWidget(parent=window, columns=test_columns)

    window.setCentralWidget(widget)
    window.resize(800, 600)
    window.show()

    sys.exit(app.exec())
