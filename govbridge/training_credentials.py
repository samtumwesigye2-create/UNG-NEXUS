import base64,hashlib,json,os,time,uuid
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import padding

def _b64(b):return base64.urlsafe_b64encode(b).decode().rstrip("=")
def issue_rs256(subject,identity_context,metrics,entitlements,modules,ttl=2592000):
    pem=os.getenv("GOVBRIDGE_TRAINING_RSA_PRIVATE_KEY_PEM","").replace("\\n","\n")
    kid=os.getenv("GOVBRIDGE_TRAINING_KID","sandbox-auth-key-current")
    if not pem:raise RuntimeError("rsa_signing_key_not_configured")
    key=serialization.load_pem_private_key(pem.encode(),password=None)
    now=int(time.time())
    header={"alg":"RS256","typ":"JWT","kid":kid}
    payload={"iss":"gov-national-sandbox-authority","sub":subject,"aud":"gov-production-iam-gateway","exp":now+int(ttl),"iat":now,"jti":f"token_{uuid.uuid4()}","identity_context":identity_context,"compliance_metrics":{**metrics,"completed_modules":modules},"production_entitlements":entitlements}
    h=_b64(json.dumps(header,separators=(",",":")).encode());p=_b64(json.dumps(payload,separators=(",",":")).encode())
    sig=key.sign(f"{h}.{p}".encode(),padding.PKCS1v15(),hashes.SHA256())
    token=f"{h}.{p}.{_b64(sig)}"
    return {"token":token,"header":header,"payload":payload,"token_sha256":hashlib.sha256(token.encode()).hexdigest()}
