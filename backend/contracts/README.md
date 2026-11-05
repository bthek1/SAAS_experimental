# Service contracts (#13)

What `catalog` and `instances` say to each other over `/internal/`. Both test suites read these files: `catalog` proves it
produces these shapes, and `instances` proves it accepts them, so neither can change alone without a test failing.
Values are examples. Keys and value types are the contract. Change a file only together with both sides.

- `event.<type>.json`: the body of `POST /internal/events/` on `instances`.
- `response.<kind>.json`: `GET /internal/{questionnaire-types,battery-types}/<id>/` on `catalog`.
- `response.type_page.json`: `GET /internal/{questionnaire-types,battery-types}/?after=<id>` on `catalog`.
