from traitsui.api import View, Item

scale_edit_view = View(
    Item("electrode_scale", label="Electrode Area Scale (pixels:mm)", style="simple"),
    title="Adjust Electrode Area Scale",
    buttons=["OK", "Cancel"],
    resizable=True
)