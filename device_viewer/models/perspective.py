from traits.api import HasTraits, List, Instance, observe
from pyface.qt.QtGui import QTransform
from pyface.qt.QtCore import QPointF
import math

class PerspectiveModel(HasTraits):
    reference_rect = List(QPointF, []) # List of reference points for the rect, relative to untransformed feed
    transformed_reference_rect = List(QPointF, []) # List of reference points for the rect, relative to transformed feed, aka the scene
    default_rect = List(QPointF, [])  # List of reference points used as a fallback if reference rect or transformed reference rect not given
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

    @observe("transformed_reference_rect.items")
    def update_transformation(self, event=None):
        """Update the transformation matrix based on the reference rectangle such that the new point replaces the old one."""
        if len(self.reference_rect) == 4 and len(self.transformed_reference_rect) == 4:
        # Assuming the reference rectangle is a quadrilateral, we can compute a perspective transform
            new_transform = QTransform()
            QTransform.quadToQuad(self.reference_rect, self.transformed_reference_rect, new_transform)
            if new_transform.isInvertible(): # Only apply transformation if it's valid
                self.transformation = new_transform
        elif len(self.transformed_reference_rect) == 4:
            new_transform = QTransform()
            QTransform.quadToQuad(self.default_rect, self.transformed_reference_rect, new_transform)
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

    def rotate_output(self, angle_degrees):
        """
        Rotates the transformed reference rectangle by 'angle_degrees'.
        This effectively spins the video feed while keeping it pinned to the same location.
        """
        if len(self.transformed_reference_rect) != 4:
            transformed_reference_rect = self.default_rect
        else:
            transformed_reference_rect = self.transformed_reference_rect

        # 1. Calculate the Centroid (Geometric Center) of the current rect
        #    We will pivot the rotation around this point.
        cx = sum(p.x() for p in transformed_reference_rect) / 4.0
        cy = sum(p.y() for p in transformed_reference_rect) / 4.0

        # 2. Create a temporary Transform for the rotation math
        rotator = QTransform()
        rotator.translate(cx, cy)  # Move origin to center
        rotator.rotate(angle_degrees)  # Rotate
        rotator.translate(-cx, -cy)  # Move origin back

        # 3. Apply this rotation to every point in the destination rect
        new_points = []
        for point in transformed_reference_rect:
            new_points.append(rotator.map(point))

        # 4. Update the trait
        #    This automatically triggers 'update_transformation' via the @observe decorator
        self.transformed_reference_rect = new_points