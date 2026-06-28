# AGENTS.md

## Purpose

This project is a Flask backend that follows a layered architecture. When making changes, prefer working within the existing structure instead of introducing new architectural patterns.

The goal is to produce code that is:

* Easy to understand
* Easy to debug
* Easy to test
* Consistent with the existing project
* Pythonic without unnecessary abstraction

---

# Project Structure

Unless explicitly requested otherwise, follow this structure.

```
app/ 
├── routes/ # HTTP endpoints and request handling 
├── services/ # Business logic 
├── models/ # Database models 
├── config/ # Configuration and initialization
```

Do **not** reorganize the project into a completely different architecture (Clean Architecture, Hexagonal Architecture, Domain Driven Design, etc.) unless explicitly asked.

Work within the current folder structure.

---

# Responsibilities

## Routes

Routes should be thin.

Responsibilities include:

* Parsing request parameters
* Input validation (or delegating to validators)
* Authentication/authorization
* Calling services
* Returning HTTP responses

Routes should **not** contain business logic.

Avoid:

* Database queries
* Complex conditionals
* Large loops
* Business rules

A route should generally read like:

```
Receive request
↓

Validate input
↓

Call service
↓

Return response
```

---

## Services

Services contain business logic.

A service may:

* Coordinate multiple models
* Perform validations
* Handle transactions
* Call external APIs
* Apply business rules

Services should not know about Flask request objects.

Prefer passing plain Python values rather than Flask globals.

---

## Models (db.py)

Models are responsible for representing persistent data.

Models should contain:

Table definitions
Relationships
Small model-specific helper methods

Avoid placing business workflows inside models.

---

## Config

Configuration belongs in the config/ directory.

Examples include:

Flask configuration
Extensions
Logging setup
Database initialization

Do not scatter configuration throughout the project.

Do not scatter configuration parsing throughout other files.

---

# Function Size

Keep functions reasonably small.

As a guideline:

* Aim for roughly **20–40 lines**.
* If a function exceeds **50–60 lines**, consider splitting it.
* If scrolling is required to understand a function, it is probably doing too much.

Large functions are harder to:

* Debug
* Review
* Test
* Reuse

Extract meaningful helper functions instead of creating deeply nested code.

---

# Complexity

Prefer reducing complexity over reducing line count.

Avoid:

* Deep nesting
* Long chains of `if/elif`
* Large `try/except` blocks
* Massive functions
* Excessive boolean expressions

Prefer:

* Early returns
* Small helper functions
* Clear naming
* Simple control flow

---

# Error Handling

Raise meaningful exceptions.

Do not silently ignore errors.

Avoid:

```python
except Exception:
    pass
```

Catch only the exceptions you expect.

Provide useful logging where appropriate.

---

# Database Access

Database interactions should be centralized.

Avoid performing queries directly inside routes.

Keep transactions contained within service functions when possible.

---

# Naming

Use descriptive names.

Prefer:

```python
create_user()

calculate_total()

generate_access_token()
```

Instead of:

```python
do()

handle()

process()

func()
```

Variable names should explain intent.

---

# Python Style

Follow standard Python conventions.

Prefer:

* Small functions
* Type hints where practical
* f-strings
* Context managers
* Enumerations instead of magic values
* Constants for repeated literals

Avoid unnecessary cleverness.

Code should be readable before it is concise.

---

# Flask Best Practices

Prefer:

* Blueprints
* Application factory pattern (if already used)
* Configuration via environment variables
* Flask extensions initialized centrally

Avoid:

* Global mutable state
* Circular imports
* Business logic inside Flask views

---

# Logging

Use logging for important events and failures.

Do not use `print()` for debugging in committed code.

Log:

* Unexpected failures
* External API failures
* Database failures
* Authentication failures

Avoid logging secrets or sensitive information.

---

# Imports

Group imports as:

1. Standard library
2. Third-party packages
3. Local project imports

Remove unused imports.

Avoid wildcard imports.

---

# Code Duplication

If logic is repeated more than twice, consider extracting it into a helper or service.

Do not over-engineer abstractions for code that is only used once.

---

# Dependencies

Before introducing a new dependency:

* Prefer the standard library when reasonable.
* Reuse existing project dependencies where possible.
* Add new libraries only when they provide clear value.

Do not introduce heavy frameworks for small problems.

---

# Backward Compatibility

Do not change:

* Folder structure
* Public APIs
* Existing interfaces
* Configuration layout

unless explicitly requested.

Prefer incremental improvements over large refactors.

---

# When Modifying Existing Code

Respect the existing style unless it is clearly problematic.

Improve code incrementally rather than rewriting unrelated sections.

Avoid unnecessary formatting-only changes.

Keep pull requests focused.

Make changes to ARCHITECTURE.md if needed.

If new packages used, add them to requirements.txt.

If a new env variable has been added, add it to .env.example as well.

---

# General Philosophy

When making implementation decisions, prioritize:

1. Correctness
2. Readability
3. Maintainability
4. Simplicity
5. Performance (only where it matters)

Prefer boring, predictable code over clever solutions.

The best code is code that another developer can understand quickly and confidently modify months later.
