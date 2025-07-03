# Device Viewer Plugin

This plugin acts as an editor/graphical display for operations on electrodes. It supports toggling electrode states, drawing/editing/erasing droplet routes, displaying states from other plugins (i.e. the protocol viewer while running a protocol) and undo/redo operations.

## Views

The entire view (views/device_view_pane.py) is a Qt layout with different implementations for each component (one per folder in views):
- electrode_view (QTGraphicsView, uses Shiboken Python bindings for a low-level graphics API)
- mode_picker (QWidget, quite standard)
- route_selection_view (TraitsUI TableEditor)

These are combined and passed the relevant references/models in device_view_pane.py's create_contents

## Models

I decided to keep the models seperate since I liked the seperation of concerns but they can totally be combined. The entire view operates on 2 models: one for electrodes/channel states, and another for routes and paths (which also include values assiciated with rendering the editor). In device_view_pane.py, these are called "electrodes_model" and "route_layer_manager" respectively.

The electrode models are quite simple. You only need to be aware that electrode channels are actually one-to-many with electrode ids (one channel can have many associate electrodes).

For the route_layer_manager, "route" refers to the actual abstract path, while the "layer" is its view. These are seperate as classes (see models/route.py) and I tried to keep my naming consistant throughout the code but there may be a few inconsistencies. For example, the color or visibility of a route is part of its layer, while the actual list of nodes (electrodes) it visites is part of its route.

## Controller

The main controller is called services/electrode_interaction_service.py. Its not an Envisage service of anything of special nature (though that could have been the original intent). In there some human-readable actions are defined, and how change the model. These should be called by the views/electrode_scene.py's Qt event listeners, turning it into a translation layer from Qt's 'events' to those meaningful to the application. There are also model listeners that force partial/total redraws of the view. I would recommend reading [the relevant documentation](https://docs.enthought.com/traits/traits_user_manual/notification.html#traits-mini-language) for how these listener strings are formatted.

## Undo/Redo

I decided to implement undo/redo using Traits listeners since all meaningful change was done through the model. I do this by setting listeners in views/device_viewer_pane.py and converting the ```event``` object traits gives its callbacks into a ```ICommand``` that the undo_manager expects. The relevant code for converting these events into Commands is in utils/commands.py. [This](https://docs.enthought.com/traits/traits_api_reference/traits.observation.html#module-traits.observation.events) page has been very useful in decoding how these event objects are structured and how one would undo the changes they describe.

If you aren't working with the undo/redo internals directly, the only thing to keep in mind is that when you are modifying a trait that's being listened to for undo/redo, each modification gets converted into an item on the stack. This means that
```
a.trait = True
a.trait = False
a.trait = True
```
is **not** the same as
```
a.trait = True
```
as the former would require 3 different undo calls to undo (which won't break anything, but is very annoying). Thus, when you can, try to have each logical action (like the actions defined in the controller) have around 1 modification to each of the traits it needs to modify. I decided to implement it this way since its really generalized, so adding another "undoable" value is as simple as adding an observer to model_change_handler.