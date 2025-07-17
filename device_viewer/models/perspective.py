from traits.api import HasTraits, List, Instance
from pyface.qt.QtGui import QTransform
from pyface.qt.QtCore import QPointF

class PerspectiveModel(HasTraits):
    reference_rect = List(QPointF, []) # List of reference points for the rect, relative to untransformed feed
    transformation = Instance(QTransform, QTransform()) # Transformation matrix for perspective correction