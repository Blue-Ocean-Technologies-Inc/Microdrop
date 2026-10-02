# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from typing import Optional, Tuple

# Enthought library imports.
from pyface.qt.QtCore import QPointF
from pyface.qt.QtGui import QTransform
from traits.api import HasTraits, Instance, List, observe

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PerspectiveModel(HasTraits):
    #: Reference rect corners in the untransformed camera feed.
    reference_rect = List(Instance(QPointF), [])

    #: Reference rect corners in the transformed feed, aka the scene.
    transformed_reference_rect = List(Instance(QPointF), [])

    #: Fallback corners used when either reference rect is not given.
    default_rect = List(Instance(QPointF), [])

    #: Resolution of the camera feed as (width, height).
    camera_resolution = Instance(tuple, allow_none=True)

    #: Perspective-correction matrix, mapping the reference rect onto the
    #: transformed one. Updated automatically when the rects change -- never
    #: set it by hand. A trait rather than a Property so it can be observed;
    #: it must stay invertible because its inverse is used.
    transformation = Instance(QTransform, QTransform())

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
        """Map the reference rect onto the transformed reference rect."""

        if not len(self.transformed_reference_rect) == 4:
            logger.warning(
                "Need 4 points in transformed reference rectangle: "
                "Transformation not updated."
            )
            return

        if len(self.reference_rect) == 4:
            logger.debug(
                "Reference rectangle has 4 points: using this as src for "
                "transformation."
            )
            src = self.reference_rect

        elif len(self.default_rect) == 4:
            logger.info(
                "Reference rectangle not set: using fallback default rectangle."
            )
            src = self.default_rect

        else:
            logger.warning(
                "Neither reference rectangle nor a fallback default rectangle "
                "has been set: Transformation not updated"
            )
            return

        new_transform = QTransform()
        ok = QTransform.quadToQuad(src, self.transformed_reference_rect, new_transform)

        # A failed quadToQuad leaves the (invertible) identity behind.
        if ok and new_transform.isInvertible():
            self.transformation = new_transform

        else:
            logger.warning(
                "Degenerate reference rectangle (no perspective maps one quad "
                "onto the other): Transformation not updated."
            )

    def reset_rects(self):
        """Reset the perspective model to its initial state.

        The transformation matrix is not reset: its inverse is needed to
        derive the reference rectangle. Call update_transformation() after
        setting the reference rectangle to update the matrix.
        """
        self.reference_rect.clear()
        self.transformed_reference_rect.clear()

    def reset(self):
        """Reset the perspective model to its initial state."""
        self.reset_rects()
        self.transformation = QTransform()

    def rotate_output(self, angle_degrees):
        """Spin the video feed by 'angle_degrees' about its own centre."""
        self._transform_output_about_centre(lambda about: about.rotate(angle_degrees))

    def flip_output(self, horizontal):
        """Mirror the video feed about its own centre.

        A horizontal flip mirrors left-right (about the vertical axis), a
        vertical flip top-bottom. Flipping twice restores the feed.
        """
        scale_x, scale_y = (-1, 1) if horizontal else (1, -1)
        self._transform_output_about_centre(lambda about: about.scale(scale_x, scale_y))

    def _transform_output_about_centre(self, apply_to):
        """Move the transformed reference rect by a transform about its centroid.

        Operating on the destination quad keeps the feed pinned in place and
        lets the result fall out of update_transformation, so it persists in
        the rect preference and corner dragging keeps working. The default
        rect is the starting quad when no rect has been placed yet.

        Parameters
        ----------
        apply_to : callable
            Receives a QTransform whose origin is at the rect's centroid and
            applies the rotation/reflection to it in place.
        """

        if len(self.transformed_reference_rect) != 4:
            transformed_reference_rect = self.default_rect

        else:
            transformed_reference_rect = self.transformed_reference_rect

        cx = sum(p.x() for p in transformed_reference_rect) / 4.0
        cy = sum(p.y() for p in transformed_reference_rect) / 4.0

        about_centre = QTransform()
        about_centre.translate(cx, cy)
        apply_to(about_centre)
        about_centre.translate(-cx, -cy)

        # Reassigning the trait triggers update_transformation via @observe.
        self.transformed_reference_rect = [
            about_centre.map(p) for p in transformed_reference_rect
        ]

    def perspective_transformation_possible(self) -> bool:
        """Return True if perspective transformation is possible."""
        return len(self.transformed_reference_rect) == 4 and (
            len(self.reference_rect) == 4 or len(self.default_rect) == 4
        )
