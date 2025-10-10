from typing import Tuple, Dict, Any, List
from traits.api import HasTraits, Str, Int, Bool
from traitsui.api import Group, Item, Label, View


def create_item_label_pair(
        item_name: str,
        label_text: str = None,
        label_position: str = 'first',
        **kwargs: Any
) -> Tuple[Label, Item] or Tuple[Item, Label]:
    """Creates a pair of TraitsUI Label and Item objects in a specified order.

    This helper function handles the creation of the core UI elements and the
    intelligent separation of keyword arguments intended for them.

    Args:
        item_name (str): The name of the model attribute for the Item.
        label_text (str, optional): Text for the label. If None, it is
            auto-generated from item_name. Defaults to None.
        label_position (str, optional): The order of the label relative to the
            item, either 'first' or 'last'. Defaults to 'first'.
        **kwargs: Keyword arguments for the Item and Label.
                  - Prefixed with `label_`: Passed to the `Label`.
                  - Prefixed with `item_` or no prefix: Passed to the `Item`.

    Returns:
        A tuple containing the configured Label and Item objects in order.

    Raises:
        ValueError: If `label_position` is an invalid value.
    """
    item_kwargs: Dict[str, Any] = {}
    label_kwargs: Dict[str, Any] = {}

    # Separate kwargs for the item and the label.
    for key, value in kwargs.items():
        if key.startswith("label_"):
            label_kwargs[key[len("label_"):]] = value
        elif key.startswith("item_"):
            item_kwargs[key[len("item_"):]] = value
        else:
            # Default any unprefixed arguments to the Item.
            item_kwargs[key] = value

    if label_text is None:
        label_text = item_name.replace('_', ' ').capitalize()

    item = Item(item_name, show_label=False, **item_kwargs)
    label = Label(label_text, **label_kwargs)

    if label_position.lower() == 'first':
        return (label, item)
    elif label_position.lower() == 'last':
        return (item, label)
    else:
        raise ValueError("label_position must be 'first' or 'last'")


def create_item_label_group(
        item_name: str,
        label_text: str = None,
        orientation: str = 'horizontal',
        label_position: str = 'first',
        **kwargs: Any
) -> Group:
    """Creates a TraitsUI Group containing a labeled item with flexible options.

    This function wraps the `create_item_label_pair` helper to place the
    resulting UI elements into a Group with a specified orientation.

    Args:
        item_name (str): The name of the model attribute.
        label_text (str, optional): The text for the label.
        orientation (str, optional): The layout direction ('horizontal' or 'vertical').
        label_position (str, optional): The position of the label ('first' or 'last').
        **kwargs: Keyword arguments for the child Item, Label, and the parent Group.
                  - Prefixed with `group_`: Passed to the `Group`.
                  - All other prefixes (`item_`, `label_`) or no prefix are
                    passed down to `create_item_label_pair`.

    Returns:
        A TraitsUI Group object configured with the item and label.

    Raises:
        ValueError: If `orientation` is an invalid value.
    """
    group_kwargs: Dict[str, Any] = {}
    other_kwargs: Dict[str, Any] = {}

    # Separate kwargs intended for the Group from those for the children.
    for key, value in kwargs.items():
        if key.startswith("group_"):
            group_kwargs[key[len("group_"):]] = value
        else:
            other_kwargs[key] = value

    # Get the ordered (label, item) tuple from the helper function.
    group_contents = create_item_label_pair(
        item_name=item_name,
        label_text=label_text,
        label_position=label_position,
        **other_kwargs
    )

    if orientation.lower() not in ['horizontal', 'vertical']:
        raise ValueError("Orientation must be 'horizontal' or 'vertical'")

    # Create and return the final Group.
    return Group(*group_contents, orientation=orientation, **group_kwargs)


