# Support matrix

| Item | Value |
|---|---|
| Execution host | Linux |
| Python | 3.12.x only (`requires-python = ">=3.12"`) |
| Windows host | Not supported. `openat` + `O_NOFOLLOW` + `dir_fd` are required. |
| Windows locator dialect | Supported as **syntax** and tested on Linux |
| POSIX locator dialect | Supported and tested on Linux |
| Notion | Fake transport for synthetic tests. Real read only with an explicit target id |
| Network in tests | Disabled (`network_mode: none` after wheel install) |

Windows review machines that lack symlink privilege or containment primitives are not a Linux failure. They also cannot be used as PASS evidence.
