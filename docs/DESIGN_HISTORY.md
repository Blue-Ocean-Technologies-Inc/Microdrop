# Design History — Pre-Development Research & Technology Selection

> Archived from the original README. This documents the research and reasoning
> that led to MicroDrop-Next-Gen's technology stack (Envisage + Dramatiq +
> Redis). For the current architecture, see the
> [README](../README.md#architecture) and the in-app architecture presentation
> (`Help → MicroDrop Architecture`).

## Background

The original *MicroDrop* application suffered from a lack of regular
maintenance, resulting in poor portability and limited accessibility for
developers. **MicroDrop-Next-Gen** was designed from scratch around modern,
maintained technologies, with future development in mind. The tables and notes
below record the options evaluated and why each was kept or rejected.

## Technologies Evaluated

| Technology | Category | Verdict |
|---|---|:---:|
| **Redis** | Message broker | ✅ |
| **Envisage** | Plugin architecture framework | ✅ |
| **Dramatiq** | Messaging / task processing | ✅ |
| Celery | Message broker | ❌ |
| RabbitMQ | Message broker | ❌ |
| ZMQ | Messaging backend | ❌ |
| Pika | Pure-Python RabbitMQ client | ❌ |
| AIO-Pika | Async RabbitMQ client | ❌ |
| APScheduler | Task execution scheduler | ❌ |
| FastAPI | Web framework for APIs | ❌ |
| FastAPI WebSockets | WebSockets for FastAPI | ❌ |
| FastStream | Python async service framework | ❌ |
| QWebSockets | Qt WebSockets | ❌ |
| Pluggy | Plugin architecture framework | ❌ |

## Technology Selection Reasoning

### Messaging Brokers

Messaging brokers facilitate messaging between different components of an
application. In our case they help achieve the following:

1. **Decoupling** — components communicate without being directly connected.
   External tasks can be completed without giving complete direct access to
   all related components.
2. **Asynchronous communication** — components send messages and continue
   working without blocking on responses, keeping the application responsive.
3. **Routing** — brokers provide ways to deliver messages to specific
   recipients (e.g. fanout and direct exchanges).
4. **Reliability** — messages that are not properly received must be re-sent
   until delivery is confirmed.

#### Our Choices (Messaging Brokers)

**Celery** was our initial option. The main problem with Celery is its poor
support for Windows, which is a requirement for our use case.

**ZMQ** was another option, but in terms of messaging, tooling, and support
via auxiliary packages it was easier to use a full message broker like Redis
over just the ZMQ framework.

**RabbitMQ** was initially chosen since it had a great amount of support for
auxiliary packages (Pika, AIO-Pika, FastAPI, Dramatiq, …) and achieves all
four goals above: fully decoupled components, async messaging, routing via
queue exchange methods, and reliability via acknowledgements and re-delivery.
But installing it was complicated and needed more external installations,
like Erlang.

So we pivoted to **Redis**, which is more lightweight and offers comparable
features. Most importantly, it can be installed using conda packages alone.
For storing publisher/subscriber data we also use the efficient Redis
in-memory key–value database.

Our code is nevertheless written against a **Dramatiq** broker abstraction
that works with either a RabbitMQ or Redis backend — it chooses whichever
broker is available — so a pivot back to RabbitMQ remains possible.

### Frameworks

Originally, MicroDrop used a plugin framework utilizing ZMQ and pyutilib for
plugin support. For MicroDrop-Next-Gen we retained the plugin model to
facilitate future development of plugin modules for use with the DropBot.
We chose **Envisage** as the framework to implement this plugin-supported
application: a robust and extensible framework designed for building
applications with dynamically loadable plugins. It provides a well-structured,
flexible environment that allows developers to add, remove, or update plugins
without altering the core application, keeping MicroDrop-Next-Gen
maintainable, scalable, and adaptable.

### Utility Packages (Dramatiq)

**Dramatiq** is a fast and reliable distributed task processing library for
Python, designed to process tasks in the background using message brokers
like RabbitMQ and Redis. It provides task scheduling, retries, and result
storage, making it an excellent choice for handling asynchronous tasks and
keeping the application responsive under complex workflows.

### Technologies Not Used

- **FastAPI** — an option for request/response handling, but since Dramatiq
  handles task processing and communication is local (not web requests),
  FastAPI was unnecessary.
- **QWebSockets** — a Qt-specific WebSockets package; not used for the same
  reason as FastAPI.
- **Pluggy** — we chose Envisage over Pluggy since Pluggy's framework was
  more complex in usage, and the five stages of plugin development
  (Discovery, Loading, Instantiation, Registration, Execution) are better
  defined and more straightforward to implement in Envisage.
- **FastStream** — only a candidate if FastAPI had been our communication
  method; Dramatiq was chosen instead.
- **FastAPI WebSockets** — not used since FastAPI was not used.
- **APScheduler** — Dramatiq covers task processing, and step
  processing/control flow is handled via messaging and the model structure
  (e.g. protocol grid → each step → left-to-right order).
