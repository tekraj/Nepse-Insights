"""business-intelligence service: the gRPC server api-service calls, and the
Temporal worker running the 24/7 automation (report refresh + monitor),
in one asyncio process."""
from __future__ import annotations

import asyncio
import logging
import os

import grpc
from temporalio.client import Client
from temporalio.worker import Worker

from nepse_common.bi_grpc import business_intelligence_pb2_grpc as pb_grpc
from nepse_common.config import load_app_config

import automation
from agents.master import MasterAgent
from grpc_server import BusinessIntelligenceServicer
from llm import LLM
from portfolio_runner import PortfolioRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bi")

MAX_MESSAGE = 64 * 1024 * 1024


async def main() -> None:
    cfg = load_app_config().bi
    llm = LLM(cfg)
    master = MasterAgent(llm)
    automation.MASTER = master
    log.info("LLM %s (model %s)", "enabled" if llm.enabled else "NOT configured - rule-based summaries only", llm.model or "-")

    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "temporal:7233"))

    server = grpc.aio.server(options=[("grpc.max_send_message_length", MAX_MESSAGE), ("grpc.max_receive_message_length", MAX_MESSAGE)])
    pb_grpc.add_BusinessIntelligenceServicer_to_server(BusinessIntelligenceServicer(master, client, PortfolioRunner(llm)), server)
    server.add_insecure_port(f"[::]:{cfg.grpc_port}")
    await server.start()
    log.info("gRPC listening on :%d", cfg.grpc_port)

    worker = Worker(client, task_queue=automation.TASK_QUEUE, workflows=automation.WORKFLOWS, activities=automation.ACTIVITIES,
                    max_concurrent_activities=max(4, cfg.report_concurrency * 2))
    await automation.upsert_schedules(client)
    await automation.pause_schedules(client, paused=not cfg.automation_enabled)
    log.info("Temporal worker on %s (automation %s)", automation.TASK_QUEUE, "on" if cfg.automation_enabled else "paused")
    await asyncio.gather(worker.run(), server.wait_for_termination())


if __name__ == "__main__":
    asyncio.run(main())
