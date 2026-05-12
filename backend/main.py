import asyncio
import contextlib
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db_with_retry
from services.overdue_scanner import start_overdue_scanner, stop_overdue_scanner
from websocket.simulator import IoTSimulator
from routers import (
    auth,
    bills,
    chat,
    client,
    complaints,
    contracts,
    delivery,
    demo,
    factory,
    iot,
    monitor,
    notifications,
    ocr,
    operation,
    orders,
    quality_reports,
    supplier,
    system,
    tianshu_insights,
    voice,
    ws,
    xinfadi,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    simulator = None
    simulator_task = None
    overdue_task = None
    await init_db_with_retry()
    if settings.simulator_enabled:
        simulator = IoTSimulator()
        simulator_task = asyncio.create_task(simulator.run())
    overdue_task = await start_overdue_scanner()
    yield
    if simulator and simulator_task:
        await simulator.stop()
        simulator_task.cancel()
        with contextlib.suppress(Exception):
            await simulator_task
    await stop_overdue_scanner(overdue_task)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(client.router, prefix=settings.api_prefix)
app.include_router(supplier.router, prefix=settings.api_prefix)
app.include_router(delivery.router, prefix=settings.api_prefix)
app.include_router(factory.router, prefix=settings.api_prefix)
app.include_router(operation.router, prefix=settings.api_prefix)
app.include_router(monitor.router, prefix=settings.api_prefix)
app.include_router(tianshu_insights.router, prefix=settings.api_prefix)
app.include_router(xinfadi.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(iot.router, prefix=settings.api_prefix)
app.include_router(ocr.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(contracts.router, prefix=settings.api_prefix)
app.include_router(orders.router, prefix=settings.api_prefix)
app.include_router(quality_reports.router, prefix=settings.api_prefix)
app.include_router(complaints.router, prefix=settings.api_prefix)
app.include_router(bills.router, prefix=settings.api_prefix)
app.include_router(demo.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(ws.router)


@app.get("/")
async def root():
    return {"message": "大宗供应链系统后端运行中"}


@app.middleware("http")
async def inject_trace_id(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", "").strip() or uuid4().hex
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response
