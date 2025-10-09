from traitsui.api import Item, Group, Label


def create_traitsui_labeled_item_group(
    item_name: str,
    label_text: str = None,
    orientation: str = 'horizontal',
    label_position: str = 'first',
        **kwargs
) -> Group:
    """
    Creates a Group containing an item and its label, with configurable
    orientation and order.

    Args:
        item_name: The name of the model attribute to display.
        label_text: The text to display next to the item. Optional.
        orientation: The layout direction, either 'horizontal' or 'vertical'.
        label_position: The order of the label relative to the item,
                       either 'first' or 'last'.
        kwargs: Additional keyword arguments passed for Group initialization.

    Returns:
        An HGroup or VGroup object configured for the labeled item.
    """
    if label_text is None:
        label_text = item_name.replace('_', ' ').capitalize()

    # Select the group class based on the orientation
    if orientation.lower() not in ['horizontal', 'vertical']:
        raise ValueError("Orientation must be 'horizontal' or 'vertical'")

    # Determine the order of the item and label
    item = Item(item_name)
    label = Label(label_text)
    if label_position.lower() == 'first':
        group_contents = (label, item)
    elif label_position.lower() == 'last':
        group_contents = (item, label)
    else:
        raise ValueError("item_position must be 'first' or 'last'")

    # Unpack the contents tuple into the GroupClass constructor
    return Group(*group_contents, orientation=orientation, **kwargs)