"""Which series are in a profile's library.

A profile's library is what its own lists hold. The manager's also takes in
every series no list holds at all - imported PDFs, J-Novel Club volumes - which
are the manager's by default because no one else could have brought them in.

A SQL fragment rather than a function, because every screen that needs it is
one query and a second round trip per series would multiply with the library.
Correlated on `s.id`, so the query using it must alias series as `s`.
"""

from typing import Any

from app.profiles import Profile

IN_LIBRARY = """
(exists (select 1 from list_entry le
          where le.series_id = s.id and le.profile_id = :profile_id)
 or (cast(:is_manager as boolean)
     and not exists (select 1 from list_entry le where le.series_id = s.id)))
"""


def params(profile: Profile) -> dict[str, Any]:
    return {"profile_id": profile.id, "is_manager": profile.is_manager}
