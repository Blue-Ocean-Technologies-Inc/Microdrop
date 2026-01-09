from traits.api import provides, HasTraits, Instance

from ...interfaces.i_column import IColumn, IColumnModel, IColumnView, IColumnHandler


@provides(IColumnHandler)
class BaseColumnHandler(HasTraits):
    def on_interact(self, step, model, value):
        return model.set_value(step, value)


@provides(IColumn)
class Column(HasTraits):
    model = Instance(IColumnModel)
    view = Instance(IColumnView)
    handler = Instance(IColumnHandler, BaseColumnHandler())

    def traits_init(self):
        """Connect model view and the handler here"""

        self.view.model = self.model

        if self.handler is not None:
            self.handler = BaseColumnHandler()

        self.handler.model = self.model
        self.handler.view = self.view
