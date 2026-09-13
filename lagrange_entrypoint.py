import app as nexus
from ung_lagrange_adapter import create_lagrange_router

app = nexus.app
app.include_router(create_lagrange_router('UNG-NEXUS', ['orchestration']))
