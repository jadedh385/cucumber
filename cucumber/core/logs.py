"""One log line per refusal (U0.10a §9.2, AC17).

A filter on the console handler, which `django` and the root logger share:

| Record                                         | Becomes                       |
|------------------------------------------------|-------------------------------|
| `django.request` 403                           | dropped (Cucumber's line)     |
| any `django.*` record for another 4xx          | kept, `exc_info` removed      |
| a request marked busy (core/busy.py)           | dropped (the `busy` line)     |
| 500 and other 5xx, and every other record      | kept as it is                 |

A kept record whose traceback is removed is a copy: the original record is
left as it was for any other handler. G2 stub: the behaviour is built at G3.
"""

import logging


class OneLinePerRefusal(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        """False to drop; the record, or a copy without `exc_info`, to keep."""
        raise NotImplementedError("U0.10a G3")
