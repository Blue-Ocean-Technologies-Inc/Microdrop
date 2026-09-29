# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Accept/discard flow: candidates -> filters -> session ROIs."""

# Microdrop package imports.
from image_viewer.analysis.ai_controller import (
    AiRoiController,
)
from image_viewer.analysis.roi_controller import (
    RoiAnalysisController,
)
from image_viewer.analysis.roi_model import (
    RoiAnalysisModel,
)
from image_viewer.analysis.sam_detect import (
    Candidate,
)
from image_viewer.model import (
    ImageViewerModel,
)


def _candidate(votes, rx=10.0):
    return Candidate(
        polygon=[0.0, 0.0, 20.0, 0.0, 20.0, 20.0],
        ellipse=[10.0, 10.0, rx, rx, 0.0],
        votes=votes,
        score=0.9,
    )


def _controllers():
    viewer = ImageViewerModel()
    analysis = RoiAnalysisModel()
    roi_controller = RoiAnalysisController(viewer_model=viewer, analysis_model=analysis)
    ai_controller = AiRoiController(viewer_model=viewer, analysis_model=analysis)
    return analysis, roi_controller, ai_controller


def test_accept_commits_only_filter_passing_undiscarded_candidates():
    analysis, roi_controller, _ai = _controllers()
    analysis.ai_candidates = [
        _candidate(votes=3),
        _candidate(votes=1),
        _candidate(votes=3),
    ]
    analysis.ai_candidates[2].discarded = True
    analysis.ai_significance = 2
    analysis.ai_accept_button = True
    assert len(roi_controller.session.rois) == 1
    assert analysis.ai_candidates == []


def test_output_kind_controls_accepted_geometry():
    analysis, roi_controller, _ai = _controllers()
    analysis.ai_output_kind = "ellipse"
    analysis.ai_candidates = [_candidate(votes=5)]
    analysis.ai_accept_button = True
    assert roi_controller.session.rois[0].kind == "ellipse"
