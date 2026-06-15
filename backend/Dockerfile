FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
# 第一步：从 PyTorch 官方 CPU 索引预下载 cpu-only wheels（PyPI 默认是 CUDA 包，体积更大）
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.4.1 torchvision==0.19.1
# 第二步：构建其余依赖 wheels；--find-links /wheels 让 pip 优先复用上一步已下载的 cpu torch，不再去 PyPI 拉 CUDA 版
RUN pip wheel --no-cache-dir --wheel-dir /wheels --find-links /wheels -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
# 走 requirements.txt + 本地 wheels，让 pip 解析单一兼容版本（两次 pip wheel 可能产生同包多版本，直接装全部会冲突）
RUN pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt

# 农产品价格网采集：Playwright + Chromium（WAF 引导）
RUN pip install --no-cache-dir 'playwright>=1.40' \
    && python -m playwright install-deps chromium \
    && python -m playwright install chromium

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
