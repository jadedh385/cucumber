"""One log line per refusal (U0.10a §9.2, AC17).

A filter on the console handler, which `django` and the root logger share:

| Record                                         | Becomes                       |
|------------------------------------------------|-------------------------------|
| `django.request` 403                           | dropped (Cucumber's line)     |
| any `django.*` record for another 4xx          | kept, `exc_info` removed      |
| a request marked busy (core/busy.py)           | dropped (the `busy` line)     |
| 500 and other 5xx, and every other record      | kept as it is                 |

A kept record whose traceback is removed is a copy: the original record is
left as it was for any other handler.
"""

import copy
import logging
from http import HTTPStatus

from cucumber.core.busy import is_marked_busy


class OneLinePerRefusal(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        """False to drop; the record, or a copy without `exc_info`, to keep."""
        status = getattr(record, "status_code", None)
        if not record.name.startswith("django.") or status is None:
            return True
        if is_marked_busy(getattr(record, "request", None)):
            return False
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            return True
        if record.name == "django.request" and status == HTTPStatus.FORBIDDEN:
            return False
        if status < HTTPStatus.BAD_REQUEST:
            return True
        one_line = copy.copy(record)
        one_line.exc_info = None
        one_line.exc_text = None
        return one_line
