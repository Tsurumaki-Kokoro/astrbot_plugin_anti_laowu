import asyncio
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from limiter import Limiter, Settings


class LimiterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000.0
        self.path = Path(self.tmp.name) / 'state.db'
        self.l = Limiter(self.path, clock=lambda: self.now, rng=lambda: 0.5)
        self.s = Settings()
        self.key = ('llbot', 'test-bot', 'group1', 'target-user')

    def tearDown(self):
        self.l.close()
        self.tmp.cleanup()

    def test_cooldown_and_two_round_pause(self):
        self.assertTrue(self.l.check(self.key, self.s).allowed)
        self.now += 179
        self.assertEqual(self.l.check(self.key, self.s).reason, 'cooldown')
        self.now += 1
        self.assertEqual(self.l.check(self.key, self.s).rounds, 2)
        self.now += 180
        self.assertEqual(self.l.check(self.key, self.s).reason, 'conversation_pause')
        self.now += 120
        self.assertEqual(self.l.check(self.key, self.s).rounds, 1)

    def test_block_does_not_extend_cooldown(self):
        self.l.check(self.key, self.s)
        for _ in range(179):
            self.now += 1
            self.assertFalse(self.l.check(self.key, self.s).allowed)
        self.now += 1
        self.assertTrue(self.l.check(self.key, self.s).allowed)

    def test_scope_and_bot_isolation(self):
        self.l.check(self.key, self.s)
        for key in [('llbot', 'test-bot', 'group2', 'target-user'),
                    ('llbot', 'test-bot', 'group1', 'other'),
                    ('llbot', 'otherbot', 'group1', 'target-user')]:
            self.assertTrue(self.l.check(key, self.s).allowed)

    def test_restart_preserves_cooldown(self):
        self.l.check(self.key, self.s)
        self.l.close()
        self.l = Limiter(self.path, clock=lambda: self.now)
        self.assertFalse(self.l.check(self.key, self.s).allowed)

    def test_probability_zero_and_one(self):
        self.assertFalse(self.l.check(self.key, replace(self.s, allow_probability=0)).allowed)
        self.assertTrue(self.l.check(self.key, self.s).allowed)

    def test_inactivity_resets_rounds(self):
        self.l.check(self.key, self.s)
        self.now += 600
        self.assertEqual(self.l.check(self.key, self.s).rounds, 1)

    def test_response_callback_does_not_refund_quota(self):
        d = self.l.check(self.key, self.s)
        self.l.record_response(d.admission_id)
        self.l.record_response(d.admission_id)
        self.assertFalse(self.l.check(self.key, self.s).allowed)

    def test_clock_rollback(self):
        self.l.check(self.key, self.s)
        self.now -= 1
        self.assertEqual(self.l.check(self.key, self.s).reason, 'clock_rollback')

    def test_config_validation_and_schema_defaults(self):
        defaults = {k: v['default'] for k, v in json.loads((ROOT/'_conf_schema.json').read_text(encoding='utf-8-sig')).items()}
        self.assertEqual(Settings.from_config(defaults), self.s)
        s = Settings.from_config({'allow_probability': 'nan', 'cooldown_seconds': -3, 'max_consecutive_rounds': 'oops'})
        self.assertEqual((s.allow_probability, s.cooldown_seconds, s.max_rounds), (1, 0, 2))

    def test_no_account_is_targeted_by_default(self):
        self.assertEqual(Settings().target_ids, frozenset())
        self.assertEqual(Settings.from_config({}).target_ids, frozenset())


def load_adapter():
    """Minimal protocol doubles; actual AstrBot smoke test is separate."""
    api = types.ModuleType('astrbot.api')
    api.AstrBotConfig = dict
    api.logger = types.SimpleNamespace(info=lambda *a: None)
    event = types.ModuleType('astrbot.api.event')
    def decorator(*a, **kw):
        def wrap(fn):
            fn.priority = kw.get('priority', 0)
            return fn
        return wrap
    event.filter = types.SimpleNamespace(event_message_type=decorator, after_message_sent=decorator,
                                        EventMessageType=types.SimpleNamespace(GROUP_MESSAGE='group'))
    event.AstrMessageEvent = object
    star = types.ModuleType('astrbot.api.star')
    class Star:
        def __init__(self, context): pass
    star.Star = Star
    star.Context = object
    star.register = lambda *a: lambda cls: cls
    star.StarTools = types.SimpleNamespace(get_data_dir=lambda: Path(tempfile.gettempdir()))
    for name, mod in [('astrbot', types.ModuleType('astrbot')), ('astrbot.api', api),
                      ('astrbot.api.event', event), ('astrbot.api.star', star)]:
        sys.modules[name] = mod
    package = types.ModuleType('anti_test')
    package.__path__ = [str(ROOT)]
    sys.modules['anti_test'] = package
    spec = importlib.util.spec_from_file_location('anti_test.main', ROOT/'main.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.AntiLaowu


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_before_chat_plus_and_no_mention_bypass(self):
        cls = load_adapter()
        self.assertGreater(cls.guard.priority, sys.maxsize-1)
        with tempfile.TemporaryDirectory() as tmp:
            plugin = object.__new__(cls)
            plugin.config = {"target_qq_ids": ["target-user"]}
            plugin.limiter = Limiter(Path(tmp)/'state.db', clock=lambda: 1000)
            class Event:
                message_str = 'Mint 你好'
                user = 'target-user'
                stopped = False
                extras = None
                def get_sender_id(self): return self.user
                def get_group_id(self): return 'g'
                def get_platform_id(self): return 'llbot'
                def get_self_id(self): return 'bot'
                def is_admin(self): return False
                def set_extra(self, k, v): self.extras = {k: v}
                def should_call_llm(self, v): self.call_llm = v
                def stop_event(self): self.stopped = True
            first = Event()
            plugin.config = {}
            await plugin.guard(first)
            self.assertIsNone(first.extras)
            plugin.config = {"target_qq_ids": ["target-user"]}
            await plugin.guard(first)
            self.assertFalse(first.stopped)
            for text in ['Mint 你好', '薄绿', '你好', '这句话引用了机器人']:
                e = Event()
                e.message_str = text
                await plugin.guard(e)
                self.assertTrue(e.stopped)
                self.assertFalse(e.call_llm)
            other = Event()
            other.user = 'other'
            await plugin.guard(other)
            self.assertFalse(other.stopped)
            command = Event()
            command.message_str = '/点歌 test'
            await plugin.guard(command)
            self.assertFalse(command.stopped)
            await plugin.terminate()


if __name__ == '__main__':
    unittest.main()
