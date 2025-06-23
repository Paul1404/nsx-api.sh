# NSX-T API Toolkit

A modern, modular, and interactive toolkit for managing VMware NSX-T via its REST API.

The main goal of this was to make it easier to replace NSX-T self-signed Certs with your own CA-Signed Certs similiar to this guide:

https://www.vgarethlewis.com/2021/03/23/replacing-the-vmware-nsx-t-self-signed-ssl-certificate/ -> But Automated

---

## Project Structure

```
.
├── Archive/           # Legacy Bash script (read-only)
│   └── nsx-api.sh
├── LICENSE
├── nsx-api.py         # Main Python CLI tool
├── pyproject.toml     # Python project metadata (for uv/pip)
├── README.md
└── uv.lock            # Astral UV lockfile for reproducible installs
```

---

## Features

- **Certificate Management**
  - List, validate, and assign NSX-T certificates
  - Assign certificates to the cluster VIP (fully automated)
  - Assign certificates to individual manager nodes (UI/manual for now; API automation coming soon)
- **Indexed Selection**
  - Pick certificates and nodes by number—no more copy-pasting IDs or FQDNs
- **Rich UX**
  - Spinner/progress bar for API calls
  - Colorful, readable tables (using [rich](https://github.com/Textualize/rich))
  - Highlights expiring/expired and in-use certificates
- **Enterprise-Ready**
  - Logs to `/var/log/nsx-api.log` (with rotation, fallback to home if needed)
  - Robust error handling, XDG config, no secrets in logs
- **Interactive & CLI-Friendly**
  - Menu-driven for interactive use
  - Extensible for CLI flags and automation (roadmap)
- **Safe**
  - Passwords never echoed or logged

---

## Requirements

- Python 3.8+
- [Astral UV](https://github.com/astral-sh/uv) for dependency management
- NSX-T 3.x or later

---

## Getting Started

### 1. **Clone the Repo**

```sh
git clone https://github.com/Paul1404/nsx-api.sh.git
cd nsx-api.sh
```

### 2. **Install Astral UV (if not already installed)**

```sh
pip install uv
```
or see [Astral UV install docs](https://github.com/astral-sh/uv#installation).

### 3. **Install Python Dependencies**

```sh
uv pip install -r pyproject.toml
```

### 4. **Run the Toolkit**

```sh
uv run nsx-api.py
```

---

## Usage

- **Interactive menu** for all major features:
  - List certificates
  - Validate certificates
  - Disable CRL checking
  - Assign certificate to cluster VIP
  - Assign certificate to a manager node
  - Assign certificate to **all** manager nodes (coming soon)
  - Show current certificate assignments
  - Raw API call for advanced users

- **Config:**  
  On first run, you’ll be prompted for NSX Manager URL, username, and password.  
  These are stored securely in `~/.config/nsx-api/config.json` (chmod 600).

---

## Roadmap

- [ ] **Automated manager node assignment** (API-driven, all nodes at once)
- [ ] CLI flags for non-interactive/automation use
- [ ] More NSX-T API helpers (segments, firewall, etc.)
- [ ] Enhanced documentation and troubleshooting

---

## Legacy Bash Script

The original Bash toolkit is archived in [`Archive/nsx-api.sh`](Archive/nsx-api.sh) for reference.  
**All new development is in Python.**

---

## License

MIT

---

**Contributions and issues welcome!**  
Open a PR or issue for feature requests, bug reports, or feedback.

---

**Note:**  
This project uses [Astral UV](https://github.com/astral-sh/uv) for Python dependency management and reproducible installs.