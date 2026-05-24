import json, re, os
import time
from dataclasses import dataclass
from typing import Any, Optional
try: from plugins.hooks import trigger as _hook
except ImportError: _hook = lambda *a, **k: None
@dataclass
class StepOutcome:
    data: Any
    next_prompt: Optional[str] = None
    should_exit: bool = False
def try_call_generator(func, *args, **kwargs):
    ret = func(*args, **kwargs)
    if hasattr(ret, '__iter__') and not isinstance(ret, (str, bytes, dict, list)): ret = yield from ret
    return ret

class BaseHandler:
    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason): return next_prompt
    def dispatch(self, tool_name, args, response, index=0, tool_num=1):
        method_name = f"do_{tool_name}"
        if hasattr(self, method_name):
            args['_index'] = index; args['_tool_num'] = tool_num
            _hook('tool_before', locals())
            ret = yield from try_call_generator(getattr(self, method_name), args, response)
            _hook('tool_after', locals())
            return ret
        elif tool_name == 'bad_json': return StepOutcome(None, next_prompt=args.get('msg', 'bad_json'), should_exit=False)
        else:
            yield f"未知工具: {tool_name}\n"
            return StepOutcome(None, next_prompt=f"未知工具 {tool_name}", should_exit=False)

def json_default(o): return list(o) if isinstance(o, set) else str(o)
def exhaust(g):
    try: 
        while True: next(g)
    except StopIteration as e: return e.value

def get_pretty_json(data):
    if isinstance(data, dict) and "script" in data:
        data = data.copy(); data["script"] = data["script"].replace("; ", ";\n  ")
    return json.dumps(data, indent=2, ensure_ascii=False).replace('\\n', '\n')

def _emit_event(event_sink, event_type, **data):
    if event_sink is None:
        return
    event = {"type": event_type, **data}
    try:
        event_sink(event)
    except Exception:
        pass

def _tool_kind(tool_name):
    name = str(tool_name or "").lower()
    if "code" in name or "shell" in name or "command" in name:
        return "command"
    if "web" in name or "scan" in name or "search" in name or "browse" in name:
        return "search"
    if "read" in name:
        return "read"
    if "file" in name or "write" in name or "patch" in name:
        return "file"
    return "tool"

