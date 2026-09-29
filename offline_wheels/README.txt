This folder intentionally contains NO packages or Oracle client DLLs.
The DB/Splunk collector requires only Python 3.11+ standard libraries.
Oracle additionally requires oracledb or cx_Oracle and an approved Oracle Instant Client.
SELECT_PYTHON.cmd can reuse an existing working Oracle Python installation.
For an IT-approved offline installation, put the matching Windows/Python wheels
AND all their dependencies here, then explicitly run INSTALL_ORACLE_OFFLINE.cmd.
It uses --no-index --no-deps and never falls back to PyPI or modifies pip.ini.
No third-party binaries or fonts are redistributed in this project.
