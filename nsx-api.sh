#!/usr/bin/env bash
set -euo pipefail

# --- Config & Constants ---
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
NSX_CONFIG_DIR="$XDG_CONFIG_HOME/nsx-api"
CONFIG_FILE="$NSX_CONFIG_DIR/config"
LOGGER_TAG="nsx-api.sh"

# --- Logging ---
log() { logger -t "$LOGGER_TAG" "$*"; }

# --- Pretty JSON ---
pretty_json() {
    if command -v jq >/dev/null 2>&1; then jq . 2>/dev/null || cat; else cat; fi
}

# --- Spinner ---
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    tput civis 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
        for c in $spinstr; do
            printf "\r\033[36m[%c] Working...\033[0m" "$c" >&2
            sleep $delay
        done
    done
    printf "\r\033[K" >&2
    tput cnorm 2>/dev/null || true
}

# --- Prompt helpers ---
prompt_yn() {
    local prompt="$1"
    read -rp "$prompt [y/N]: " yn
    [[ "$yn" =~ ^[Yy]$ ]]
}

# --- Config Management ---
create_config() {
    echo "=== NSX API Client Config Setup ==="
    read -rp "NSX Manager URL (e.g. https://nsxmgr.local): " NSX_URL
    read -rp "NSX Username: " NSX_USER
    read -srp "NSX Password: " NSX_PASS
    echo
    mkdir -p "$NSX_CONFIG_DIR"
    cat > "$CONFIG_FILE" <<EOF
nsx_url="$NSX_URL"
username="$NSX_USER"
password='$NSX_PASS'
EOF
    chmod 600 "$CONFIG_FILE"
    log "Config created at $CONFIG_FILE"
    echo "Config saved to $CONFIG_FILE"
}

load_config() {
    if [[ ! -f "$CONFIG_FILE" ]]; then create_config; fi
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
    [[ -z "${nsx_url:-}" || -z "${username:-}" || -z "${password:-}" ]] && {
        log "Config missing required fields"
        echo "Config missing required fields. Please re-create."
        rm -f "$CONFIG_FILE"
        create_config
    }
    log "Config loaded for $nsx_url"
}

# --- API Core with Spinner ---
api_call() {
    local method="$1"
    local endpoint="$2"
    local payload="${3:-}"
    shift 3 || true
    local extra=("$@")
    local curl_args=(-sk -u "$username:$password" -H "Content-Type: application/json" -X "$method")
    [[ -n "$payload" ]] && curl_args+=(-d "$payload")
    local base="${nsx_url%/}"
    local path="${endpoint#/}"
    curl_args+=("${extra[@]}" "$base/$path")
    log "API call: $method $base/$path"
    # Run curl in background and show spinner
    local tmpfile
    tmpfile=$(mktemp)
    (curl "${curl_args[@]}" > "$tmpfile" 2>&1) &
    local curl_pid=$!
    spinner $curl_pid
    wait $curl_pid
    cat "$tmpfile"
    rm -f "$tmpfile"
}

