def modern_to_terminal(fields,mapping):
    screen=[]
    for name,value in fields.items():
        m=mapping.get(name)
        if m:screen.append({"row":int(m["row"]),"col":int(m["col"]),"text":str(value),"synthetic":True})
    return {"operations":screen,"mode":"emulator-only"}
def terminal_to_modern(buffer,mapping):
    out={}
    for name,m in mapping.items():
        row=str(m["row"]);col=str(m["col"])
        value=(buffer.get(row) or {}).get(col)
        if value is not None:out[name]=value
    return out
