ALLOWED_ROUTES = {
    "GOU-UGHUB": {"*"},
    "GOU-NIRA": {"identity.verify"},
    "GOU-URA": {"taxpayer.verify","tax.status","payment.verify"},
    "GOU-URSB": {"business.verify","company.lookup"},
    "GOU-EGP": {"procurement.lookup","award.lookup","contract.status"},
    "GOU-IFMS": {"payment.status","commitment.status"},
    "GOU-UBOS": {"statistics.query","geography.lookup"},
}

def allowed(target: str, message_type: str) -> bool:
    rules = ALLOWED_ROUTES.get(target, set())
    return "*" in rules or message_type in rules
