"""Account-scoped guard; runs before Chat Plus without changing its code."""
import sys
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from .limiter import Limiter, Settings


@register("astrbot_plugin_anti_laowu", "Tsurumaki-Kokoro", "防止机器人之间高强度互动的可配置限流器", "0.1.0")
class AntiLaowu(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.limiter = Limiter(StarTools.get_data_dir() / "limiter.sqlite3")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=sys.maxsize)
    async def guard(self, event: AstrMessageEvent):
        s = Settings.from_config(self.config)
        user, group = str(event.get_sender_id()), str(event.get_group_id())
        if not s.enabled or user not in s.target_ids:
            return
        if s.group_ids and group not in s.group_ids:
            return
        if s.exempt_admins and event.is_admin():
            return
        body = (event.message_str or "").strip()
        command = body.removeprefix("/").split(maxsplit=1)[0] if body else ""
        if command in s.exempt_commands:
            if s.log_decisions:
                logger.info(f"[anti_laowu] allow reason=exempt_command group={group} user={user}")
            return
        key = (event.get_platform_id(), str(event.get_self_id()), group, user)
        d = self.limiter.check(key, s)
        if s.log_decisions:
            logger.info(f"[anti_laowu] {'allow' if d.allowed else 'block'} reason={d.reason} "
                        f"group={group} user={user} wait_seconds={d.wait_seconds:.1f} rounds={d.rounds}")
        if d.allowed:
            event.set_extra("anti_laowu_admission", d.admission_id)
        else:
            event.should_call_llm(False)
            event.stop_event()

    @filter.after_message_sent()
    async def record_response(self, event: AstrMessageEvent):
        admission = event.get_extra("anti_laowu_admission")
        result = event.get_result()
        if admission and result is not None and result.chain:
            self.limiter.record_response(admission)

    async def terminate(self):
        self.limiter.close()
