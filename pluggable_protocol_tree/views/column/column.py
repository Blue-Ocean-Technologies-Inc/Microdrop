from traits.api import provides, HasTraits, Instance, observe

from ...interfaces.i_column import IColumn, IColumnModel, IColumnView, IColumnHandler


@provides(IColumnHandler)
class BaseColumnHandler(HasTraits):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)

    def on_interact(self, step, model, value):
        return model.set_value(step, value)

    def on_run_step(self, row, context=None):
        """
        The main hook. Called when the row is the active step.

        Args:
            row: The row object (HasTraits)
            context: A shared dictionary for passing data between steps
        """
        pass


@provides(IColumn)
class Column(HasTraits):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler)

    def traits_init(self):
        """Connect model view and the handler here"""

        self.view.model = self.model

        if self.handler is None:
            self.handler = BaseColumnHandler()

        self.handler.model = self.model
        self.handler.view = self.view

    @observe('handler', post_init=True)
    def _handler_changed(self, event):
        print("handler changed")
        self.handler.model = self.model
        self.handler.view = self.view

    @observe('view', post_init=True)
    def _view_changed(self, event):
        print("view changed")
        self.view.model = self.model
        self.handler.view = self.view

    @observe('model', post_init=True)
    def _model_changed(self, event):
        print("model changed")
        self.view.model = self.model

