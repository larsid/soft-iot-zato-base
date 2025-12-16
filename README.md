# Zato project blueprint

This repository provides a blueprint structure for deploying Zato integration projects using DevOps practices.

## What this is

This is a sample project structure that demonstrates how to organize and deploy Zato projects from git to Docker containers.
It serves as a template for building your own provisioning scripts and managing Zato environments across development, testing, and production.

## What you'll learn

* How to structure your Zato projects with proper separation of code, configuration, and credentials
* Where to keep your Zato services and how to organize them
* How to use enmasse files (YAML) to define and version-control your configuration
* How to pass passwords and credentials securely using environment variables
* How to install Python dependencies and manage custom configuration files
* How to create reproducible builds that persist when containers restart
* How to configure SSL/TLS

## Project structure

```
myproject
├── config
│   ├── enmasse
│   │   └── enmasse.yaml       # Configuration definitions (REST channels, security, etc.)
│   ├── python-reqs
│   │   └── requirements.txt   # Python dependencies from PyPI
│   └── user-conf
│       └── myproject.ini      # Custom configuration for fast RAM access
└── impl
    ├── scripts
    │   └── run-container.sh   # Blueprint provisioning script
    └── src
        └── api                # Your Zato services go here
            ├── billing.py
            └── employee.py
```

## Getting started

Follow the complete [DevOps deployment tutorial](https://zato.io/en/tutorials/devops/deployment.html) to learn how to use this blueprint for your own projects.
