from traitsui.api import View, Item

scale_edit_view = View(
    Item("electrode_scale", label=f"Electrode Area Scale (measured)", style="simple"),
    title="Adjust Electrode Area Scale",
    buttons=["OK", "Cancel"],
    resizable=True
)