def agent_runner_loop(client, system_prompt, user_input, handler, tools_schema,
                      max_turns=40, verbose=True, initial_user_content=None,
                      yield_info=False, event_sink=None):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user_content if initial_user_content is not None else user_input}
    ]
    turn = 0;  handler.max_turns = max_turns
    _hook('agent_before', locals())
    while turn < handler.max_turns:
        turn += 1; _emit_event(event_sink, "turn.start", turn=turn); turnstr = f'LLM Running (Turn {turn}) ...'
        if handler.parent.task_dir: turnstr = f'Turn {turn} ...'
        if verbose: turnstr = f'**{turnstr}**'
        if yield_info: yield {'turn': turn}
        yield f"\n\n{turnstr}\n\n"
        if turn%10 == 0: client.last_tools = ''  # 每10轮重置一次工具描述
        _hook('turn_before', locals())
        _hook('llm_before', locals())
        _emit_event(event_sink, "llm.start", turn=turn)
        llm_started_at = time.time()
        response_gen = client.chat(messages=messages, tools=tools_schema)
        if verbose:
            response = yield from response_gen
            yield '\n\n'
        else:
            response = exhaust(response_gen)
            cleaned = _clean_content(response.content)
            if cleaned: yield cleaned + '\n'
        llm_elapsed_ms = int((time.time() - llm_started_at) * 1000)
        _hook('llm_after', locals())
        _emit_event(
            event_sink,
            "llm.end",
            turn=turn,
            text=getattr(response, "content", "") or "",
            has_tools=bool(getattr(response, "tool_calls", None)),
            elapsed_ms=llm_elapsed_ms,
        )

        if not response.tool_calls: tool_calls = [{'tool_name': 'no_tool', 'args': {}}]
        else: tool_calls = [{'tool_name': tc.function.name, 'args': json.loads(tc.function.arguments), 'id': tc.id}
                          for tc in response.tool_calls]
       
        tool_results = []; next_prompts = set(); exit_reason = {}
        for ii, tc in enumerate(tool_calls):
            tool_name, args, tid = tc['tool_name'], tc['args'], tc.get('id', '')
            public_args = {k: v for k, v in args.items() if k not in ("_index", "_tool_num")}
            if tool_name == 'no_tool': pass
            else: 
                if verbose: yield f"🛠️ Tool: `{tool_name}`  📥 args:\n````text\n{get_pretty_json(args)}\n````\n"
                else: yield f"🛠️ {tool_name}({_compact_tool_args(tool_name, args)})\n\n\n"
            handler.current_turn = turn
            gen = handler.dispatch(tool_name, args, response, index=ii, tool_num=len(tool_calls))
            tool_started_at = time.time()
            if tool_name != 'no_tool':
                _emit_event(
                    event_sink,
                    "tool.start",
                    turn=turn,
                    index=ii,
                    total=len(tool_calls),
                    tool_call_id=tid,
                    tool_name=tool_name,
                    tool_kind=_tool_kind(tool_name),
                    args=public_args,
                )
            tool_chunks = []
            try:
                v = next(gen)
                if verbose: yield '`````\n'
                def proxy(): yield v; return (yield from gen)
                proxy_gen = proxy()
                while True:
                    try:
                        chunk = next(proxy_gen)
                    except StopIteration as e:
                        outcome = e.value
                        break
                    if tool_name != 'no_tool':
                        text_chunk = str(chunk)
                        tool_chunks.append(text_chunk)
                        _emit_event(
                            event_sink,
                            "tool.delta",
                            turn=turn,
                            index=ii,
                            tool_call_id=tid,
                            tool_name=tool_name,
                            tool_kind=_tool_kind(tool_name),
                            delta=text_chunk,
                        )
                    if verbose:
                        yield chunk
                if verbose: yield '`````\n'
            except StopIteration as e: outcome = e.value
            if tool_name != 'no_tool':
                elapsed_ms = int((time.time() - tool_started_at) * 1000)
                failed = isinstance(getattr(outcome, "data", None), str) and "[Error]" in outcome.data
                _emit_event(
                    event_sink,
                    "tool.end",
                    turn=turn,
                    index=ii,
                    tool_call_id=tid,
                    tool_name=tool_name,
                    tool_kind=_tool_kind(tool_name),
                    status="failed" if failed else "done",
                    result=getattr(outcome, "data", None),
                    output="".join(tool_chunks),
                    elapsed_ms=elapsed_ms,
                )
            
            if outcome.should_exit: 
                exit_reason = {'result': 'EXITED', 'data': outcome.data}
                _emit_event(event_sink, "agent.final", turn=turn, text=str(getattr(response, "content", "") or ""), exit_reason=exit_reason)
                break
            if not outcome.next_prompt: 
                exit_reason = {'result': 'CURRENT_TASK_DONE', 'data': outcome.data}
                _emit_event(event_sink, "agent.final", turn=turn, text=str(getattr(response, "content", "") or ""), exit_reason=exit_reason)
                break
            if outcome.next_prompt.startswith('未知工具'): client.last_tools = ''
            if outcome.data is not None and tool_name != 'no_tool': 
                datastr = json.dumps(outcome.data, ensure_ascii=False, default=json_default) if type(outcome.data) in [dict, list] else str(outcome.data) 
                tool_results.append({'tool_use_id': tid, 'content': datastr})
            next_prompts.add(outcome.next_prompt)
        if len(next_prompts) == 0 or exit_reason:
            if len(handler._done_hooks) == 0 or exit_reason.get('result', '') == 'EXITED':
                _emit_event(event_sink, "turn.end", turn=turn, exit_reason=exit_reason)
                break
            next_prompts.add(handler._done_hooks.pop(0))
        next_prompt = handler.turn_end_callback(response, tool_calls, tool_results, turn, '\n'.join(next_prompts), exit_reason)
        _emit_event(event_sink, "turn.end", turn=turn, exit_reason=exit_reason)
        _hook('turn_after', locals())
        messages = [{"role": "user", "content": next_prompt, "tool_results": tool_results}]   # just new message, history is kept in *Session
    if exit_reason: handler.turn_end_callback(response, tool_calls, tool_results, turn, '', exit_reason)
    _hook('agent_after', locals())
    _emit_event(event_sink, "agent.done", turn=turn, exit_reason=exit_reason or {'result': 'MAX_TURNS_EXCEEDED'})
    return exit_reason or {'result': 'MAX_TURNS_EXCEEDED'}

def _clean_content(text):
    if not text: return ''
    def _shrink_code(m):
        lines = m.group(0).split('\n')
        lang = lines[0].replace('```','').strip()
        body = [l for l in lines[1:-1] if l.strip()]
        if len(body) <= 6: return m.group(0)
        preview = '\n'.join(body[:5])
        return f'```{lang}\n{preview}\n  ... ({len(body)} lines)\n```'
    text = re.sub(r'```[\s\S]*?```', _shrink_code, text)
    for p in [r'<file_content>[\s\S]*?</file_content>', r'<tool_(?:use|call)>[\s\S]*?</tool_(?:use|call)>', r'(\r?\n){3,}']:
        text = re.sub(p, '\n\n' if '\\n' in p else '', text)
    return text.strip()

def _compact_tool_args(name, args):
    a = {k: v for k, v in args.items() if k != '_index'}
    for k in ('path',): 
        if k in a: a[k] = os.path.basename(a[k])
    if name == 'update_working_checkpoint': s = a.get('key_info', ''); return (s[:60]+'...') if len(s)>60 else s
    if name == 'ask_user':
        q = str(a.get('question', ''))
        cs = a.get('candidates') or []
        if cs: q += '\ncandidates:\n' + '\n'.join(f'- {c}' for c in cs)
        return q
    s = json.dumps(a, ensure_ascii=False); return (s[:120]+'...') if len(s)>120 else s
