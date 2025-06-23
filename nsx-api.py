#!/usr/bin/env python3
import os
import sys
import json
import requests
import logging
from getpass import getpass
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
console = Console()

# --- Logging Setup ---
def ensure_logfile(path: str) -> str:
    try:
        if not os.path.exists(path):
            with open(path, "a"):
                os.utime(path, None)
            os.chmod(path, 0o666)
    except PermissionError:
        fallback = os.path.expanduser("~/.nsx-api.log")
        console.print(f"[yellow]Warning: Cannot write to {path}, using {fallback} instead.[/yellow]")
        return fallback
    except Exception as e:
        console.print(f"[red]Error creating log file: {e}[/red]")
        return os.path.expanduser("~/.nsx-api.log")
    return path

LOG_PATH = ensure_logfile("/var/log/nsx-api.log")
logger = logging.getLogger("nsx-api")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
console.print(f"[green]Logging to {LOG_PATH}[/green]")

# --- Config ---
XDG_CONFIG_HOME = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
NSX_CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, "nsx-api")
CONFIG_FILE = os.path.join(NSX_CONFIG_DIR, "config.json")

def save_config(cfg: dict):
    os.makedirs(NSX_CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)
    os.chmod(CONFIG_FILE, 0o600)
    logger.info(f"Config saved to {CONFIG_FILE}")

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        console.print("[bold yellow]=== NSX API Client Config Setup ===[/bold yellow]")
        nsx_url = input("NSX Manager URL (e.g. https://nsxmgr.local): ").strip()
        nsx_user = input("NSX Username: ").strip()
        nsx_pass = getpass("NSX Password: ")
        cfg = {"nsx_url": nsx_url, "username": nsx_user, "password": nsx_pass}
        save_config(cfg)
        return cfg
    with open(CONFIG_FILE) as f:
        return json.load(f)

cfg = load_config()

# --- API Call with Rich Spinner ---
def api_call(method: str, endpoint: str, payload: dict = None, base_url: str = None):
    url = (base_url or cfg["nsx_url"]).rstrip("/") + "/" + endpoint.lstrip("/")
    auth = (cfg["username"], cfg["password"])
    headers = {"Content-Type": "application/json"}
    logger.info(f"API call: {method} {url}")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("Waiting for NSX API...", start=False)
        progress.start_task(task)
        try:
            if method == "GET":
                resp = requests.get(url, auth=auth, headers=headers, verify=False, timeout=30)
            elif method == "POST":
                resp = requests.post(url, auth=auth, headers=headers, json=payload, verify=False, timeout=30)
            elif method == "PUT":
                resp = requests.put(url, auth=auth, headers=headers, json=payload, verify=False, timeout=30)
            elif method == "DELETE":
                resp = requests.delete(url, auth=auth, headers=headers, verify=False, timeout=30)
            else:
                raise ValueError("Unsupported method")
        except Exception as e:
            logger.error(f"API call failed: {e}")
            console.print(f"[red]API call failed: {e}[/red]")
            return None
    if resp.status_code >= 400:
        try:
            err = resp.json()
            logger.error(f"API error: {err.get('error_message', resp.text)}")
            console.print(f"[red]API error: {err.get('error_message', resp.text)}[/red]")
        except Exception:
            logger.error(f"API error: {resp.text}")
            console.print(f"[red]API error: {resp.text}[/red]")
        return None
    try:
        return resp.json()
    except Exception:
        return resp.text

# --- Cert Management ---
def get_vip_cert_id():
    data = api_call("GET", "/api/v1/cluster/api-certificate")
    if data and "certificate_id" in data:
        return data["certificate_id"]
    return None

