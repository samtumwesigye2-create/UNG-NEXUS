ALLOWED={"MOVE_CURSOR","SEND_KEYSTROKES","SEND_COMMAND_KEY"}
KEYS={"ENTER","PF1","PF2","PF3","PF4","PF5","PF6","PF7","PF8","PF9","PF10","PF11","PF12","CLEAR"}
def compile_actions(body):
    out=[]
    for a in body.get("actions") or []:
        typ=a.get("type")
        if typ not in ALLOWED:raise ValueError("unsupported_terminal_action")
        if typ=="MOVE_CURSOR":
            r=int(a.get("row",0));c=int(a.get("column",0))
            if not 1<=r<=43 or not 1<=c<=132:raise ValueError("invalid_terminal_coordinate")
            out.append({"type":typ,"row":r,"column":c})
        elif typ=="SEND_COMMAND_KEY":
            k=str(a.get("value","")).upper()
            if k not in KEYS:raise ValueError("unsupported_command_key")
            out.append({"type":typ,"value":k})
        else:
            v=str(a.get("value",""))
            if len(v)>256:raise ValueError("keystroke_payload_too_large")
            out.append({"type":typ,"value":v})
    return {"target_screen_id":str(body.get("target_screen_id","")),"actions":out,"validation":body.get("response_validation") or {}}