def create_grid_group(items: List[str], **kwargs: Any) -> Group:
    """Creates a grid layout of labeled items in a two-column table.

    Args:
        items (List[str]): A list of the model attribute names to display.
        **kwargs: Keyword arguments for the parent `Group` and the child
                  `Item`/`Label` pairs.
                  - `group_*`: Passed to the parent `Group` (e.g., `group_label`).
                  - `item_*`, `label_*`, etc.: Passed to each child pair.

    Returns:
        A TraitsUI Group object configured as a grid.
    """
    group_kwargs: Dict[str, Any] = {}
    child_kwargs: Dict[str, Any] = {}

    # Separate kwargs for the parent Group from those for the children.
    for key, value in kwargs.items():
        if key.startswith("group_"):
            group_kwargs[key[len("group_"):]] = value
        else:
            child_kwargs[key] = value

    grid_contents = []
    for item_name in items:
        pair = create_item_label_pair(item_name, **child_kwargs)
        grid_contents.extend(pair)

    # Sensible defaults for a grid layout.
    grid_defaults = {'columns': 2, 'show_labels': False}
    final_group_kwargs = {**grid_defaults, **group_kwargs}

    return Group(*grid_contents, **final_group_kwargs)


def create_grid_view(items: List[str], **kwargs: Any) -> View:
    """Creates a TraitsUI View with a grid layout of labeled items.

    This function provides a complete View containing a two-column grid of
    settings, ideal for preferences dialogs.

    Args:
        items (List[str]): A list of the model attribute names to display.
        **kwargs: Keyword arguments for the `View`, the main `Group`, and the
                  child `Item`/`Label` pairs.
                  - `view_*`: Passed to the `View` (e.g., `view_title`).
                  - `group_*`: Passed to the main `Group`.
                  - Others: Passed to each child `Item`/`Label` pair.

    Returns:
        A TraitsUI View object configured with the grid.
    """
    view_kwargs: Dict[str, Any] = {}
    other_kwargs: Dict[str, Any] = {}

    # Separate kwargs for the View from all others.
    for key, value in kwargs.items():
        if key.startswith("view_"):
            view_kwargs[key[len("view_"):]] = value
        else:
            other_kwargs[key] = value

    grid_group = create_grid_group(items, **other_kwargs)

    # Sensible defaults for the view.
    view_defaults = {'buttons': ['OK', 'Cancel'], 'resizable': True}
    final_view_kwargs = {**view_defaults, **view_kwargs}

    return View(grid_group, **final_view_kwargs)


# --- Test Harness ---
if __name__ == "__main__":
    class TestHarness(HasTraits):
        """A simple class to demonstrate the UI helper functions."""
        # Define some traits to be used in the UI
        user_name = Str("J. Doe")
        user_age = Int(30)
        send_notifications = Bool(True)
        home_directory = Str("/home/user")


    # 1. Demonstrate create_item_label_pair (low-level helper)
    print("--- Demonstrating create_item_label_pair ---")
    pair = create_item_label_pair('user_name', label_text="Your Name:")
    print(f"Returned pair: {pair}")
    print("-" * 20 + "\n")

    # 2. Demonstrate create_labeled_group in a standalone view
    print("--- Demonstrating create_labeled_group ---")
    labeled_group_demo = TestHarness()
    labeled_group_demo.view = View(
        create_item_label_group(
            'send_notifications',
            orientation='horizontal',
            group_show_border=True,
            group_label="Notification Settings"
        ),
        title="Labeled Group Demo",
        buttons=['OK']
    )
    # To run this demo, uncomment the following line:
    # labeled_group_demo.configure_traits()
    print("A view for 'create_labeled_group' has been created but not shown.")
    print("-" * 20 + "\n")

    # 3. Demonstrate create_grid_view (the primary high-level function)
    print("--- Demonstrating create_grid_view ---")
    grid_view_demo = TestHarness()

    # List the traits we want to appear in our grid
    grid_items = [
        'user_name',
        'user_age',
        'send_notifications',
        'home_directory'
    ]

    # Use the helper to generate the entire View
    grid_view_demo.view = create_grid_view(
        grid_items,
        view_title="User Preferences",
        group_label="User Details",
        group_show_border=True,
        item_style='simple'  # This kwarg is passed down to all Items
    )

    print("Launching the main grid view demo...")
    grid_view_demo.configure_traits()
    print("Grid view demo closed.")

