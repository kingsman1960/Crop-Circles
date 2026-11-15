"""Every page renders for every field and language without an exception. Run from the repo root: python app/smoke_test.py"""
from streamlit.testing.v1 import AppTest

import accounts
from i18n import available

PAGES = ["views/home.py", "views/field.py", "views/strategies.py", "views/landscape.py", "views/community.py", "views/sources.py"]

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
                    if len(at.text_input) == 2:  # the login card: sign in as admin, who sees every field
                        at.text_input[0].set_value("admin"), at.text_input[1].set_value(accounts.DEMO_PASSWORD), at.button[0].set_value(True)
                        at.run()
                    at.run()
                    for key, value in (("lang", tag), ("field", field)):
                        if any(b.key == key for b in at.button_group):
                            at.button_group(key=key).set_value(value).run()
                assert not at.exception, f"{page} {field} {scope} {tag}: {at.exception}"
                print(f"ok  {page} {field} {scope} {tag}: {at.subheader[0].value if at.subheader else at.title[0].value if at.title else "rendered"}")

# the login card: a platform page without a session shows it and nothing else; a wrong password is refused
at = AppTest.from_file("app.py", default_timeout=120)
at.query_params["lang"] = "en"
at.run()
at.switch_page("views/field.py").run()
at.button_group(key="lang").set_value("en").run()  # the AppTest quirk above
assert not at.exception and not at.title and len(at.text_input) == 2, f"login card expected: {at.exception}"
at.text_input[0].set_value("anna"), at.text_input[1].set_value("wrong"), at.button[0].set_value(True)  # a form: one run
at.run()
assert at.error and not at.title, "a wrong password must be refused"
at.text_input[0].set_value("anna"), at.text_input[1].set_value(accounts.DEMO_PASSWORD), at.button[0].set_value(True)
at.run()
assert not at.exception and at.subheader and at.session_state["field"] == "F1", f"anna should land on F1: {at.exception}"
assert not any(b.key == "field" for b in at.button_group), "a farmer with one field has no field switch"
print("ok  login card: wrong password refused, anna sees F1 and no field switch")
