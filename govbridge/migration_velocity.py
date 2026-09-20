PLAN={
 1:{"target_users":12000000,"group":"A","strategy":"hub-heavy","risk_mode":"fail-closed"},
 2:{"target_users":12000000,"group":"B","strategy":"cloud-scale","risk_mode":"degrade-gracefully"},
 3:{"target_users":12000000,"group":"C","strategy":"regional-edge","risk_mode":"degrade-gracefully"},
 4:{"target_users":12000000,"group":"D","strategy":"maximum-cell-utilization","risk_mode":"mixed"},
 5:{"target_users":2000000,"group":"long-tail","strategy":"consolidated","risk_mode":"mixed"},
}
def plan():return PLAN
