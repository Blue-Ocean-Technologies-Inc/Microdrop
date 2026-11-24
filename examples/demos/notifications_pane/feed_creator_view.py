# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The feed creator's window: the posts at the left, the form for the one
selected, its checks, and a live preview that is the feed's own card view.

Declarative TraitsUI; Qt only for the two editors TraitsUI lacks (rich
text, and a preview that can take another theme's palette) and a date box
with a calendar popup. Runs standalone against its model and controller::

    FeedCreatorController(model=FeedCreatorModel()).configure_traits(
        view=FeedCreatorView
    )
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Bool, Instance, List, Property, Str, observe
from traitsui.api import (
    BasicEditorFactory,
    DateEditor,
    EnumEditor,
    FileEditor,
    HGroup,
    HSplit,
    InstanceEditor,
    Item,
    ListStrEditor,
    TableEditor,
    UItem,
    VGroup,
    View,
    VSplit,
    spring,
)
from traitsui.qt.date_editor import SimpleEditor as QtSimpleDateEditor
from traitsui.qt.editor import Editor

# Microdrop style imports.
from microdrop_style.colors import BLACK, GREY, INFO_COLOR, WHITE
from microdrop_style.palettes import dark_palette

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import ObjectColumn

# Local imports.
from .feed_creator_rich_text import RichTextEditor
from .sci_bots_feed_cards import GRID, FeedPostCard, accent_color
from .sci_bots_feed_groups import group_posts
from .sci_bots_feed_view import ThemedWidget

#: The Type dropdown: stored value -> what the author reads.
KIND_LABELS = {
    "announcement": "1:Announcement",
    "product": "2:Product",
    "newsletter": "3:Newsletter",
    "post": "4:Post",
}

#: The preview is at least a feed pane wide; the post list keeps room too.
PREVIEW_MIN_WIDTH = 400
POST_LIST_MIN_WIDTH = 360

#: The preview's two cards: (lead, caption).
PREVIEW_CAPTIONS = (
    (True, "As the first post under “{group}”"),
    (False, "As a later post in the group"),
)

#: The picture file chooser's filter.
IMAGE_FILTER = ["Pictures (*.png *.jpg *.jpeg *.gif *.webp)"]


class _PopupDateEditor(QtSimpleDateEditor):
    """TraitsUI's date box, with a calendar to pick from."""

    def init(self, parent):
        super().init(parent)
        self.control.setCalendarPopup(True)
        self.control.setDisplayFormat("yyyy-MM-dd")


class PopupDateEditor(DateEditor):
    """A date box with a calendar popup."""

    simple_editor_class = Property()

    def _get_simple_editor_class(self):
        return _PopupDateEditor


class _FeedPreviewEditor(Editor):
    """Shows the edited post twice with the feed's own cards, as its group's
    lead card and as a compact row, in a chosen theme."""

    #: The preview's theme: one of PREVIEW_THEMES.
    theme = Str()

    #: The cards on show.
    _cards = List(Instance(FeedPostCard))

    #: Whether a rebuild for a palette change is already queued.
    _rebuild_queued = Bool(False)

    def init(self, parent):
        self.control = ThemedWidget()
        self.control.setAutoFillBackground(True)
        self.control.setMinimumWidth(PREVIEW_MIN_WIDTH)
        self.control.palette_changed.connect(self._queue_rebuild)
        layout = QtWidgets.QVBoxLayout(self.control)
        layout.setContentsMargins(2 * GRID, 2 * GRID, 2 * GRID, 2 * GRID)
        layout.setSpacing(GRID)

        self.sync_value(self.factory.theme, "theme", "from")

    def update_editor(self):
        """The first post as a lead card and as a row, with captions."""
        self._clear()

        layout = self.control.layout()

        for post in self.value[:1]:
            spec = group_posts([post])[0][0]
            accent = accent_color(spec, self.control.palette()).name()

            for lead, caption in PREVIEW_CAPTIONS:
                label = QtWidgets.QLabel(caption.format(group=spec.title), self.control)
                label.setForegroundRole(QtGui.QPalette.ColorRole.PlaceholderText)
                layout.addWidget(label)

                card = FeedPostCard(post=post.clone_traits(), lead=lead, accent=accent)
                layout.addWidget(card.create(self.control))
                self._cards.append(card)

        layout.addStretch()

    def dispose(self):
        self._clear()
        super().dispose()

    def _clear(self):
        for card in self._cards:
            card.dispose()

        self._cards = []
        layout = self.control.layout()

        while layout.count():
            item = layout.takeAt(0)

            if item.widget() is not None:
                item.widget().deleteLater()

    def _queue_rebuild(self):
        if not self._rebuild_queued:
            self._rebuild_queued = True
            QtCore.QTimer.singleShot(0, self._rebuild)

    def _rebuild(self):
        self._rebuild_queued = False

        if self.control is not None:
            self.update_editor()

    @observe("theme")
    def _apply_theme(self, event):
        if self.control is None:
            return

        palettes = {"Dark": _dark_preview_palette, "Light": _light_preview_palette}
        # An empty palette follows the app's, live theme switches included;
        # the cards are rebuilt in whichever it is.
        self.control.setPalette(palettes.get(self.theme, QtGui.QPalette)())


def _dark_preview_palette():
    """The app's dark palette, with the muted text and card edges it leaves
    to the platform."""
    palette = dark_palette()
    roles = QtGui.QPalette.ColorRole

    palette.setColor(roles.PlaceholderText, QtGui.QColor(GREY["lighter"]))
    palette.setColor(roles.Mid, QtGui.QColor(GREY["dark"]))

    return palette


def _light_preview_palette():
    """A light palette in Microdrop colours, whatever the platform's theme."""
    roles = QtGui.QPalette.ColorRole
    palette = QtGui.QPalette(QtGui.QColor(GREY["lightest"]))

    role_colors = {
        roles.Window: GREY["lightest"],
        roles.Base: WHITE,
        roles.Text: BLACK,
        roles.WindowText: BLACK,
        roles.PlaceholderText: GREY["dark"],
        roles.Mid: GREY["lighter"],
        roles.Link: INFO_COLOR,
    }

    for role, color in role_colors.items():
        palette.setColor(role, QtGui.QColor(color))

    return palette


class FeedPreviewEditor(BasicEditorFactory):
    """Preview a SciBotsFeed as the feed shows it."""

    klass = _FeedPreviewEditor

    #: The extended name of the theme trait.
    theme = Str()


PostFormView = View(
    VGroup(
        Item(
            "title",
            invalid="title_invalid",
            tooltip="One short line: the card's heading.",
        ),
        Item(
            "kind",
            label="Type",
            editor=EnumEditor(values=KIND_LABELS),
            invalid="kind_invalid",
            tooltip="What this is; it decides the group the post shows under.",
        ),
        Item(
            "date",
            editor=PopupDateEditor(),
            invalid="date_invalid",
            tooltip="When it was published. Click the arrow for a calendar.",
        ),
        Item(
            "month_only",
            label="Month only",
            tooltip="For newsletters: the card shows just the month, e.g. "
            "'September 2026'. The day is ignored.",
        ),
        Item(
            "summary_html",
            label="Summary",
            editor=RichTextEditor(),
            tooltip="A few sentences for the card. Select words to make them "
            "bold, italic or a link. Pasted text keeps no fonts or colours.",
        ),
        Item(
            "url",
            label="Link",
            invalid="url_invalid",
            tooltip="The web page 'Read more' opens, starting with https://",
        ),
        Item(
            "image",
            label="Picture",
            editor=FileEditor(filter=IMAGE_FILTER, dialog_style="open"),
            invalid="image_invalid",
            tooltip="Paste a web address (https://…) of a picture, or Browse "
            "for a file. Wide pictures show as a banner.",
        ),
        UItem("image_hint", style="readonly", visible_when="image_hint"),
        Item("pinned", tooltip="Pinned posts show first, under Top stories."),
        Item(
            "source",
            label="Source",
            tooltip="Optional: where it came from, e.g. LinkedIn.",
        ),
        Item(
            "has_expires",
            label="Expires",
            tooltip="Tick to hide the post from the feed after a date.",
        ),
        Item(
            "expires",
            label="Hide after",
            editor=PopupDateEditor(),
            enabled_when="has_expires",
        ),
    ),
)

posts_list = VGroup(
    UItem(
        "posts",
        editor=TableEditor(
            columns=[
                ObjectColumn(
                    name="list_title",
                    label="Post",
                    editable=False,
                    resize_mode="stretch",
                ),
                ObjectColumn(
                    name="list_date",
                    label="Date",
                    editable=False,
                    resize_mode="resize_to_contents",
                ),
            ],
            selected="selected",
            editable=False,
            sortable=False,
            auto_size=False,
        ),
        tooltip="The posts in the order the feed shows them: pinned first, "
        "then newest first.",
        width=POST_LIST_MIN_WIDTH,
    ),
    HGroup(
        UItem("add_button", tooltip="Add a new post"),
        UItem("duplicate_button", tooltip="Copy the selected post"),
        UItem("delete_button", tooltip="Delete the selected post"),
    ),
    label="Posts",
    show_border=True,
)

post_form = VGroup(
    UItem(
        "selected",
        style="custom",
        editor=InstanceEditor(view=PostFormView),
        visible_when="selected is not None",
    ),
    label="Post",
    show_border=True,
)

checks = VGroup(
    HGroup(UItem("checks_summary", style="readonly"), spring),
    UItem(
        "check_lines",
        editor=ListStrEditor(editable=False, selected_index="selected_check_index"),
        tooltip="Click a problem to go to its post. Errors must be fixed "
        "before saving; warnings are advice.",
        height=-150,
    ),
    label="Checks",
    show_border=True,
)

preview = VGroup(
    Item("preview_theme", label="Show in"),
    UItem("object.preview.posts", editor=FeedPreviewEditor(theme="preview_theme")),
    label="Preview",
    show_border=True,
)

FeedCreatorView = View(
    VGroup(
        HGroup(
            UItem("new_button", tooltip="Start an empty feed file"),
            UItem("open_button", tooltip="Open a feed file"),
            UItem("save_button", tooltip="Save the feed file"),
            UItem("save_as_button", tooltip="Save the feed file under a new name"),
            spring,
            UItem(
                "send_button",
                visible_when="can_send",
                tooltip="Show these posts in the demo's feed now",
            ),
        ),
        HSplit(
            posts_list,
            VSplit(post_form, checks),
            preview,
        ),
        UItem("status", style="readonly", visible_when="status"),
    ),
    title="Sci-Bots Feed creator",
    resizable=True,
    width=1440,
    height=900,
)
