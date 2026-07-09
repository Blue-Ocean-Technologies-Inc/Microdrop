![In Development](https://img.shields.io/badge/status-in_development-yellow)

# **Microdrop Documentation Guide**

## **Purpose**

*MicroDrop* is a graphical user interface designed for the DropBot Digital Microfluidics control system. The original *MicroDrop* application suffered from a lack of regular maintenance, resulting in poor portability and limited accessibility for developers. To address these issues, we introduce **MicroDrop-Next-Gen**, a modern application for running the DropBot Digital Microfluidics control system. This new version leverages updated technologies and is built with future development in mind. This document provides an overview of the design considerations, code documentation, current technology requirements, and installation instructions for **MicroDrop-Next-Gen**.

## **Disclaimer**

*Microdrop* is an open-source software platform currently in beta and is provided for testing and evaluation purposes. It is under active development and may contain bugs, errors, or unexpected behaviour.

Users are responsible for validating the software in their own workflows and for maintaining appropriate data backups before, during, and after use.

This software is provided under the GNU Affero General Public License (AGPLv3), without any warranty. Use at your own risk.

## **Research Pre-Development**
$$
\begin{array}{|l|l|l|l|l|l|l|l|}
\hline \text { Technology } & \text { Category } & \text{Platform Compatibility (Dev)} & \text{External Deps} & \text{Complexity} & \text{licensing} & \text{async} & \checkmark \text{/X } \\
\hline \text { Redis } & \text { Message Broker } & \checkmark \\
\hline \text { Celery } & \text { Message Broker } & \text { X } \\
\hline \text { RabbitMQ } & \text { Message Broker } & \text { X } \\
\hline \text { ZMQ } & \text { Messaging Backend } & \text { X } \\
\hline \text { Pika } & \text { Pure Python Client Library for RabbitMQ } & \text { X } \\
\hline \text { APScheduler } & \text { Task Execution Scheduler } & \text { X } \\
\hline \text { FastAPIWebsockets } & \text { WebSocket specifically for use with FastAPI } & \text { X } \\
\hline \text { AIO Pika } & \text { Async Client Library for RabbitMQ } & \text { X } \\
\hline \text { Envisage } & \text { Plugin Architecture Framework } & \checkmark \\
\hline \text { FastStream } & \text { Python Async Service Framework } & \text { X } \\
\hline \text { FastAPI } & \text { Web Framework for Implementing APIs } & \text { X } \\
\hline \text { QWebsockets } & \text { QT Websockets } & \text { X } \\
\hline \text { Dramatiq } & \text { Messaging System } & \checkmark \\
\hline \text { Pluggy } & \text { Plugin Architecture Framework } & \text { X } \\
\hline
\end{array}
$$


### **Technology Selection Reasoning**

#### *Messaging Brokers*
Messaging brokers are a tool used to facilitate messaging between different components of an application. In this case it helps to achieve the following:

1. **Decoupling** - By using message brokers, we can allow components to communicate without being directly connected. This allows external tasks to be completed without giving complete direct access to all related components.

2. **Asynchronous Communication** - Components can send messages to other components and continue completing tasks without needing responses to the messages that they send. This is useful when tasks do not need to be blocking, so that the application can run seamlessly.

3. **Routing** - Ensuring that messages get to the correct recipient is one of the most important tasks in communication. Brokers typically give us a way to share information with specific recipients in many different ways like 'fanout', and 'direct' exchanges.

4. **Reliability** - When determining which method of communication we use, the tool must make sure messages are reliably reaching their target. For example, if a message is sent, but is not properly received, the broker must make sure that the message is re-sent and achieves proper delivery.

##### *Our Choices (Messaging Brokers)*

**Celery** was our initial option. The main problem with **Celery** is that they have poor support for windows which is a requirement for our use case.

**ZMQ** was another option, but we determined that in terms of messaging and use of the technical tool and further support via other auxiliary tools, it was easier to use a full message broker like **Redis** over just the **ZMQ** framework.

**RabbitMQ** was initially chosen since it had a great amount of support for auxiliary packages like **Pika**, **AIO-Pika**, **FastAPI**, **Dramatiq** **etc...** In addition, **RabbitMQ** achieves all 4 of the above goals. It allows for fully decoupled components, async messaging, routing methods that are defined in queue exchange methods, and reliability is all ensured via acknowledgements and resending of messages based on lack of acknowledgements. But installing it was complicated, and needed more external installations, like the need for Erlang. 

So we pivoted to using **Redis** which is more lightweight, and offers comparible features. Most importantly, it can be installed just using conda packages. For storing publisher subcriber data, we also use the efficient redis in-memory key–value database. If there is a need to pivot to **RabbitMQ**, this needs a replacement.

However our code is written in a way that it can work with either a **RabbitMQ** or **Redis** backend since we are using a **Dramatiq** broker abstraction.
This will choose whichever broker is available.

#### *Frameworks*

Originally, MicroDrop used a plugin framework, utilizing ZMQ and pyutilib for plugin support. For MicroDrop-Next-Gen, we have decided to retain the plugin model to facilitate future development of plugin modules for use with the DropBot. We have chosen Envisage as the framework to implement this plugin-supported application. Envisage is a robust and extensible framework designed for building applications with dynamically loadable plugins. It provides a well-structured and flexible environment that allows developers to add, remove, or update plugins without altering the core application. This choice will ensure that MicroDrop-Next-Gen remains maintainable, scalable, and adaptable to new technologies and requirements as they arise.

#### *Utility Packages (Dramatiq)*

Dramatiq is a fast and reliable distributed task processing library for Python. It is designed to process tasks in the background using message brokers like RabbitMQ and Redis. It provides support for task scheduling, retries, and result storage, making it an excellent choice for handling asynchronous tasks in MicroDrop-Next-Gen. By integrating Dramatiq, we can ensure that our application remains responsive and capable of handling complex workflows efficiently.

#### *Not Used Technologies*

*FastAPI* - an option for request and response handling but since we decided that it made more sense to use **Dramatiq** for task processing and not use web requests (only local) for task handling, we decided to not use **FastAPI**.

*QWebsockets* - a QT specific websockets package. Not used for the same reason above.

*Pluggy* - a plugin architecture framework. We decided to use **Envisage** over **pluggy** since **pluggy**'s framework was more complex in usage and the tasks we needed from a plugin framework is better defined and implemented via **Envisage**. Envisage allowed us to implement the 5 stages of plugin development (Discovery, Loading, Instantiation, Registration, and Execution) in a more straightforward manner.

*FastStream* - a python async service framework. Not used since **Dramatiq** was chosen for task processing and this was only going to be thought of as an option if we used FastAPI as our communication method.

*FastAPIWebsockets* - a websockets package specifically for use with FastAPI. Not used since we decided to not use **FastAPI**.

*APScheduler* - a task execution scheduler. Not used since **Dramatiq** was chosen for task processing and we can handle task scheduling via **Dramatiq** information flow or if we choose, we can implement custom APScheduler's to handle step processing. As of current, it seems that development for step processing and control flow will be handled via communication and model structure (EX: Protocol Grid -> each step -> left to right order).

## **Installation Instructions**

### **Prerequisites**

1. **Python 3.12** 

We are using redis since it can be installed from the binstar anaconda channel.

simply use the environment.yml from this repos root directory to create a conda environment with the necessary dependencies.
The command to create the environment is:
```conda create -f environment.yml```

And remember to startup the redis server. There is a start_redis_server.py python script for thisnin examples. Or one can just ruin ``redis-server`` on a terminal.

## **Running the Application**

Redis must be running before launching (see above).

The combined launcher `examples/run_device_viewer_pluggable.py` can load any
combination of plugin layers via `--plugins`, so a single script covers the
full app, frontend-only, or backend-only runs:

```bash
# Full app — frontend + backend (the default)
python examples/run_device_viewer_pluggable.py

# Frontend (GUI) only — needs Redis + a backend running separately
python examples/run_device_viewer_pluggable.py --plugins frontend

# Backend only — persistent headless process, connects to an existing Redis
python examples/run_device_viewer_pluggable.py --plugins backend

# Any combination, with a device selection
python examples/run_device_viewer_pluggable.py --plugins backend services --device mock
```

`--plugins` accepts one or more space-separated values from `frontend`,
`backend`, and `services`, defaulting to `frontend backend`. Notes:

- **Services** (e.g. SSH controls) are trust-bound to the GUI host, so they
  load automatically with `frontend`, or on explicit `services` request.
- Selecting `frontend` runs the GUI application; a backend-only selection runs
  the persistent headless backend application.
- The **frontend host owns the Redis server**; a backend-only run instead
  connects to an already-running Redis (use this for a remote backend host).

`--device` selects the hardware target (`dropbot`, `opendrop`, or `mock`;
default `dropbot`) and pulls in the matching device-specific plugins.

# **Remote Microdrop Instructions**

## **1. SERVER-SIDE (via SSH)**

- Start your Redis server (see Redis configuration note below).

- Run the backend script by executing: pixi run microdrop-backend

## **2. CLIENT-SIDE (Local Machine)**
- Headless: Send commands using publish_message(message, topic).
- GUI: Run pixi run microdrop-frontend to use the visual interface to send commands.

## **Redis Configuration Note**

### **On the Redis server machine:** 

- Ensure the Redis server is configured to accept external connections.
- This means binding to the correct network adapter in the redis.conf file, and disabling protected mode if applicable.
- This Redis server can actually run anywhere; it does not need to be on the exact same machine as the microdrop-backend script.

### **On each client machine (frontend/backend):** 
- Tell the application where to find the Redis server by editing the redis_settings.json (you can copy the template [redis_settings.example.json](https://github.com/Blue-Ocean-Technologies-Inc/Microdrop/blob/main/redis_settings.example.json))
- Set the host to the Redis server's IP and the port to match.

# **Developer Workflow**

## **Commit Messages (Conventional Commits)**

Every commit message must follow the
[Conventional Commits](https://www.conventionalcommits.org/) format — a CI
check ([conventional-commits.yml](.github/workflows/conventional-commits.yml))
runs `cz check` on every PR commit, so non-conforming messages block the merge.
The format matters because releases are derived from it: commitizen reads the
commit history to compute the next version number and generate the changelog
(see [Releases & CHANGELOG.md](#releases--changelogmd) below).

```
type(scope): subject

optional body explaining why and what

optional footer (e.g. BREAKING CHANGE: ...)
```

- **Types:** `feat` (new feature → minor bump), `fix` (bug fix → patch bump),
  `refactor`, `perf`, `docs`, `ci`, `chore`, `test`.
- **Scope** is optional but encouraged — use the plugin/package name, e.g.
  `feat(device_viewer): add electrode search`.
- **Breaking changes:** append `!` after the type/scope
  (`feat(api)!: drop legacy topics`) or add a `BREAKING CHANGE:` footer →
  major bump.
- Keep the subject imperative and ~50 characters; put the why/what in the body.

Examples:

```
feat(dropbot_controller): add short-detection retry
fix(protocol_grid): preserve step order on paste
docs: add developer workflow section to README
chore: release v1.1.0
```

### **Setup: enforce the convention locally**

The repo ships a [pre-commit](https://pre-commit.com/) config
([.pre-commit-config.yaml](.pre-commit-config.yaml)) that installs git hooks
enforcing the format at commit time, so mistakes are caught before CI.

**If you develop through the
[pixi-microdrop](https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop)
repo** (the pixi environment that carries this repo as the `src/` submodule),
this is a one-time command per clone, run from the outer `microdrop-py/`
directory:

```bash
pixi run setup-hooks
```

This installs the hooks into this repo **and** the plugin clones
(heater / magnet / fluorescence).

**Without pixi**, install `pre-commit` yourself (e.g.
`pipx install pre-commit` or `pip install pre-commit`) and run this once
inside each repo clone:

```bash
pre-commit install --hook-type commit-msg --hook-type pre-commit
```

If you prefer to be prompted instead of writing the message yourself,
commitizen can compose a conforming message interactively:

```bash
# via pixi-microdrop (no install needed)
pixi exec --spec "commitizen>=4,<5" -- cz commit

# without pixi (after `pipx install "commitizen>=4,<5"`)
cz commit
```

## **Git Hooks**

The setup above (`pixi run setup-hooks`, or the manual `pre-commit install`)
wires two kinds of hooks (defined in
[.pre-commit-config.yaml](.pre-commit-config.yaml)); they run automatically on
every `git commit`:

**commit-msg hook** (runs on the message):

| Hook | What it does |
|---|---|
| `commitizen` | Rejects the commit if the message isn't valid Conventional Commits — the local mirror of the CI gate. |

**pre-commit hooks** (run on the staged files):

| Hook | What it does |
|---|---|
| `check-ast` | Staged `.py` files must parse (catches syntax errors before they land). |
| `check-merge-conflict` | Blocks files containing leftover merge-conflict markers. |
| `check-added-large-files` | Blocks files larger than 500 kB. |
| `forbid-scratch-files` | Blocks scratch/artifact paths (`__pycache__/`, `.pixi/`, `.task-report.md`, `.superpowers/`) from ever being committed. |

Useful commands:

```bash
# Run all file hooks against the whole repo (not just staged files)
pre-commit run --all-files

# A failed hook aborts the commit — fix the issue (or the message) and retry.
# In a genuine emergency a hook can be bypassed with `git commit --no-verify`,
# but the CI check will still fail the PR, so fix the message instead.
```

## **Releases & CHANGELOG.md**

[CHANGELOG.md](CHANGELOG.md) is **generated, never hand-edited**. Commitizen
(configured in [.cz.toml](.cz.toml)) builds it from the Conventional Commit
history:

- The version lives in **git tags only** (`version_provider = "scm"`, tags
  formatted `vX.Y.Z`) — there is no version string in the source to bump.
- `cz bump` looks at all commits since the last `v*` tag, derives the bump
  (`feat` → minor, `fix` → patch, `BREAKING CHANGE`/`!` → major), rewrites
  CHANGELOG.md with sections grouped by type (Feat / Fix / Refactor / ...),
  commits it as `chore: release vX.Y.Z`, and creates an annotated tag.
- Commit **scopes** become the bold prefixes in changelog entries
  (e.g. `- **plugin-management**: full Manage Plugins window`), which is why
  meaningful scopes are worth writing.

Cutting a release (maintainers, from an up-to-date `main`):

```bash
# via pixi-microdrop
pixi exec --spec "commitizen>=4,<5" -- cz bump

# without pixi (after `pipx install "commitizen>=4,<5"`)
cz bump

# then, either way (requires branch-protection bypass, i.e. an admin):
git push origin main --follow-tags
```

The related **heater/magnet plugin repos** release fully automatically: every
push to `main` containing release-worthy conventional commits bumps the
version, regenerates their CHANGELOG.md, publishes the conda package to
`prefix.dev/microdrop-plugins`, and tags — no manual `cz bump` needed there.

