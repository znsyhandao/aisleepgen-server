from ..utils.monitor import global_monitor

@global_monitor.track('api_predict')
async def api_predict(request: Request):
    data = await request.json()
    processed = await hardware_manager.process_data(data)
    return JSONResponse(processed)
