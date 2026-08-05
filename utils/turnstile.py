import base64
import json
import random
import time
from typing import Any, Dict, Optional


class OrderedMap:
    def __init__(self) -> None:
        self.keys = []
        self.values = {}

    def add(self, key: str, value: Any) -> None:
        if key not in self.values:
            self.keys.append(key)
        self.values[key] = value


def _turnstile_to_str(value: Any) -> str:
    if value is None:
        return "undefined"
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        special = {
            "window.Math": "[object Math]",
            "window.Reflect": "[object Reflect]",
            "window.performance": "[object Performance]",
            "window.localStorage": "[object Storage]",
            "window.Object": "function Object() { [native code] }",
            "window.Reflect.set": "function set() { [native code] }",
            "window.performance.now": "function () { [native code] }",
            "window.Object.create": "function create() { [native code] }",
            "window.Object.keys": "function keys() { [native code] }",
            "window.Math.random": "function random() { [native code] }",
        }
        return special.get(value, value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ",".join(value)
    return str(value)


def _xor_string(text: str, key: str) -> str:
    if not key:
        return text
    return "".join(chr(ord(ch) ^ ord(key[i % len(key)])) for i, ch in enumerate(text))


def solve_turnstile_token(dx: str, p: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(dx).decode()
        token_list = json.loads(_xor_string(decoded, p))
    except Exception:
        return None

    process_map: Dict[Any, Any] = {}
    start_time = time.time()
    result = ""

    def get_value(key: Any, default: Any = None) -> Any:
        return process_map.get(key, default)

    def set_value(key: Any, value: Any) -> None:
        process_map[key] = value

    def js_abs(value: Any) -> float:
        try:
            return abs(float(value))
        except Exception:
            return 0.0

    def js_prop(obj: Any, key: Any) -> Any:
        if isinstance(obj, OrderedMap):
            return obj.values.get(str(key))
        if isinstance(obj, dict):
            return obj.get(key)
        if isinstance(obj, (list, tuple)):
            try:
                return obj[int(key)]
            except Exception:
                return None
        if isinstance(obj, str):
            key_text = _turnstile_to_str(key)
            if key_text == "location" and obj == "window.document":
                return "https://chatgpt.com/"
            if key_text and key_text not in {"undefined", "None"}:
                return f"{obj}.{key_text}"
        return None

    def call_target(target: Any, args: list[Any]) -> Any:
        if isinstance(target, str):
            if target == "window.performance.now":
                elapsed_ns = time.time_ns() - int(start_time * 1e9)
                return (elapsed_ns + random.random()) / 1e6
            if target == "window.Object.create":
                return OrderedMap()
            if target == "window.Object.keys":
                if args and args[0] == "window.localStorage":
                    return [
                        "STATSIG_LOCAL_STORAGE_INTERNAL_STORE_V4",
                        "STATSIG_LOCAL_STORAGE_STABLE_ID",
                        "client-correlated-secret",
                        "oai/apps/capExpiresAt",
                        "oai-did",
                        "STATSIG_LOCAL_STORAGE_LOGGING_REQUEST",
                        "UiState.isNavigationCollapsed.1",
                    ]
                if args and isinstance(args[0], OrderedMap):
                    return list(args[0].keys)
                if args and isinstance(args[0], dict):
                    return list(args[0].keys())
            if target == "window.Math.random":
                return random.random()
            if target == "window.Reflect.set":
                if len(args) >= 3:
                    obj, key_name, val = args[:3]
                    if isinstance(obj, OrderedMap):
                        obj.add(str(key_name), val)
                        return True
                    if isinstance(obj, dict):
                        obj[str(key_name)] = val
                        return True
                return False
        if callable(target):
            return target(*args)
        return None

    def run_queue(limit: int = 20000) -> None:
        steps = 0
        while isinstance(process_map.get(9), list) and process_map[9]:
            steps += 1
            if steps > limit:
                raise RuntimeError("turnstile_vm_step_limit")
            token = process_map[9].pop(0)
            if not isinstance(token, list) or not token:
                continue
            fn = process_map.get(token[0])
            if not callable(fn):
                continue
            try:
                fn(*token[1:])
            except Exception:
                continue

    def func_1(e: float, t: float) -> None:
        process_map[e] = _xor_string(_turnstile_to_str(get_value(e)), _turnstile_to_str(get_value(t)))

    def func_2(e: float, t: Any) -> None:
        process_map[e] = t

    def func_3(e: str) -> None:
        nonlocal result
        result = base64.b64encode(e.encode()).decode()

    def func_5(e: float, t: float) -> None:
        current = get_value(e)
        incoming = get_value(t)
        if isinstance(current, (list, tuple)):
            process_map[e] = list(current) + [incoming]
            return
        if isinstance(current, (str, float)) or isinstance(incoming, (str, float)):
            process_map[e] = _turnstile_to_str(current) + _turnstile_to_str(incoming)
            return
        process_map[e] = "NaN"

    def func_6(e: float, t: float, n: float) -> None:
        process_map[e] = js_prop(get_value(t), get_value(n))

    def func_7(e: float, *args: float) -> None:
        call_target(get_value(e), [get_value(arg) for arg in args])

    def func_8(e: float, t: float) -> None:
        process_map[e] = process_map[t]

    def func_13(e: float, t: float, *args: float) -> None:
        try:
            call_target(get_value(t), list(args))
        except Exception as exc:
            process_map[e] = str(exc)

    def func_14(e: float, t: float) -> None:
        process_map[e] = json.loads(process_map[t])

    def func_15(e: float, t: float) -> None:
        process_map[e] = json.dumps(process_map[t])

    def func_17(e: float, t: float, *args: float) -> None:
        process_map[e] = call_target(get_value(t), [get_value(arg) for arg in args])

    def func_18(e: float) -> None:
        process_map[e] = base64.b64decode(_turnstile_to_str(process_map[e])).decode()

    def func_19(e: float) -> None:
        process_map[e] = base64.b64encode(_turnstile_to_str(process_map[e]).encode()).decode()

    def func_20(e: float, t: float, n: float, *args: float) -> None:
        if get_value(e) == get_value(t):
            target = get_value(n)
            if callable(target):
                target(*args)

    def func_21(e: float, t: float, n: float, r: float, *args: float) -> None:
        try:
            delta = float(get_value(e)) - float(get_value(t))
        except Exception:
            delta = 0.0
        if abs(delta) > js_abs(get_value(n)):
            target = get_value(r)
            if callable(target):
                target(*args)

    def func_22(e: float, queue: list[Any]) -> None:
        previous = list(process_map.get(9) or [])
        process_map[9] = list(queue or [])
        run_queue()
        process_map[e] = "None"
        process_map[9] = previous

    def func_23(e: float, t: float, *args: float) -> None:
        if get_value(e) is not None and callable(get_value(t)):
            process_map[t](*args)

    def func_24(e: float, t: float, n: float) -> None:
        process_map[e] = js_prop(get_value(t), get_value(n))

    def func_27(e: float, t: float) -> None:
        current = get_value(e)
        incoming = get_value(t)
        if isinstance(current, list):
            try:
                current.pop(current.index(incoming))
            except ValueError:
                pass
            return
        try:
            process_map[e] = current - incoming
        except Exception:
            process_map[e] = 0

    def func_29(e: float, t: float, n: float) -> None:
        try:
            process_map[e] = get_value(t) < get_value(n)
        except Exception:
            process_map[e] = False

    def func_30(e: float, t: float, n: float, r: Any = None) -> None:
        is_array = isinstance(r, list)
        capture_keys = n if is_array else []
        queue = r if is_array else n
        queue = list(queue or [])

        def subroutine(*call_args: Any) -> None:
            previous = list(process_map.get(9) or [])
            if is_array:
                for index, key in enumerate(capture_keys):
                    if index < len(call_args):
                        process_map[key] = call_args[index]
            process_map[9] = list(queue)
            run_queue()
            process_map[9] = previous

        process_map[e] = subroutine

    def func_33(e: float, t: float, n: float) -> None:
        try:
            process_map[e] = float(get_value(t)) * float(get_value(n))
        except Exception:
            process_map[e] = 0

    def func_34(e: float, t: float) -> None:
        process_map[e] = get_value(t)

    def noop(*_: Any) -> None:
        return

    process_map.update({
        1: func_1,
        2: func_2,
        3: func_3,
        5: func_5,
        6: func_6,
        7: func_7,
        8: func_8,
        9: token_list,
        10: "window",
        11: lambda e, t: set_value(e, None),
        12: lambda e: set_value(e, process_map),
        13: func_13,
        14: func_14,
        15: func_15,
        16: p,
        17: func_17,
        18: func_18,
        19: func_19,
        20: func_20,
        21: func_21,
        22: func_22,
        23: func_23,
        24: func_24,
        25: noop,
        26: noop,
        27: func_27,
        28: noop,
        29: func_29,
        30: func_30,
        33: func_33,
        34: func_34,
    })

    run_queue()
    return result or None
