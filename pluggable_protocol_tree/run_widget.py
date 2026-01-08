from pluggable_protocol_tree.models.column import BaseColumnModel
from pluggable_protocol_tree.tree_widget import ProtocolEditorWidget
from pluggable_protocol_tree.views.base_column_views import StringEditColumnView
from pluggable_protocol_tree.views.column import Column
from pluggable_protocol_tree.views.default_column_views import IDView

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow

    # 2. Setup Columns
    test_columns = [
        Column(model=BaseColumnModel(col_name="ID", col_id="id"), view=IDView()),
        Column(
            model=BaseColumnModel(col_name="Name", col_id="name"),
            view=StringEditColumnView(),
        ),
    ]

    # 4. Run App
    app = QApplication(sys.argv)

    window = QMainWindow()
    widget = ProtocolEditorWidget(parent=window, columns=test_columns)

    window.setCentralWidget(widget)
    window.resize(800, 600)
    window.show()

    sys.exit(app.exec())
