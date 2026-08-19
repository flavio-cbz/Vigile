"""
Vigile — Chat Orchestration Engine

Orchestrates the conversational loop between the user, the LLM, the tool executor,
and the worker nodes. Produces a unified SSE stream.
"""

import json
import logging
import time
from typing import AsyncIterator, Any

import aiosqlite

from master.core.llm_client import LLMClient
from master.core.node_manager import NodeManager
from master.core.tools import TOOL_DEFINITIONS, ToolExecutor
from master.core.prompts import load_prompt

logger = logging.getLogger(__name__)


class ChatEngine:
    """Manages multi-round tool-calling chat execution and SSE event generation."""

    def __init__(
        self,
        llm: LLMClient,
        nm: NodeManager,
        db: aiosqlite.Connection,
        user_id: str,
    ) -> None:
        self.llm = llm
        self.nm = nm
        self.db = db
        self.user_id = user_id

    async def run(
        self,
        history: list[dict[str, Any]],
        node_id: str | None,
        locale: str = "fr",
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Run the multi-round conversational loop.
        Yields SSE-compatible dict events.
        """
        # 1. Build initial context and system prompt
        system_prompt = await self._build_system_prompt(node_id, locale)
        
        # Build full messages chain for the LLM
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        round_limit = 5
        current_round = 0

        while current_round < round_limit:
            current_round += 1
            token_buffer = ""
            tool_calls_map = {}
            has_tool_calls = False

            # Call LLM with tool definitions
            stream_gen = self.llm.stream(
                messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.3,
            )

            async for event in stream_gen:
                if event["type"] == "token":
                    token_buffer += event["content"]
                    yield {"type": "token", "content": event["content"]}

                elif event["type"] == "tool_call":
                    has_tool_calls = True
                    for tc in event["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        
                        if tc.get("id"):
                            tool_calls_map[idx]["id"] = tc["id"]
                        
                        func = tc.get("function", {})
                        if func.get("name"):
                            tool_calls_map[idx]["name"] = func["name"]
                        if func.get("arguments"):
                            tool_calls_map[idx]["arguments"] += func["arguments"]

                elif event["type"] == "error":
                    yield {"type": "error", "detail": event["detail"]}
                    return

            # If the LLM outputted normal tokens and no tool calls, we are done
            if not has_tool_calls:
                # Save assistant content to conversation history
                if token_buffer:
                    history.append({"role": "assistant", "content": token_buffer})
                break

            # Process accumulated tool calls
            assistant_tool_calls = []
            tool_messages_to_add = []
            proposals_detected = []

            for idx, tc in sorted(tool_calls_map.items()):
                tc_id = tc["id"]
                tc_name = tc["name"]
                tc_args_str = tc["arguments"]

                try:
                    tc_args = json.loads(tc_args_str) if tc_args_str else {}
                except Exception:
                    tc_args = {}

                # Notify frontend about tool call execution
                yield {
                    "type": "tool_call",
                    "id": tc_id,
                    "name": tc_name,
                    "arguments": tc_args,
                }

                # Record the tool call for the OpenAI message structure
                assistant_tool_calls.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {
                        "name": tc_name,
                        "arguments": tc_args_str,
                    }
                })

                # Execute tool
                logger.info("Executing tool: %s with args %s", tc_name, tc_args)
                result = await ToolExecutor.execute(
                    tc_name, tc_args, self.nm, self.db, self.user_id
                )

                # If this tool was a mutation proposal, capture the proposal ID to pass to UI
                if result.get("proposal_id"):
                    proposals_detected.append(result["data"])

                # Notify frontend about tool result
                yield {
                    "type": "tool_result",
                    "id": tc_id,
                    "name": tc_name,
                    "success": result["success"],
                    "data": result["data"],
                    "error": result["error"],
                }

                # Record the tool response
                tool_messages_to_add.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tc_name,
                    "content": json.dumps(result),
                })

            # Append the assistant's tool call invocation and the tool responses to messages
            assistant_msg = {
                "role": "assistant",
                "content": token_buffer or None,
                "tool_calls": assistant_tool_calls,
            }
            
            # If a proposal was generated, attach it to the history message for rendering
            if proposals_detected:
                assistant_msg["proposal"] = proposals_detected[0]

            messages.append(assistant_msg)
            history.append(assistant_msg)

            for tm in tool_messages_to_add:
                messages.append(tm)
                history.append(tm)

            # Yield proposal events so frontend can render approve/reject cards immediately
            for prop in proposals_detected:
                yield {
                    "type": "proposal",
                    "proposal_id": prop["proposal_id"],
                    "action": prop["action"],
                    "risk_level": prop["risk_level"],
                    "reasoning": prop["reasoning"],
                    "params": prop["params"],
                }

            # Loop back to LLM to process tool results and generate final response (or more tool calls)
            logger.info("Re-calling LLM with tool responses (round %d)", current_round)

    async def _build_system_prompt(self, node_id: str | None, locale: str) -> str:
        """Load and format the low-level copilot system prompt with current node context."""
        lang_instruction = (
            "You must always reply in English."
            if locale == "en"
            else "Tu dois toujours répondre en français."
        )

        if not node_id or node_id == "all":
            # Global overview context
            context_lines = "- Aucun nœud spécifique ciblé. Utilisez 'get_fleet_overview' pour lister les machines."
            return load_prompt(
                "copilot_system",
                lang_instruction=lang_instruction,
                context_lines=context_lines,
            )

        node = await self.nm.get_node(self.db, node_id)
        if node is None:
            context_lines = f"- ID de nœud spécifié invalide ou introuvable : {node_id}"
            return load_prompt(
                "copilot_system",
                lang_instruction=lang_instruction,
                context_lines=context_lines,
            )

        # Build detailed node context
        context_parts = [
            f"Nœud ciblé : {node.get('name', 'inconnu')} (ID: {node_id})",
            f"État : {node.get('state', 'inconnu')}",
            f"Système : {node.get('os', 'inconnu')} / {node.get('arch', 'inconnu')}",
            f"Nom d'hôte : {node.get('hostname', 'inconnu')}",
        ]

        if node.get("state") == "CONNECTED":
            context_parts.append("Statut : En ligne")
            
            # Fetch latest metrics snapshot
            try:
                async with self.db.execute(
                    "SELECT cpu_percent, mem_percent, disk_percent, uptime_seconds "
                    "FROM metrics_snapshots WHERE node_id = ? "
                    "ORDER BY collected_at DESC LIMIT 1",
                    (node_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    context_parts.append(
                        f"Métriques actuelles : CPU: {row['cpu_percent']:.1f}% | "
                        f"RAM: {row['mem_percent']:.1f}% | "
                        f"Disque: {row['disk_percent']:.1f}% | "
                        f"Uptime: {row['uptime_seconds'] / 3600:.0f}h"
                    )
            except Exception:
                pass
        else:
            context_parts.append("Statut : Hors ligne")

        context_lines = "\n".join(f"- {line}" for line in context_parts)
        return load_prompt(
            "copilot_system",
            lang_instruction=lang_instruction,
            context_lines=context_lines,
        )
