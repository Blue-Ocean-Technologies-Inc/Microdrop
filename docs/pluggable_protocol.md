InTake a look at some of the work that has been done on the pluggable protocol tree branch. You dont need to be following that too stringly. I want a greenfield approach.

Here are some requirements

Background:

The goal is to have a plugin provider inject the protocol grid controller with whatever columns they want. 
This provides an encapsulated column logic, that can ne plugged into the main protocol grid with ease. 
The columns would be independent, and editing them alone should become easy.

So what we need is something like this:

1. Model for a column:
    - Each column should have certain core information the plugin provider must declare:
      - Type, Name, Id, and whatever other traits that could be useful
    
    - This model shouyld be a traits object that can be contributed to as a service or just to a new extension point, whichever way is simplest. 
    - The core protocol grid plugin would have to recieve all of these, and use it to put together the protocool grid 

2. Row Manager:
    - The core protocol grid plugin should be able to manage the rows:
      - Copy
      - Paste
      - Cut
      - Select single row, range or rows, specific rows, and pull up their column data. 
      - Flattened indexing. Nested rows (inside a group from the top level) just get a indexing like [0,1] or doubl enested will be [0,1,1], top level would just be [0], [1], etc
      This row id column would just determine which level and which group a step belongs too. A group can also have an id just like this or not, plan what is a good way to make this work well.

3. Protocol Executor:
- Should async execute each of the columns based on instructions from the plugin provider. The way to do this is this:
  - Have each model declare some hooks: 
  - 1. Pre protocol, 2. Pre-step, 3. on-step, 4. post-step, 5. post-protocol
  - The hooks should be able to help the plugin provider instruct the executor on what to do when step needs to be done
  - Like for the voltage column, this means sending out a message to the dropbot backend to set a voltage. 

4. View:
- Similar to traitsui, just based on the type solely. The user could give hints maybe, like if its a float, specify the increment size for the spinner, decimals to show, etc. If its a bool, just checkbox, etc. 

5. Listener dramatiq:
Each  column given by the plugin provider, has the hooks methods. These may require in some cases a control flow involving dramatiq message reception. 
The message should have a decorator that declares the dramatiq Topic its completion is depending on, and the value to expect, and which attribute to set the value to. 
So for example:

## Plugin side
```python
@needs_dramatiq_reponse(topic="greet", attr=f"{plugin_id}_greeting_recieved")
def on_step_routine(parent):
    """A simple greeting function waiting for dramatiq message."""
    
    # send request
    publish_message(topic="greet", message="how are you")
    
    # wait for response
    while not parent.{plugin_id}_greeting_recieved:
        time.wait(0.1)
    
    response_msg = parent.{plugin_id}_greeting_recieved
    
    if response_msg == "good"
        return True
    
    else:
        return False
```

## Protocol Exector Side
- Compile all of hooks, and potential dramatiq attributes that may need to be set when hooks are executed. 

This is one theiry we have, maybe you can alswo think of better ways to do this control flow. 
But there needs to be a way to do this so that we dont just move on to the next hook without every task being completed even if its something that needs a dramatiq response from a backend or something. 



