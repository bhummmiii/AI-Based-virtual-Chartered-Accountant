"""
FinLedger AI Assistant package
==============================
Grounded, tool-first assistant used by BOTH:

  * the per-client "AI Insights" assistant   (scope = one client)
  * the sidebar "AI Assistant"               (scope = whole workspace)

Pipeline:  question -> intent detection -> verified tools (existing services)
           -> verified facts -> (optional) LLM explains -> guard -> answer + sources
"""

from app.services.ai_assistant.engine import assistant_engine  # noqa: F401
