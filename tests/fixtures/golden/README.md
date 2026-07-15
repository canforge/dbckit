# Golden fixture provenance

These fixtures are copied without modification from established open-source CAN
projects and pinned to specific upstream commits.

- `opendbc_comma_body.dbc`: `opendbc/dbc/comma_body.dbc` from
  [`commaai/opendbc`](https://github.com/commaai/opendbc) commit
  `bc7aaf9be25b836b4862f2e201d82827aa27d2ec`. Licensed under the MIT License;
  see `LICENSE.opendbc.txt`.
- `python_can_logfile.asc`: `test/data/logfile.asc` from
  [`hardbyte/python-can`](https://github.com/hardbyte/python-can) commit
  `b4f82abede25ff83376be793a2935c41f81c3869`. Licensed under LGPL-3.0;
  see `LICENSE.python-can.txt`.

The tests assert semantic DBC parse/serialize/parse stability and verify the ASC
reader against the upstream Vector-format trace, including its mixture of frame,
status, error, statistics, J1939, and CAN FD rows.
