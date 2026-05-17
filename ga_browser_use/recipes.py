from __future__ import annotations

from typing import Any

from ga_browser_use.results import failed_result


SUPPORTED_RECIPES = {"custom_select", "layer_select", "table_locate", "component_wait"}
SUPPORTED_CONDITIONS = {"layer_open", "layer_closed", "options_visible", "field_value", "element_enabled", "not_busy"}


class BrowserRecipeRunner:
    def __init__(self, layer: Any) -> None:
        self.layer = layer

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
            layer=None,
            max_results=max_results,
        )
        steps.append({"tool": "browser_find", **option_find})
        if not option:
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
            result["steps"].append({"tool": "browser_find", **confirm_find})
            if not confirm:
                confirm_find["recipe"] = "layer_select"
                return self._with_steps(confirm_find, result["steps"])
            confirm_click = self.layer.run_action(driver, action="click", index=confirm["index"], timeout=timeout)
            result["steps"].append({"tool": "browser_action", **confirm_click})
            if confirm_click.get("status") != "success":
                confirm_click["recipe"] = "layer_select"
                return self._with_steps(confirm_click, result["steps"])
        return result

    def _table_locate(self, driver: Any, *, table: dict[str, Any] | None, max_results: int) -> dict[str, Any]:
        result = self.layer.find(driver, table=table or {}, max_results=max_results)
        step = {"tool": "browser_find", **result}
        result["steps"] = [step]
        if result.get("status") == "success":
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

        find_result, match = self._find_one(driver, recipe="component_wait", target=target, max_results=max_results)
        steps = [{"tool": "browser_find", **find_result}]
        if match:
            return {
                "status": "success",
                "recipe": "component_wait",
                "condition": condition,
                "match": match,
                "steps": steps,
                "recovery": None,
            }
        result = failed_result(None, "component_not_ready", f"Timed out waiting for component condition: {condition}")
        result["recipe"] = "component_wait"
        result["recovery"]["code"] = "wait_component"
        result["recovery"]["next_tool"] = "browser_recipe"
        result["recovery"]["next_args"] = {"recipe": "component_wait", "condition": condition, "timeout": timeout}
        result["last_find"] = find_result
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
