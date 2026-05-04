"""Topic constants and ACTOR_TOPIC_DICT for PPT-8 droplet check."""

from dropbot_protocol_controls.consts import (
    ACTOR_TOPIC_DICT,
    CALIBRATION_LISTENER_ACTOR_NAME,
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
)


def test_droplet_check_decision_topics_are_strings():
    assert DROPLET_CHECK_DECISION_REQUEST == "ui/droplet_check/decision_request"
    assert DROPLET_CHECK_DECISION_RESPONSE == "ui/droplet_check/decision_response"


def test_droplet_check_listener_actor_name_has_no_ppt_prefix():
    # Cross-issue policy (memory: actor names decouple from issue tracking)
    assert DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME == "droplet_check_decision_listener"
    assert "ppt" not in DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME.lower()


def test_actor_topic_dict_routes_decision_request_to_listener():
    assert (
        ACTOR_TOPIC_DICT[DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME]
        == [DROPLET_CHECK_DECISION_REQUEST]
    )


def test_actor_topic_dict_preserves_calibration_listener_from_ppt7():
    # Don't break the existing PPT-7 routing
    from dropbot_protocol_controls.consts import CALIBRATION_DATA
    assert ACTOR_TOPIC_DICT[CALIBRATION_LISTENER_ACTOR_NAME] == [CALIBRATION_DATA]