# Print certs table and return JSON (for use in pick_cert)
list_certs() {
    local certs_json
    certs_json=$(api_call GET "/api/v1/trust-management/certificates")
    # Uncomment for debugging:
    # echo "Raw API response:"
    # echo "$certs_json"
    readarray -t cert_lines < <(echo "$certs_json" | jq -r '
        .results[] |
        [
            .display_name // "-",
            .category // "-",
            .type // "-",
            .expiration_date // "-",
            .subject_cn // "-",
            .issuer_cn // "-",
            .in_use // "-"
        ] | @tsv
    ')
    echo -e "\033[1;34m#  Name\t\tCategory\tType\tExpiry\tSubject\tIssuer\tInUse\033[0m"
    for i in "${!cert_lines[@]}"; do
        printf "%2d %s\n" "$i" "${cert_lines[$i]}"
    done
    # Always return JSON for use in pick_cert
    echo "$certs_json"
}

pick_cert() {
    local certs_json
    certs_json=$(list_certs --table)
    local total
    total=$(echo "$certs_json" | jq '.results | length')
    local idx
    while true; do
        read -rp "Pick certificate by index (0-$(($total-1))): " idx
        if [[ "$idx" =~ ^[0-9]+$ ]] && (( idx >= 0 && idx < total )); then
            CERT_ID=$(echo "$certs_json" | jq -r ".results[$idx].id")
            break
        else
            echo -e "\033[31mInvalid selection.\033[0m"
        fi
    done
    echo "$CERT_ID"
}

validate_cert() {
    local cert_id
    cert_id=$(pick_cert)
    local resp
    resp=$(api_call GET "/api/v1/trust-management/certificates/$cert_id?action=validate")
    if echo "$resp" | jq -e '.status' >/dev/null; then
        echo -e "\033[32mValidation result:\033[0m"
        echo "$resp" | pretty_json
    else
        echo -e "\033[31mValidation error:\033[0m"
        echo "$resp" | pretty_json
    fi
}

disable_crl_checking() {
    local config rev
    config=$(api_call GET "/api/v1/global-configs/SecurityGlobalConfig")
    rev=$(echo "$config" | jq '._revision')
    api_call PUT "/api/v1/global-configs/SecurityGlobalConfig" \
        "{\"crl_checking_enabled\": false, \"resource_type\": \"SecurityGlobalConfig\", \"_revision\": $rev}" | pretty_json
}

apply_cert_cluster() {
    local cert_id
    cert_id=$(pick_cert)
    local resp
    resp=$(api_call POST "/api/v1/cluster/api-certificate?action=set_cluster_certificate&certificate_id=$cert_id" '{}')
    if echo "$resp" | jq -e '.error_code' >/dev/null; then
        echo -e "\033[31mError applying certificate:\033[0m"
        echo "$resp" | pretty_json
    else
        echo -e "\033[32mCertificate applied successfully!\033[0m"
        echo "$resp" | pretty_json
    fi
}

apply_cert_node() {
    local cert_id
    cert_id=$(pick_cert)
    read -rp "Enter NSX Manager node FQDN (e.g. nsxmgr01.domain): " NODE
    local resp
    resp=$(api_call POST "/api/v1/node/services/http?action=apply_certificate&certificate_id=$cert_id" '{}')
    if echo "$resp" | jq -e '.error_code' >/dev/null; then
        echo -e "\033[31mError applying certificate:\033[0m"
        echo "$resp" | pretty_json
    else
        echo -e "\033[32mCertificate applied successfully!\033[0m"
        echo "$resp" | pretty_json
    fi
}

show_assignments() {
    echo -e "\033[1;34mCluster VIP certificate assignment:\033[0m"
    api_call GET "/api/v1/cluster/api-certificate" | jq '{id, display_name, issuer_cn, expiration_date, subject_cn}'
    echo
    echo -e "\033[1;34mManager node certificate assignments:\033[0m"
    api_call GET "/api/v1/trust-management/certificates" | jq '.results[] | select(.service_type=="API") | {id, display_name, bound_resource_type, bound_resource_id}'
}

# --- Main Handler ---
main() {
    load_config
    while true; do
        echo
        echo -e "\033[1;36mNSX-T Certificate/API Management\033[0m"
        echo "1) List certificates"
        echo "2) Validate certificate"
        echo "3) Disable CRL checking"
        echo "4) Apply certificate to cluster VIP"
        echo "5) Apply certificate to manager node"
        echo "6) Show current certificate assignments"
        echo "7) Raw API call"
        echo "0) Exit"
        read -rp "Choose an option: " opt
        case "$opt" in
            1) list_certs >/dev/null ;; # Output handled in pick_cert
            2) validate_cert ;;
            3) disable_crl_checking ;;
            4) apply_cert_cluster ;;
            5) apply_cert_node ;;
            6) show_assignments ;;
            7)
                read -rp "HTTP method: " m
                read -rp "Endpoint: " e
                read -rp "Payload (or leave blank): " p
                api_call "$m" "$e" "$p" | pretty_json
                ;;
            0) log "Session ended"; echo "Goodbye!"; exit 0 ;;
            *) echo -e "\033[31mInvalid option\033[0m" ;;
        esac
    done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi