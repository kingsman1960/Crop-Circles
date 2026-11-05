"""Every page renders for every field and language without an exception. Run from the repo root: python app/smoke_test.py"""
from streamlit.testing.v1 import AppTest

from i18n import available

PAGES = ["views/home.py", "views/field.py", "views/strategies.py", "views/landscape.py", "views/sources.py"]

for page in PAGES:
    for field in ["F1", "F2", "F3"] if page in ("views/field.py", "views/strategies.py") else ["F1"]:
        for tag in available():
            at = AppTest.from_file("app.py", default_timeout=120)
            at.query_params["field"], at.query_params["lang"] = field, tag
            at.switch_page(page).run()
            assert not at.exception, f"{page} {field} {tag}: {at.exception}"
            print(f"ok  {page} {field} {tag}")
