![In Development](https://img.shields.io/badge/status-in_development-yellow)

# **Microdrop Documentation Guide**

## **Purpose**

*MicroDrop* is a graphical user interface designed for the DropBot Digital Microfluidics control system. The original *MicroDrop* application suffered from a lack of regular maintenance, resulting in poor portability and limited accessibility for developers. To address these issues, we introduce **MicroDrop-Next-Gen**, a modern application for running the DropBot Digital Microfluidics control system. This new version leverages updated technologies and is built with future development in mind. This document provides an overview of the design considerations, code documentation, current technology requirements, and installation instructions for **MicroDrop-Next-Gen**.


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
