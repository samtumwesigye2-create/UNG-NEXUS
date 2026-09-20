import re
SAFE=re.compile(r"^[A-Z0-9.$#@_-]+$")
def _safe(v,label,maxlen=44):
    v=str(v or "").upper()
    if not v or len(v)>maxlen or not SAFE.match(v):raise ValueError(f"invalid_{label}")
    return v
def render(body,job_class):
    job=_safe(body.get("job_name"),"job_name",8);acct=_safe(body.get("account_string"),"account_string",44)
    ds=_safe(body.get("dataset_target"),"dataset_target",44);jc=_safe(job_class,"job_class",1)
    # Template-only allowlisted JCL; callers cannot inject executable statements.
    return "\n".join([f"//{job} JOB ({acct}),'BATCH SYNC',CLASS={jc},MSGCLASS=X",
      "//STEP1     EXEC PGM=GOVTRANS","//SYSPRINT  DD SYSOUT=*",f"//SYSIN     DD DSN={ds},DISP=SHR",
      "//SYSUT2    DD DSN=PRODUCTION.NEWAPP.MIRROR,DISP=(NEW,CATLG,DELETE)","/*"])
