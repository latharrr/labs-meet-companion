"""Minimal companion gateway. All upstream authentication checks remain intact."""
from gateway.adapters import build_production_app

ALLOWED = {
    '/health': {'GET'},
    '/auth/me': {'GET'},
    '/bots': {'POST'},
    '/bots/{platform}/{native_meeting_id}': {'DELETE'},
    '/bots/{platform}/{native_meeting_id}/chat': {'POST'},
    '/bots/{platform}/{native_meeting_id}/chat/{request_id}': {'GET'},
    '/transcripts/{platform}/{native_meeting_id}': {'GET'},
}


def make_app():
    app = build_production_app()
    # Pinned gateway requires MCP manifest even with no MCP_URL. Assemble normally,
    # then retain only companion HTTP methods/paths. No docs, WS, share, calendar,
    # agent, MCP, bot sign-in, speak, model or arbitrary-user-settings endpoints.
    routes=[]
    for route in app.router.routes:
        wanted=ALLOWED.get(getattr(route,'path',''))
        if wanted:
            methods=set(getattr(route,'methods',())) & wanted
            if methods:
                route.methods=methods
                routes.append(route)
    app.router.routes[:]=routes
    app.openapi_schema=None
    if {r.path for r in routes} != set(ALLOWED):
        raise RuntimeError('Pinned companion gateway route contract changed')
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(make_app(), host='0.0.0.0', port=8056, access_log=False)
