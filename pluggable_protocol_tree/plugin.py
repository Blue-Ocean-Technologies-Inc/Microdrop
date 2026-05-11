"""Envisage plugin wiring for the pluggable protocol tree.

Registers the PROTOCOL_COLUMNS extension point; contributes a dock
pane via TASK_EXTENSIONS. Other plugins contribute IColumn instances
by declaring `List(contributes_to=PROTOCOL_COLUMNS)` in their own
plugin class."""

from envisage.api import ExtensionPoint, Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.task_extension import TaskExtension
from traits.api import List, Str, Either

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import make_linear_repeats_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import make_repeat_duration_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import make_trail_length_column
from pluggable_protocol_tree.builtins.trail_overlay_column import make_trail_overlay_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, PKG, PKG_name, PROTOCOL_COLUMNS,
)
from pluggable_protocol_tree.services.device_viewer_sync import SYNC_ACTOR_TOPIC_DICT
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.models._compound_adapters import _expand_compound

from logger.logger_service import get_logger
logger = get_logger(__name__)


class PluggableProtocolTreePlugin(Plugin):
    id = f"{PKG}.plugin"
    name = PKG_name

    #: Envisage extension point — other plugins contribute IColumn /
    #: ICompoundColumn instances here. Named with a leading underscore so
    #: tests can inject contributions directly via `contributed_columns`
    #: (a plain List) without needing a full Envisage application registry.
    #:
    #: The element type is untyped (plain ``List``) on purpose:
    #: ``ICompoundColumn`` is parallel to (not a subtype of) ``IColumn``,
    #: so a typed ``List(Instance(IColumn))`` would raise TraitError
    #: whenever any plugin contributes a compound column, dropping every
    #: other contribution along with it. ``_assemble_columns`` dispatches
    #: on ``isinstance(c, ICompoundColumn)`` to expand compounds and
    #: keep plain columns as-is.
    _column_extension_point = ExtensionPoint(
        List(Either(IColumn, ICompoundColumn)), id=PROTOCOL_COLUMNS,
        desc="Columns contributed by other plugins (IColumn or ICompoundColumn).",
    )

    #: Plain list — set directly in tests; populated from the extension
    #: point at plugin start in a live application.
    contributed_columns = List(desc="Columns contributed by other plugins")

    # Standard plumbing
    actor_topic_routing = List([ACTOR_TOPIC_DICT, SYNC_ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._make_dock_pane],
            ),
        ]

    def _make_dock_pane(self, *args, **kwargs):
        from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane
        columns = self._assemble_columns()
        return PluggableProtocolDockPane(columns=columns, *args, **kwargs)

    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
            make_duration_column(),
            make_electrodes_column(),
            make_routes_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
            make_soft_start_column(),
            make_soft_end_column(),
            make_repeat_duration_column(),
            make_linear_repeats_column(),
        ]
        try:
            contributed = list(self.contributed_columns)
        except Exception:
            contributed = []     # no extension registry attached (e.g. headless)
        out = []
        for c in (builtins + contributed):
            if isinstance(c, ICompoundColumn):
                out.extend(_expand_compound(c))
            else:
                out.append(c)
        return out

    def start(self):
        """Populate contributed_columns from the extension point, then
        register the executor listener's subscriptions with the message
        router. Called by Envisage at plugin start, after extension points
        have resolved."""
        super().start()
        # Pull contributions from the Envisage extension point into the
        # plain contributed_columns list so _assemble_columns sees them.
        try:
            self.contributed_columns = list(self._column_extension_point)
        except Exception as e:
            # Don't swallow silently — a TraitError here used to drop
            # every contribution from every plugin and surface only as
            # an empty dock pane. Log it so the developer sees it.
            logger.warning(
                f"failed to read PROTOCOL_COLUMNS extension point: {e}"
            )
        try:
            from microdrop_utils.dramatiq_pub_sub_helpers import MessageRouterData
        except ImportError:
            # Headless test environments may not have a broker. Plugin
            # construction must not require Redis; a missing broker is
            # only a problem at the moment a protocol actually runs.
            return
        try:
            topics = sorted({
                t for c in self._assemble_columns()
                for t in (c.handler.wait_for_topics or [])
            })
            if not topics:
                return
            router_data = MessageRouterData()
            for topic in topics:
                router_data.add_subscriber_to_topic(
                    topic=topic,
                    subscribing_actor_name="pluggable_protocol_tree_executor_listener",
                )
        except Exception as e:
            # Redis briefly unreachable at startup shouldn't block the
            # plugin from contributing its dock pane. The protocol
            # itself can't run without Redis but the UI should still
            # mount so the user gets a meaningful error on play, not
            # a missing pane.
            logger.warning(
                f"failed to wire executor listener subscriptions "
                f"(Redis unreachable?): {e}"
            )
