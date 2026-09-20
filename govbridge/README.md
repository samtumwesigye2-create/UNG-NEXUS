# UNG-GOVBRIDGE

UNG-GOVBRIDGE is the external interoperability gateway between the UNG architecture and approved Uganda government systems.

## Internal route
UNG systems -> NEXUS -> GOVBRIDGE -> approved government endpoint.

## Initial adapters
UGHub, NIRA, URA, URSB, e-GP, IFMS and UBOS.

## Security
- Service-to-service bearer authentication from NEXUS.
- Per-agency credentials are environment variables only.
- Route allowlist blocks unapproved message types.
- No government credential or citizen record is committed to source control.
- Message IDs, correlation IDs and trace IDs are preserved.

## Required environment
UNG_GOVBRIDGE_TOKEN

Per adapter, configure only when official access exists:
UGHUB_BASE_URL / UGHUB_API_TOKEN
NIRA_BASE_URL / NIRA_API_TOKEN
URA_BASE_URL / URA_API_TOKEN
URSB_BASE_URL / URSB_API_TOKEN
EGP_BASE_URL / EGP_API_TOKEN
IFMS_BASE_URL / IFMS_API_TOKEN
UBOS_BASE_URL / UBOS_API_TOKEN

Government endpoint paths are intentionally adapter-configurable. Official production API contracts and credentials must come from the relevant government integration authority; this service does not fabricate them.
