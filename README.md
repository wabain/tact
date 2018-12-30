tact
====

A platform for n-dimensional tic-tac-toe.

CI
---

[![Build Status](https://travis-ci.org/wabain/tact.svg?branch=master)](https://travis-ci.org/wabain/tact)
[![Coverage Status](https://coveralls.io/repos/github/wabain/tact/badge.svg?branch=master)](https://coveralls.io/github/wabain/tact?branch=master)

Development
-----------

Setup:

```bash
$ python3 -m venv .venv-tact && source .venv-tact/bin/activate
$ python setup.py develop

# Test dependencies must be installed in the development environment to allow
# linting test code.
$ pip install tact[develop,testing]
```

Run `scripts/precommit.py` to check your commit prior to merging.
