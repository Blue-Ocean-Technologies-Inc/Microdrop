"""Envisage plugin wiring for the pluggable protocol tree.

Registers the PROTOCOL_COLUMNS extension point; contributes a dock
pane via TASK_EXTENSIONS. Other plugins contribute IColumn instances
by declaring `List(contributes_to=PROTOCOL_COLUMNS)` in their own
plugin class."""

from envisage.api import ExtensionPoint, Plugin, TASK_EXTENSIONS
from envisage.ids import PREFERENCES_CATEGORIES, PREFERENCES_PANES
from envisage.ui.tasks.task_extension import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import Instance, List, Str, Either

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.electrodes_column import make_electrodes_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.linear_repeats_column import make_linear_repeats_column
from pluggable_protocol_tree.builtins.message_prompt_column import make_message_prompt_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.repeat_duration_column import make_repeat_duration_column
from pluggable_protocol_tree.builtins.repetitions_column import make_repetitions_column
from pluggable_protocol_tree.builtins.route_repetitions_column import (
    make_route_repetitions_column,
)
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.builtins.soft_end_column import make_soft_end_column
from pluggable_protocol_tree.builtins.soft_start_column import make_soft_start_column
from pluggable_protocol_tree.builtins.trail_length_column import make_trail_length_column
from pluggable_protocol_tree.builtins.trail_overlay_column import make_trail_overlay_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, EXECUTOR_LISTENER_NAME,
    PKG, PKG_name, PROTOCOL_COLUMNS, PROTOCOL_QUICK_ACTIONS,
)
from pluggable_protocol_tree.interfaces.i_compound_column import ICompoundColumn
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.interfaces.i_quick_action import IQuickAction
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

    #: Envisage extension point — sibling plugins contribute
    #: IQuickAction instances rendered as buttons on the tree's
    #: quick-actions toolbar. Tree plugin itself contributes none.
    _quick_action_extension_point = ExtensionPoint(
        List(Instance(IQuickAction)), id=PROTOCOL_QUICK_ACTIONS,
        desc="IQuickAction instances contributed by sibling plugins.",
    )

    contributed_quick_actions = List(
        desc="Quick actions contributed by other plugins (populated "
             "from the extension point at plugin start).")

    # Standard plumbing
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    # Protocol Settings tab (#419) — the tree's own category id, ordered
    # like the legacy grid tab (after Device Viewer, before Peripheral
    # Settings). Imports are local so plugin import stays light (the pane
    # pulls traitsui).
    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    def _preferences_panes_default(self):
        from pluggable_protocol_tree.services.preferences import (
            ProtocolPreferencesPane,
        )
        return [ProtocolPreferencesPane]

    def _preferences_categories_default(self):
        from pluggable_protocol_tree.services.preferences import (
            protocol_tree_tab,
        )
        return [protocol_tree_tab]

    def _contributed_task_extensions_default(self):
        from pluggable_protocol_tree.menus import (
            new_experiment_factory, protocol_menu_factory,
        )
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._make_dock_pane],
                actions=[
                    SchemaAddition(
                        factory=new_experiment_factory,
                        path='MenuBar/File',
                        absolute_position="first",
                    ),
                    SchemaAddition(
                        factory=protocol_menu_factory,
                        path="MenuBar/File",
                        before="Exit",
                    ),
                ],
            ),
        ]

    def _make_dock_pane(self, *args, **kwargs):
        from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane
        columns = self._assemble_columns()
        quick_actions = self._assemble_quick_actions()
        return PluggableProtocolDockPane(
            columns=columns, quick_actions=quick_actions,
            *args, **kwargs)

    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_repetitions_column(),
            make_route_repetitions_column(),
            make_duration_column(),
            make_electrodes_column(),
            make_routes_column(),
            make_trail_length_column(),
            make_trail_overlay_column(),
            make_soft_start_column(),
            make_soft_end_column(),
            make_repeat_duration_column(),
            make_linear_repeats_column(),
            make_message_prompt_column(),
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

    def _assemble_quick_actions(self):
        """Return contributed quick actions in deterministic order
        (priority then action_id)."""
        try:
            actions = list(self.contributed_quick_actions)
        except Exception:
            actions = []
        return sorted(actions, key=lambda a: (a.priority, a.action_id))

    def start(self):
        """Populate contributed_columns from the extension point, then
        contribute the executor listener's topics to the message router's
        routing extension point. Called by Envisage at plugin start, after
        extension points have resolved."""
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
            self.contributed_quick_actions = list(
                self._quick_action_extension_point)
        except Exception as e:
            logger.warning(
                f"failed to read PROTOCOL_QUICK_ACTIONS extension point: {e}"
            )

        try:
            # The executor's wait topics depend on the assembled column
            # set, so they can't sit in the static ACTOR_TOPIC_DICT
            # contribution — append them at start. Works in either start
            # order: a router that starts later reads the full
            # contribution list; one that started earlier picks the
            # append up via its extension-point change handler.
            executor_topics = sorted({
                topic for col in self._assemble_columns()
                for topic in (col.handler.wait_for_topics or [])
            })
            if not executor_topics:
                return
            self.actor_topic_routing.append(
                {EXECUTOR_LISTENER_NAME: executor_topics})
        except Exception as e:
            # If the router already started, the append subscribes
            # synchronously through its change handler — Redis briefly
            # unreachable at startup shouldn't block the plugin from
            # contributing its dock pane. The protocol itself can't run
            # without Redis but the UI should still mount so the user
            # gets a meaningful error on play, not a missing pane.
            logger.warning(
                f"failed to contribute executor listener subscriptions "
                f"(Redis unreachable?): {e}"
            )
