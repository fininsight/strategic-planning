from . import analysis, checklist, files, health, notices

routers = (
    health.router,
    notices.router,
    analysis.router,
    checklist.router,
    files.router,
)
