# NSX-T API Bash Toolkit

A modern, modular, and interactive Bash toolkit for managing VMware NSX-T via its REST API.

## Features

- **Certificate management**: List, validate, assign, and manage NSX-T certificates
- **Indexed selection**: Pick certificates by number, not by copy-pasting IDs
- **Spinner**: Fun, visible feedback for slow API calls
- **Colorful output**: Errors in red, success in green, headers in blue
- **Enterprise-ready**: Logs to systemd journal, robust error handling, XDG config
- **CLI and interactive**: Use as a script or source as a library
- **Safe**: No secrets in logs, password never echoed

## Requirements

- Bash 4+
- `jq`
- `curl`
- (Optional) `logger` for journald/syslog logging

## Usage

### Interactive mode

```sh
./nsx-api.sh
```

### CLI mode

```sh
./nsx-api.sh --get /api/v1/logical-ports
./nsx-api.sh --list-certs
./nsx-api.sh --apply-cluster <cert-id>
```

### As a library

```bash
source nsx-api.sh
load_config
api_call GET /api/v1/logical-ports | jq .
```

## Configuration

On first run, the script will prompt for your NSX Manager URL, username, and password, and save them in `~/.config/nsx-api/config` (chmod 600).

## Roadmap

- Fuzzy search for certs
- More API helpers
- Automated certificate rotation
- More CLI flags and subcommands

## License

MIT

---

**Contributions and issues welcome!**