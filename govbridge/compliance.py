import os,time
CONTROL_TARGETS={
 "NIST-SP-800-53-REV5":["AC","AU","IA","SC","SI","CP","IR"],
 "NIST-SP-800-207":["policy-enforcement-point","per-request-authz","resource-centric-access"],
 "FIPS-140-3":["validated-crypto-module-required","approved-security-functions"],
 "FEDRAMP-HIGH":["authorization-boundary","continuous-monitoring","incident-response"],
 "NIST-SP-800-63":["phishing-resistant-admin-authentication"],
}
def posture():
    return {
      "target_controls":CONTROL_TARGETS,
      "fips_provider_configured":bool(os.getenv("GOVBRIDGE_FIPS_CRYPTO_PROVIDER")),
      "hsm_configured":bool(os.getenv("GOVBRIDGE_HSM_KEY_URI")),
      "worm_audit_sink_configured":bool(os.getenv("GOVBRIDGE_WORM_AUDIT_URL")),
      "siem_configured":bool(os.getenv("GOVBRIDGE_SIEM_URL")),
      "device_posture_required":os.getenv("GOVBRIDGE_REQUIRE_DEVICE_POSTURE","true").lower()=="true",
      "status":"control-targets-configured-not-certified"
    }