def list_certs(return_json: bool = False):
    data = api_call("GET", "/api/v1/trust-management/certificates")
    vip_cert_id = get_vip_cert_id()
    if not data or "results" not in data:
        console.print("[red]No certificates found or API error.[/red]")
        return []
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("#", style="bold")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("Type")
    table.add_column("Expiry", style="bold")
    table.add_column("Subject")
    table.add_column("Issuer")
    table.add_column("InUse")
    certs = []
    now = datetime.now(timezone.utc)
    for i, cert in enumerate(data["results"]):
        certs.append(cert)
        expiry = cert.get("expiration_date", "-")
        expiry_str = expiry
        style = ""
        # Highlight expired/expiring certs
        try:
            if expiry and expiry != "-":
                exp_dt = datetime.strptime(expiry, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                days_left = (exp_dt - now).days
                if days_left < 0:
                    style = "bold red"
                    expiry_str += " (EXPIRED)"
                elif days_left < 30:
                    style = "yellow"
                    expiry_str += f" ({days_left}d left)"
        except Exception:
            pass
        # Highlight VIP cert
        name = cert.get("display_name", "-")
        if cert.get("id") == vip_cert_id:
            name = f"[bold green]{name} (VIP)[/bold green]"
        table.add_row(
            str(i),
            name,
            cert.get("category", "-"),
            cert.get("type", "-"),
            f"[{style}]{expiry_str}[/{style}]" if style else expiry_str,
            cert.get("subject_cn", "-"),
            cert.get("issuer_cn", "-"),
            str(cert.get("in_use", "-")),
        )
    console.print(table)
    if return_json:
        return certs
    input("Press Enter to continue...")
    return certs

def pick_cert() -> str:
    certs = list_certs(return_json=True)
    if not certs:
        return None
    while True:
        idx = input(f"Pick certificate by index (0-{len(certs)-1}) or 'b' to go back: ").strip()
        if idx.lower() == 'b':
            return None
        if idx.isdigit() and 0 <= int(idx) < len(certs):
            return certs[int(idx)]["id"]
        else:
            console.print("[red]Invalid selection.[/red]")

def pick_node() -> dict:
    data = api_call("GET", "/api/v1/cluster/nodes")
    if not data or "nodes" not in data:
        console.print(f"[red]No nodes found or API error: {data}[/red]")
        return None
    nodes = data["nodes"]
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("#", style="bold")
    table.add_column("FQDN")
    table.add_column("IP")
    table.add_column("Role")
    for i, node in enumerate(nodes):
        table.add_row(
            str(i),
            node.get("fqdn", "-"),
            node.get("ip_address", "-"),
            node.get("node_role", "-"),
        )
    console.print(table)
    while True:
        idx = input(f"Pick node by index (0-{len(nodes)-1}) or 'b' to go back: ").strip()
        if idx.lower() == 'b':
            return None
        if idx.isdigit() and 0 <= int(idx) < len(nodes):
            return nodes[int(idx)]
        else:
            console.print("[red]Invalid selection.[/red]")

def validate_cert():
    cert_id = pick_cert()
    if not cert_id:
        return
    data = api_call("GET", f"/api/v1/trust-management/certificates/{cert_id}?action=validate")
    if data and data.get("status") == "OK":
        console.print("[green]Validation result: OK[/green]")
        logger.info(f"Certificate {cert_id} validated OK")
    else:
        console.print(f"[red]Validation error: {data}[/red]")
        logger.error(f"Validation error for {cert_id}: {data}")

def disable_crl_checking():
    config = api_call("GET", "/api/v1/global-configs/SecurityGlobalConfig")
    if not config:
        return
    rev = config.get("_revision", 0)
    payload = {
        "crl_checking_enabled": False,
        "resource_type": "SecurityGlobalConfig",
        "_revision": rev
    }
    confirm = input("Are you sure you want to disable CRL checking? (y/N): ").strip().lower()
    if confirm != "y":
        console.print("[yellow]Aborted.[/yellow]")
        return
    data = api_call("PUT", "/api/v1/global-configs/SecurityGlobalConfig", payload)
    console.print(data)
    logger.info("CRL checking disabled")

def apply_cert_cluster():
    cert_id = pick_cert()
    if not cert_id:
        return
    confirm = input("Apply this certificate to the cluster VIP? (y/N): ").strip().lower()
    if confirm != "y":
        console.print("[yellow]Aborted.[/yellow]")
        return
    data = api_call("POST", f"/api/v1/cluster/api-certificate?action=set_cluster_certificate&certificate_id={cert_id}", {})
    if data and "error_code" in data:
        console.print(f"[red]Error applying certificate: {data}[/red]")
        logger.error(f"Error applying cert {cert_id} to cluster: {data}")
    else:
        console.print("[green]Certificate applied successfully![/green]")
        logger.info(f"Certificate {cert_id} applied to cluster")

def apply_cert_node():
    cert_id = pick_cert()
    if not cert_id:
        return
    node = pick_node()
    if not node:
        return
    node_fqdn = node.get("fqdn")
    node_ip = node.get("ip_address")
    base_url = None
    if node_fqdn:
        base_url = f"https://{node_fqdn}"
    elif node_ip:
        base_url = f"https://{node_ip}"
    else:
        console.print("[red]Node has no FQDN or IP![/red]")
        return
    confirm = input(f"Apply certificate to node {node_fqdn or node_ip}? (y/N): ").strip().lower()
    if confirm != "y":
        console.print("[yellow]Aborted.[/yellow]")
        return
    data = api_call(
        "POST",
        f"/api/v1/node/services/http?action=apply_certificate&certificate_id={cert_id}",
        {},
        base_url=base_url
    )
    if data and "error_code" in data:
        console.print(f"[red]Error applying certificate: {data}[/red]")
        logger.error(f"Error applying cert {cert_id} to node {base_url}: {data}")
    else:
        console.print("[green]Certificate applied successfully![/green]")
        logger.info(f"Certificate {cert_id} applied to node {base_url}")

def apply_cert_all_nodes():
    cert_id = pick_cert()
    if not cert_id:
        return
    data = api_call("GET", "/api/v1/cluster/nodes")
    if not data or "nodes" not in data:
        console.print("[red]No nodes found or API error.[/red]")
        return
    nodes = data["nodes"]
    results = []
    for node in nodes:
        node_fqdn = node.get("fqdn")
        node_ip = node.get("ip_address")
        base_url = f"https://{node_fqdn or node_ip}"
        console.print(f"Assigning cert to node: {node_fqdn or node_ip} ...")
        resp = api_call(
            "POST",
            f"/api/v1/node/services/http?action=apply_certificate&certificate_id={cert_id}",
            {},
            base_url=base_url
        )
        if resp and "error_code" not in resp:
            console.print(f"[green]Success for {node_fqdn or node_ip}[/green]")
            results.append((node_fqdn or node_ip, "Success"))
        else:
            console.print(f"[red]Failed for {node_fqdn or node_ip}: {resp}[/red]")
            results.append((node_fqdn or node_ip, f"Failed: {resp}"))
    # Summary table
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Node")
    table.add_column("Result")
    for node, result in results:
        table.add_row(node, result)
    console.print(table)

def show_assignments():
    console.print("[bold blue]Cluster VIP certificate assignment:[/bold blue]")
    data = api_call("GET", "/api/v1/cluster/api-certificate")
    if data:
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Field")
        table.add_column("Value")
        for k, v in data.items():
            table.add_row(str(k), str(v))
        console.print(table)
    logger.info("Showed cluster VIP certificate assignment")
    console.print("[bold blue]Manager node certificate assignments:[/bold blue]")
    data = api_call("GET", "/api/v1/trust-management/certificates")
    if data and "results" in data:
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Node/Service")
        table.add_column("Cert Name")
        table.add_column("In Use")
        table.add_column("Expiry")
        now = datetime.now(timezone.utc)
        for cert in data["results"]:
            if cert.get("service_type") == "API":
                expiry = cert.get("expiration_date", "-")
                expiry_str = expiry
                style = ""
                try:
                    if expiry and expiry != "-":
                        exp_dt = datetime.strptime(expiry, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                        days_left = (exp_dt - now).days
                        if days_left < 0:
                            style = "bold red"
                            expiry_str += " (EXPIRED)"
                        elif days_left < 30:
                            style = "yellow"
                            expiry_str += f" ({days_left}d left)"
                except Exception:
                    pass
                table.add_row(
                    cert.get("node_id", "-"),
                    cert.get("display_name", "-"),
                    str(cert.get("in_use", "-")),
                    f"[{style}]{expiry_str}[/{style}]" if style else expiry_str,
                )
        console.print(table)
    logger.info("Showed manager node certificate assignments")

def raw_api_call():
    m = input("HTTP method: ").strip().upper()
    e = input("Endpoint: ").strip()
    p = input("Payload (or leave blank): ").strip()
    payload = None
    if p:
        try:
            payload = json.loads(p)
        except Exception:
            console.print("[yellow]Payload is not valid JSON, sending as string.[/yellow]")
            payload = p
    data = api_call(m, e, payload)
    console.print(data)
    logger.info(f"Raw API call: {m} {e}")

# --- Main Menu ---
def main():
    while True:
        console.print("\n[bold cyan]NSX-T Certificate/API Management[/bold cyan]")
        console.print("1) List certificates")
        console.print("2) Validate certificate")
        console.print("3) Disable CRL checking")
        console.print("4) Apply certificate to cluster VIP")
        console.print("5) Apply certificate to manager node")
        console.print("6) Apply certificate to ALL manager nodes")
        console.print("7) Show current certificate assignments")
        console.print("8) Raw API call")
        console.print("0) Exit")
        opt = input("Choose an option: ").strip()
        if opt == "1":
            list_certs()
        elif opt == "2":
            validate_cert()
        elif opt == "3":
            disable_crl_checking()
        elif opt == "4":
            apply_cert_cluster()
        elif opt == "5":
            apply_cert_node()
        elif opt == "6":
            apply_cert_all_nodes()
        elif opt == "7":
            show_assignments()
        elif opt == "8":
            raw_api_call()
        elif opt == "0":
            logger.info("Session ended")
            print("Goodbye!")
            sys.exit(0)
        else:
            console.print("[red]Invalid option[/red]")

if __name__ == "__main__":
    main()