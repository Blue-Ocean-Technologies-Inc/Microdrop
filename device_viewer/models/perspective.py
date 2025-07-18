from traits.api import HasTraits, List, Instance
from pyface.qt.QtGui import QTransform
from pyface.qt.QtCore import QPointF
import math

class PerspectiveModel(HasTraits):
    reference_rect = List(QPointF, []) # List of reference points for the rect, relative to untransformed feed
    transformation = Instance(QTransform, QTransform()) # Transformation matrix for perspective correction

    # -------------------- Methods ------------------------
    def transformed_reference_rect(self) -> list[QPointF]:
        """Get the transformed reference rectangle points."""
        return [self.transformation.map(point) for point in self.reference_rect]

    def get_closest_point(self, point: QPointF) -> tuple[QPointF, int]:
        """Get the closest point and index in the reference rectangle to a given point."""
        transformed_rect = self.transformed_reference_rect()
        closest_point = transformed_rect[0]
        min_distance = math.hypot(closest_point.x() - point.x(), closest_point.y() - point.y())
        closest_index = 0
        for i, ref_point in enumerate(transformed_rect[1:], start=1):
            distance = math.hypot(ref_point.x() - point.x(), ref_point.y() - point.y())
            if distance < min_distance:
                min_distance = distance
                closest_point = ref_point
                closest_index = i
        return closest_point, closest_index
    
    def update_transformation(self, old_point_index, new_point: QPointF):
        """Update the transformation matrix based on the reference rectangle such that the new point replaces the old one."""
        if len(self.reference_rect) == 4:
            # Assuming the reference rectangle is a quadrilateral, we can compute a perspective transform
            new_transform = QTransform()
            new_polygon = self.transformed_reference_rect()
            new_polygon[old_point_index] = new_point
            QTransform.quadToQuad(self.transformed_reference_rect(), new_polygon, new_transform)
            new_transform = self.transformation * new_transform  # Combine with existing transformation
            if new_transform.isInvertible():
                self.transformation = new_transform

    def reset(self):
        """Reset the perspective model to its initial state."""
        self.reference_rect.clear()
        self.transformation = QTransform()