SUPPORTED={"barcode","passport-dummy","smartcard-dummy","document-reader-dummy"}
def emulate(kind,payload):
    if kind not in SUPPORTED:raise ValueError("unsupported_training_peripheral")
    return {"kind":kind,"sandbox":True,"synthetic":True,"translated_input":payload}
