from typing import Tuple, Optional

from traits.api import HasTraits, List, Instance, observe
from pyface.qt.QtGui import QTransform
from pyface.qt.QtCore import QPointF

from logger.logger_service import get_logger
logger = get_logger(__name__)

class PerspectiveModel(HasTraits):
    reference_rect = List(Instance(QPointF), []) # List of reference points for the rect, relative to untransformed feed
    transformed_reference_rect = List(Instance(QPointF), []) # List of reference points for the rect, relative to transformed feed, aka the scene
    default_rect = List(Instance(QPointF), [])  # List of reference points used as a fallback if reference rect or transformed reference rect not given
    camera_resolution = Instance(tuple, allow_none=True) # Resolution of the camera feed as (width, height)

    # Don't manually set this, it is updated automatically when the reference rect changes!
    # Not a property because it needs to be a trait for observe to work
    # Note: This matrix must be invertible, since we use its inverse
    transformation = Instance(QTransform, QTransform()) # Transformation matrix for perspective correction

    # -------------------- Methods ------------------------
    def get_closest_point(self, point: QPointF) -> Tuple[Optional[QPointF], int]:
        """
        Get the closest point and index in the reference rectangle to a given point.
        Returns (None, -1) if the rectangle is empty.
        """
        if not self.transformed_reference_rect:
            return None, -1

        closest_point = self.transformed_reference_rect[0]
        closest_index = 0

        # Use squared distance to avoid expensive math.sqrt calls
        dx = closest_point.x() - point.x()
        dy = closest_point.y() - point.y()
        min_dist_sq = dx * dx + dy * dy

        for i, ref_point in enumerate(self.transformed_reference_rect[1:], start=1):
            dx = ref_point.x() - point.x()
            dy = ref_point.y() - point.y()
            dist_sq = dx * dx + dy * dy

            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_point = ref_point
                closest_index = i

        return closest_point, closest_index

    @observe("transformed_reference_rect.items")
    def update_transformation(self, event=None):
        """Update the transformation matrix based on the reference rectangle such that the new point replaces the old one."""

        if not len(self.transformed_reference_rect) == 4:
            logger.warning("Need 4 points in transformed reference rectangle: Transformation not updated.")
            return

        if len(self.reference_rect) == 4:
            logger.debug("Reference rectangle has 4 points: using this as src for transformation.")
            src = self.reference_rect

        elif len(self.default_rect) == 4:
            logger.info("Reference rectangle not set: using fallback default rectangle.")
            src = self.default_rect

        else:
            logger.warning('Neither reference rectangle nor a fallback default rectangle has been set: Transformation not updated')
            return

        new_transform = QTransform()
        QTransform.quadToQuad(src, self.transformed_reference_rect, new_transform)
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
        new_points = [rotator.map(p) for p in transformed_reference_rect]

        # 4. Update the trait
        #    This automatically triggers 'update_transformation' via the @observe decorator
        self.transformed_reference_rect = new_points

    def perspective_transformation_possible(self) -> bool:
        """
        Return True if perspective transformation is possible, False otherwise.
        """
        return len(self.transformed_reference_rect) == 4 and (len(self.reference_rect) == 4 or len(self.default_rect) == 4)