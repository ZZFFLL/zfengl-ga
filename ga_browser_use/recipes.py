from __future__ import annotations

import time
from typing import Any

from ga_browser_use.results import failed_result


SUPPORTED_RECIPES = {"custom_select", "layer_select", "table_locate", "component_wait"}
SUPPORTED_CONDITIONS = {"layer_open", "layer_closed", "options_visible", "field_value", "element_enabled", "not_busy"}


def _safe_timeout(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 10
    if parsed < 0:
        return 1
    return min(60, parsed)


class BrowserRecipeRunner:
    def __init__(self, layer: Any) -> None:
        self.layer = layer
        self._component_wait_poll_interval = 0.2

    @staticmethod
    def _prefer_overlay_match(find_result: dict[str, Any], fallback: dict[str, Any] | None) -> dict[str, Any] | None:
        matches = find_result.get("matches") or []
        for candidate in matches:
            element = candidate.get("element", {})
            layer = candidate.get("layer") or element.get("layer")
            if layer and layer != "main":
                return candidate
        element = (fallback or {}).get("element", {})
        layer = (fallback or {}).get("layer") or element.get("layer")
        return fallback if layer and layer != "main" else None

    def _overlay_target_not_found(self, recipe: str, find_result: dict[str, Any], target_name: str) -> dict[str, Any]:
        result = failed_result(None, "target_not_found", f"Recipe {target_name} was not found in an overlay layer.")
        result["recipe"] = recipe
        result["candidates"] = find_result.get("matches", [])
        if recipe == "layer_select":
            result["recovery"]["code"] = "use_layer_select_recipe"
        elif recipe == "custom_select":
            result["recovery"]["code"] = "use_custom_select_recipe"
        return result

    def _ambiguous(self, recipe: str, find_result: dict[str, Any]) -> dict[str, Any]:
        result = failed_result(None, "ambiguous_target", "Recipe target is ambiguous.")
        result["recipe"] = recipe
        result["candidates"] = find_result.get("matches", [])
        if recipe == "layer_select":
            result["recovery"]["code"] = "use_layer_select_recipe"
        elif recipe == "custom_select":
            result["recovery"]["code"] = "use_custom_select_recipe"
        return result

    def _find_one(
        self,
        driver: Any,
        *,
        recipe: str,
        target: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        target = target or {}
        if target.get("index"):
            index = target["index"]
            return (
                {"status": "success", "matches": [{"index": index, "element": {"index": index}}], "ambiguous": False},
                {"index": index},
            )
        result = self.layer.find(
            driver,
            query=target.get("query") or kwargs.pop("query", None),
            max_results=kwargs.pop("max_results", 5),
            **kwargs,
        )
        if result.get("status") != "success":
            return result, None
        if result.get("ambiguous"):
            return self._ambiguous(recipe, result), None
        matches = result.get("matches") or []
        return result, matches[0] if matches else None

    @staticmethod
    def _with_steps(result: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
        result["steps"] = steps
        return result

    @staticmethod
    def _component_condition_met(condition: str, match: dict[str, Any] | None) -> bool:
        if condition in {"layer_closed", "not_busy"}:
            return match is None
        if condition in {"layer_open", "options_visible"}:
            return match is not None
        if condition == "element_enabled":
            element = (match or {}).get("element", {})
            return match is not None and element.get("disabled") is not True
        if condition == "field_value":
            element = (match or {}).get("element", {})
            return match is not None and bool(element.get("value") or element.get("text"))
        return False

    @staticmethod
    def _find_index_in_state(state: dict[str, Any], index: Any) -> tuple[dict[str, Any], dict[str, Any] | None]:
        try:
            expected_index = int(index)
        except (TypeError, ValueError):
            return failed_result(None, "invalid_args", "target.index must be an integer."), None
        if not isinstance(state, dict) or state.get("status") != "success":
            stage = str((state or {}).get("stage") or "state_missing")
            error = str((state or {}).get("error") or "component_wait requires a successful browser_state.")
            return failed_result(None, stage, error), None
        for element in state.get("elements") or []:
            if not isinstance(element, dict):
                continue
            try:
                element_index = int(element.get("index"))
            except (TypeError, ValueError):
                continue
            if element_index == expected_index:
                match = {"index": expected_index, "element": element}
                return {"status": "success", "matches": [match], "ambiguous": False}, match
        result = failed_result(None, "target_not_found", "Indexed component target was not found in refreshed browser_state.")
        result["recovery"]["code"] = "refresh_state_then_find"
        result["recovery"]["next_tool"] = "browser_find"
        result["recovery"]["next_args"] = {"refresh": True, "max_results": 5}
        return result, None

    def _custom_select(
        self,
        driver: Any,
        *,
        target: dict[str, Any] | None,
        option_text: str,
        timeout: int,
        max_results: int,
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        trigger_find, trigger = self._find_one(driver, recipe="custom_select", target=target, max_results=max_results)
        steps.append({"tool": "browser_find", **trigger_find})
        if not trigger:
            return self._with_steps(trigger_find, steps)

        trigger_index = trigger["index"]
        click_trigger = self.layer.run_action(driver, action="click", index=trigger_index, timeout=timeout)
        steps.append({"tool": "browser_action", **click_trigger})
        if click_trigger.get("status") != "success":
            click_trigger["recipe"] = "custom_select"
            return self._with_steps(click_trigger, steps)

        state = self.layer.get_state(driver, max_elements=120)
        steps.append({"tool": "browser_state", "status": state.get("status")})

        option_find, option = self._find_one(
            driver,
            recipe="custom_select",
            target={"query": option_text},
            max_results=max_results,
        )
        option = self._prefer_overlay_match(option_find, option)
        steps.append({"tool": "browser_find", **option_find})
        if not option:
            if option_find.get("status") == "success":
                option_find = self._overlay_target_not_found("custom_select", option_find, "option")
            return self._with_steps(option_find, steps)

        option_index = option["index"]
        click_option = self.layer.run_action(driver, action="click", index=option_index, timeout=timeout)
        steps.append({"tool": "browser_action", **click_option})
        if click_option.get("status") != "success":
            click_option["recipe"] = "custom_select"
            return self._with_steps(click_option, steps)
        return {"status": "success", "recipe": "custom_select", "steps": steps, "recovery": None}

    def _layer_select(
        self,
        driver: Any,
        *,
        target: dict[str, Any] | None,
        option_text: str,
        confirm_text: str | None,
        timeout: int,
        max_results: int,
    ) -> dict[str, Any]:
        result = self._custom_select(
            driver,
            target=target,
            option_text=option_text,
            timeout=timeout,
            max_results=max_results,
        )
        result["recipe"] = "layer_select"
        if result.get("status") != "success":
            result.setdefault("recovery", {}).update({"code": "use_layer_select_recipe"})
            return result

        if confirm_text:
            confirm_find, confirm = self._find_one(
                driver,
                recipe="layer_select",
                target={"query": confirm_text},
                max_results=max_results,
            )
            confirm = self._prefer_overlay_match(confirm_find, confirm)
            result["steps"].append({"tool": "browser_find", **confirm_find})
            if not confirm:
                if confirm_find.get("status") == "success":
                    confirm_find = self._overlay_target_not_found("layer_select", confirm_find, "confirm target")
                else:
                    confirm_find["recipe"] = "layer_select"
                return self._with_steps(confirm_find, result["steps"])
            confirm_click = self.layer.run_action(driver, action="click", index=confirm["index"], timeout=timeout)
            result["steps"].append({"tool": "browser_action", **confirm_click})
            if confirm_click.get("status") != "success":
                confirm_click["recipe"] = "layer_select"
                return self._with_steps(confirm_click, result["steps"])
        return result

    def _table_locate(self, driver: Any, *, table: dict[str, Any] | None, max_results: int) -> dict[str, Any]:
        table = table or {}
        if not any(table.get(key) for key in ("row_text", "column_text", "header_text")):
            return failed_result(None, "invalid_args", "table_locate requires row_text, column_text, or header_text.")

        result = self.layer.find(driver, table=table, max_results=max_results)
        step = {"tool": "browser_find", **result}
        result["steps"] = [step]
        if result.get("status") == "success":
            if result.get("ambiguous"):
                ambiguous = self._ambiguous("table_locate", result)
                ambiguous["steps"] = [step]
                return ambiguous
            result["recipe"] = "table_locate"
        return result

    def _component_wait(
        self,
        driver: Any,
        *,
        condition: str,
        target: dict[str, Any] | None,
        timeout: int,
        max_results: int,
    ) -> dict[str, Any]:
        if condition not in SUPPORTED_CONDITIONS:
            return failed_result(None, "invalid_args", f"Unsupported browser recipe condition: {condition}")

        safe_timeout = _safe_timeout(timeout)
        deadline = time.monotonic() + safe_timeout
        poll_interval = max(0, float(self._component_wait_poll_interval))
        steps: list[dict[str, Any]] = []
        last_find: dict[str, Any] | None = None

        while True:
            state = self.layer.get_state(driver, max_elements=120)
            steps.append({"tool": "browser_state", "status": state.get("status")})

            if isinstance(target, dict) and target.get("index") is not None:
                find_result, match = self._find_index_in_state(state, target.get("index"))
            else:
                find_result, match = self._find_one(driver, recipe="component_wait", target=target, max_results=max_results)
            last_find = find_result
            steps.append({"tool": "browser_find", **find_result})
            if find_result.get("status") != "success":
                if condition in {"layer_closed", "not_busy"} and find_result.get("stage") == "target_not_found":
                    return {
                        "status": "success",
                        "recipe": "component_wait",
                    "condition": condition,
                    "match": None,
                    "timeout": safe_timeout,
                    "steps": steps,
                    "recovery": None,
                }
                if find_result.get("stage") == "ambiguous_target":
                    find_result["recipe"] = "component_wait"
                    return self._with_steps(find_result, steps)
            elif self._component_condition_met(condition, match):
                return {
                    "status": "success",
                    "recipe": "component_wait",
                    "condition": condition,
                    "match": match,
                    "timeout": safe_timeout,
                    "steps": steps,
                    "recovery": None,
                }

            now = time.monotonic()
            if now >= deadline:
                break
            time.sleep(min(poll_interval, deadline - now))

        result = failed_result(None, "component_not_ready", f"Timed out waiting for component condition: {condition}")
        result["recipe"] = "component_wait"
        result["timeout"] = safe_timeout
        result["recovery"]["code"] = "wait_component"
        result["recovery"]["next_tool"] = "browser_recipe"
        next_args: dict[str, Any] = {
            "recipe": "component_wait",
            "condition": condition,
            "timeout": safe_timeout,
            "max_results": max_results,
        }
        if target:
            next_args["target"] = dict(target)
        result["recovery"]["next_args"] = next_args
        result["last_find"] = last_find
        result["steps"] = steps
        return result

    def run(
        self,
        driver: Any,
        *,
        recipe: str,
        target: dict[str, Any] | None = None,
        option_text: str | None = None,
        confirm_text: str | None = None,
        table: dict[str, Any] | None = None,
        condition: str | None = None,
        timeout: int = 10,
        max_results: int = 5,
        **_: Any,
    ) -> dict[str, Any]:
        recipe = str(recipe or "").strip()
        if recipe not in SUPPORTED_RECIPES:
            return failed_result(None, "invalid_args", f"Unsupported browser recipe: {recipe}")
        if recipe == "custom_select":
            if not option_text:
                return failed_result(None, "invalid_args", "option_text is required for custom_select.")
            return self._custom_select(driver, target=target, option_text=option_text, timeout=timeout, max_results=max_results)
        if recipe == "layer_select":
            if not option_text:
                return failed_result(None, "invalid_args", "option_text is required for layer_select.")
            return self._layer_select(
                driver,
                target=target,
                option_text=option_text,
                confirm_text=confirm_text,
                timeout=timeout,
                max_results=max_results,
            )
        if recipe == "table_locate":
            return self._table_locate(driver, table=table, max_results=max_results)
        return self._component_wait(
            driver,
            condition=condition or "",
            target=target,
            timeout=timeout,
            max_results=max_results,
        )
