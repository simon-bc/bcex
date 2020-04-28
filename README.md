Blockchain.com Exchange python client
=====================================
[![PyPi](https://img.shields.io/pypi/v/bcex.svg)](https://pypi.python.org/pypi/bcex)
![Python](https://img.shields.io/badge/Python-3.6+-green.svg)

This is a sample python client to connect to the [Blockchain.com Exchange](https://exchange.blockchain.com).

In order to use the authenticated channels you will need to create an account on the exchange and generate an [API secret](https://exchange.blockchain.com/settings/api). You can then either pass the API secret to the client or you can store it as an enviroment variable BCEX_API_SECRET.

To obtain access to staging environment, request to our support center needs to be made.

The best starting place is to look at some of the [examples](https://github.com/simon-bc/bcex/tree/master/examples)

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
