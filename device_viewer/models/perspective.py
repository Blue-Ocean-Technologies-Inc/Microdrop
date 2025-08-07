from traits.api import HasTraits, List, Instance, observe
from pyface.qt.QtGui import QTransform
from pyface.qt.QtCore import QPointF
import math

class PerspectiveModel(HasTraits):
    reference_rect = List(QPointF, []) # List of reference points for the rect, relative to untransformed feed
    transformed_reference_rect = List(QPointF, []) # List of reference points for the rect, relative to transformed feed, aka the scene
    camera_resolution = Instance(tuple, allow_none=True) # Resolution of the camera feed as (width, height)

    # Don't manually set this, it is updated automatically when the reference rect changes!
    # Not a property because it needs to be a trait for observe to work
    # Note: This matrix must be invertible, since we use its inverse
    transformation = Instance(QTransform, QTransform()) # Transformation matrix for perspective correction

    # -------------------- Methods ------------------------
    def get_closest_point(self, point: QPointF) -> tuple[QPointF, int]:
        """Get the closest point and index in the reference rectangle to a given point."""
        closest_point = self.transformed_reference_rect[0]
        min_distance = math.hypot(closest_point.x() - point.x(), closest_point.y() - point.y())
        closest_index = 0
        for i, ref_point in enumerate(self.transformed_reference_rect[1:], start=1):
            distance = math.hypot(ref_point.x() - point.x(), ref_point.y() - point.y())
            if distance < min_distance:
                min_distance = distance
                closest_point = ref_point
                closest_index = i
        return closest_point, closest_index

    @observe("reference_rect.items, transformed_reference_rect.items")
    def update_transformation(self, event=None):
        """Update the transformation matrix based on the reference rectangle such that the new point replaces the old one."""
        if len(self.reference_rect) == 4 and len(self.transformed_reference_rect) == 4:
            # Assuming the reference rectangle is a quadrilateral, we can compute a perspective transform
            new_transform = QTransform()
            QTransform.quadToQuad(self.reference_rect, self.transformed_reference_rect, new_transform)
            if new_transform.isInvertible(): # Only apply transformation if it's valid
                self.transformation = new_transform

    def reset_rects(self):
        """Reset the perspective model to its initial state. 
        Note that the transformation matrix is not reset. This is because we need to use the 
        inverse of the previous transformation to derive the reference rectangle. Call 
        update_transformation() after setting the reference rectangle to update the transformation matrix."""
        self.reference_rect.clear()
        self.transformed_reference_rect.clear()

    def reset(self):
        """Reset the perspective model to its initial state."""
        self.reset_rects()
        self.transformation = QTransform()