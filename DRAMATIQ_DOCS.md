# **Dramatiq Package Documentation**

## **Functions**

*Dramatiq.get_broker()* -> (Type: Broker) - Gets the global broker instance.

    If no global broker is set, a RabbitMQ broker will be returned. If the RabbitMQ dependencies are not installed, a Redis broker will be returned.

*Dramatiq.set_broker(broker: Broker)* -> None - Sets the global broker instance.

*Dramatiq.get_encoder()* -> (Type: Encoder) - Gets the global encoder instance.

    Default encoder is JSONEncoder. Other option is PickleEncoder. Base class has decode and encode methods.

*Dramatiq.set_encoder(encoder: Encoder)* -> None - Sets the global encoder instance.

## **Actors & Messages**

### *Overview*

Documentation on how to use Dramatiq for creating and managing actors and messages in an asynchronous task processing system. Dramatiq actors are callable objects that store metadata about how tasks should be executed asynchronously.

### Declaring an Actor

To declare an actor, use the `dramatiq.actor` decorator.

### Example

```
import dramatiq

@dramatiq.actor
def add(x, y):
    print(x + y)

# Using the actor
add(1, 2)  # Synchronously calls the function and prints 3
add.send(1, 2)  # Asynchronously sends a message to the actor
```

### Parameters

- `fn (callable)`: The function to wrap.
- `actor_class (type)`: The type created by the decorator. Defaults to `Actor`.
- `actor_name (str)`: The name of the actor.
- `queue_name (str)`: The name of the queue to use.
- `priority (int)`: The actor’s global priority.
- `broker (Broker)`: The broker to use with this actor.
- `**options`: Arbitrary options that vary with the set of middleware you use.

### Returns

- `Actor`: The decorated function.

## Actor Class

The `Actor` class is a thin wrapper around callables that stores metadata about how they should be executed asynchronously.

### Attributes

- `logger (Logger)`: The actor’s logger.
- `fn (callable)`: The underlying callable.
- `broker (Broker)`: The broker this actor is bound to.
- `actor_name (str)`: The actor’s name.
- `queue_name (str)`: The actor’s queue.
- `priority (int)`: The actor’s priority.
- `options (dict)`: Arbitrary options that are passed to the broker and middleware.

### Methods

#### `message(*args, **kwargs) -> Message`

Build a message. Useful for composing actors.

```
msg = add.message(1, 2)
```

#### `message_with_options(*, args=(), kwargs=None, **options) -> Message`

Build a message with arbitrary processing options.

```
msg = add.message_with_options(args=(1, 2), delay=1000)
```

#### `send(*args, **kwargs) -> Message`

Asynchronously send a message to this actor.

```
msg = add.send(1, 2)
```

#### `send_with_options(*, args=(), kwargs=None, delay=None, **options) -> Message`

Asynchronously send a message with arbitrary processing options.

```
msg = add.send_with_options(args=(1, 2), delay=1000)
```

## Message Class

Encapsulates metadata about messages being sent to individual actors.

### Parameters

- `queue_name (str)`: The name of the queue the message belongs to.
- `actor_name (str)`: The name of the actor that will receive the message.
- `args (tuple)`: Positional arguments passed to the actor.
- `kwargs (dict)`: Keyword arguments passed to the actor.
- `options (dict)`: Arbitrary options passed to the broker and middleware.
- `message_id (str)`: A globally unique ID assigned to the actor.
- `message_timestamp (int)`: The UNIX timestamp in milliseconds when the message was first enqueued.

### Methods

#### `asdict() -> Dict[str, Any]`

Convert this message to a dictionary.

#### `copy(**attributes) -> Message`

Create a copy of this message.

#### `classmethod decode(data: bytes) -> Message`

Convert a bytestring to a message.

#### `encode() -> bytes`

Convert this message to a bytestring.

#### `get_result(*, backend=None, block=False, timeout=None) -> Any`

Get the result associated with this message from a result backend.

## Group and Pipeline

### Group

Run a group of actors in parallel.

#### Methods

- `add_completion_callback(message)`
- `property completed`
- `property completed_count`
- `get_results(*, block=False, timeout=None)`
- `run(*, delay=None)`
- `wait(*, timeout=None)`

### Pipeline

Chain actors together, passing the result of one actor to the next one in line.

#### Methods

- `property completed`
- `property completed_count`
- `get_result(*, block=False, timeout=None)`
- `get_results(*, block=False, timeout=None)`
- `run(*, delay=None)`

## Usage Examples

### Declaring and Using an Actor

```
import dramatiq

@dramatiq.actor
def add(x, y):
    return x + y

# Synchronously call the function
add(1, 2)

# Asynchronously send a message to the actor
add.send(1, 2)
```

### Creating and Sending Messages

```
# Create a message
msg = add.message(1, 2)

# Send a message with options
msg = add.send_with_options(args=(1, 2), delay=1000)
```

### Using Groups and Pipelines

```
import dramatiq

@dramatiq.actor
def task1():
    pass

@dramatiq.actor
def task2():
    pass

# Create a group
group = dramatiq.group([task1.message(), task2.message()])

# Run the group
group.run()

# Create a pipeline
pipeline = dramatiq.pipeline([task1.message(), task2.message()])

# Run the pipeline
pipeline.run()
```

