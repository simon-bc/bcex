Blockchain.com Exchange python client
=====================================

Code formatting
---------------

Install the python package `pre-commit`. This should probably be done in a
non-virtualenv specific manner (i.e. using `pipsi`)

```pipsi install pre-commit ```

```pipsi install black```

After the repo has cloned run
```pre-commit install``` in the cloned directory. This will install the code
formatting hooks

To install blacken in your editor please see instructions
[https://github.com/ambv/black]

For documentation use NumPy style [https://numpydoc.readthedocs.io/en/latest/format.html]

Where possible also type annotate code [https://docs.python.org/3/library/typing.html#module-typing]