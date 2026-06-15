import asyncio
import contextlib
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db_with_retry
from services.billing_followup_scanner import start_billing_followup_scanner, stop_billing_followup_scanner
from services.overdue_scanner import start_overdue_scanner, stop_overdue_scanner
from services.storage.minio_client import ensure_minio_bucket_ready_at_startup
from websocket.simulator import IoTSimulator
from routers import (
    auth,
    bills,
    chat,
    client,
    complaints,
    contracts,
    delivery,
    delivery_dispatch,
    delivery_sort,
    demo,
    driver,
    factory,
    iot,
    monitor,
    notifications,
    ocr,
    operation,
    orders,
    periodic_quality_reports,
    quality_reports,
    supplier,
    smart_scale_recognition,
    system,
    tianshu_insights,
    voice,
    ws,
    xinfadi,
    zgncpjgw,
)


async def _warm_audit_chain_cache() -> None:
    """监管首页态势数据：13 张表聚合较重，启动时静默预热，避免第一个用户撞冷加载。"""
    try:
        from database import SessionLocal
        from routers.monitor import _compute_audit_chain
        async with SessionLocal() as db:
            await _compute_audit_chain(db)
    except Exception:
        # 预热失败不阻断启动；首个请求会再触发一次冷算
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    simulator = None
    simulator_task = None
    overdue_task = None
    billing_followup_task = None
    audit_warm_task = None
    await init_db_with_retry()
    ensure_minio_bucket_ready_at_startup()
    if settings.simulator_enabled:
        simulator = IoTSimulator()
        simulator_task = asyncio.create_task(simulator.run())
    overdue_task = await start_overdue_scanner()
    billing_followup_task = await start_billing_followup_scanner()
    audit_warm_task = asyncio.create_task(_warm_audit_chain_cache())
    yield
    # 开发模式 --reload 时若后台任务长时间不退出，会导致整站 API 挂起（前端全部请求失败）
    if simulator and simulator_task:
        await simulator.stop()
        simulator_task.cancel()
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
            await asyncio.wait_for(simulator_task, timeout=3.0)
    with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
        await asyncio.wait_for(stop_overdue_scanner(overdue_task), timeout=3.0)
    with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
        await asyncio.wait_for(stop_billing_followup_scanner(billing_followup_task), timeout=3.0)
    if audit_warm_task and not audit_warm_task.done():
        audit_warm_task.cancel()
        with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
            await asyncio.wait_for(audit_warm_task, timeout=2.0)


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
app.include_router(delivery_dispatch.router, prefix=settings.api_prefix)
app.include_router(delivery_sort.router, prefix=settings.api_prefix)
app.include_router(factory.router, prefix=settings.api_prefix)
app.include_router(operation.router, prefix=settings.api_prefix)
app.include_router(monitor.router, prefix=settings.api_prefix)
app.include_router(tianshu_insights.router, prefix=settings.api_prefix)
app.include_router(xinfadi.router, prefix=settings.api_prefix)
app.include_router(zgncpjgw.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(notifications.router, prefix=settings.api_prefix)
app.include_router(iot.router, prefix=settings.api_prefix)
app.include_router(ocr.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(contracts.router, prefix=settings.api_prefix)
app.include_router(orders.router, prefix=settings.api_prefix)
app.include_router(periodic_quality_reports.router, prefix=settings.api_prefix)
app.include_router(quality_reports.router, prefix=settings.api_prefix)
app.include_router(complaints.router, prefix=settings.api_prefix)
app.include_router(bills.router, prefix=settings.api_prefix)
app.include_router(demo.router, prefix=settings.api_prefix)
app.include_router(driver.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(smart_scale_recognition.router, prefix=settings.api_prefix)
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
