from traitsui.menu import Menu, Action
 
RouteLayerMenu = Menu(
    Action(name="Invert", action="invert_layer"),
    Action(name="Delete", action="delete_layer"),
    Action(name="Start Merge", action="start_merge_layer", visible_when="not object.merge_in_progress"), # Note that object in this case refers to the RouteLayer clicked on! No easy way to access main model
    Action(name="Merge With", action="merge_layer", visible_when="object.merge_in_progress"),
    Action(name="Stop Merging", action="cancel_merge_layer", visible_when="object.merge_in_progress")
)