"""Every page renders for every field and language without an exception. Run from the repo root: python app/smoke_test.py"""
from streamlit.testing.v1 import AppTest

from i18n import available

PAGES = ["views/home.py", "views/field.py", "views/strategies.py", "views/landscape.py", "views/sources.py"]

for page in PAGES:
    for field in ["F1", "F2", "F3"] if page in ("views/field.py", "views/strategies.py") else ["F1"]:
        for scope in ["bbox", "bw"] if page == "views/landscape.py" else ["bbox"]:  # Our region: Kraichgau and all BW
            for tag in available():
                at = AppTest.from_file("app.py", default_timeout=120)
                at.query_params["field"], at.query_params["lang"] = field, tag
                at.session_state["ls_scope"] = scope
                at.run()
                if page != "views/home.py":
                    # AppTest finds a page with a custom url_path only after a first run (before, it silently shows
                    # the home page), and its first run of a platform page loses the language and field widgets'
                    # values: run once more, then set both on the widgets themselves
                    at.switch_page(page).run()
                    at.run()
                    for key, value in (("lang", tag), ("field", field)):
                        if any(b.key == key for b in at.button_group):
                            at.button_group(key=key).set_value(value).run()
                assert not at.exception, f"{page} {field} {scope} {tag}: {at.exception}"
                print(f"ok  {page} {field} {scope} {tag}: {at.subheader[0].value if at.subheader else at.title[0].value}")
