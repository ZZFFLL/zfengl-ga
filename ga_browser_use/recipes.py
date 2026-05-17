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
    def _tab_kwargs(switch_tab_id: str | None) -> dict[str, str]:
        return {"switch_tab_id": switch_tab_id} if switch_tab_id else {}

    @staticmethod
    def _target_index(target: dict[str, Any] | None) -> int | None:
        if not isinstance(target, dict) or target.get("index") is None:
            return None
        try:
            index = int(target.get("index"))
        except (TypeError, ValueError):
            return None
        return index if index > 0 else None

    @classmethod
    def _validate_target(cls, recipe: str, target: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(target, dict):
            return cls._invalid_target(recipe)
        if target.get("index") is not None and cls._target_index(target) is None:
            result = failed_result(None, "invalid_args", "target.index must be a positive integer.")
            result["recipe"] = recipe
            result["recovery"] = cls._bounded_target_recovery(recipe)
            return result
        if cls._target_index(target) is not None or str(target.get("query") or "").strip():
            return None
        return cls._invalid_target(recipe)

    @staticmethod
    def _bounded_target_recovery(recipe: str) -> dict[str, Any]:
        return {
            "code": "provide_bounded_target",
            "message": f"Retry {recipe} with target.index from a known browser_state or target.query with specific visible text.",
            "stop_retry": True,
        }

    @staticmethod
    def _invalid_target(recipe: str) -> dict[str, Any]:
        if recipe == "component_wait":
            error = "component_wait requires target.query."
        else:
            error = f"{recipe} requires target.query or target.index."
        result = failed_result(None, "invalid_args", error)
        result["recipe"] = recipe
        result["recovery"] = BrowserRecipeRunner._bounded_target_recovery(recipe)
        return result

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

    @staticmethod
    def _recipe_retry_args(
        recipe: str,
        *,
        target: dict[str, Any] | None = None,
        option_text: str | None = None,
        confirm_text: str | None = None,
        timeout: int | None = None,
        max_results: int | None = None,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any] | None:
        args: dict[str, Any] = {"recipe": recipe}
        if recipe in {"custom_select", "layer_select"}:
            if not isinstance(target, dict) or not option_text:
                return None
            args["target"] = dict(target)
            args["option_text"] = option_text
            if recipe == "layer_select" and confirm_text:
                args["confirm_text"] = confirm_text
        if timeout is not None:
            args["timeout"] = timeout
        if max_results is not None:
            args["max_results"] = max_results
        if switch_tab_id:
            args["switch_tab_id"] = switch_tab_id
        return args

    @staticmethod
    def _recipe_recovery(
        recipe: str,
        stage: str,
        *,
        target: dict[str, Any] | None = None,
        option_text: str | None = None,
        confirm_text: str | None = None,
        timeout: int | None = None,
        max_results: int | None = None,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        if recipe == "layer_select":
            if stage == "ambiguous_target":
                message = "Retry layer_select with a more specific target, option_text, or confirm_text so only one overlay candidate matches."
            else:
                message = "Retry layer_select with bounded target, option_text, and optional confirm_text that match the opened overlay."
            next_args = BrowserRecipeRunner._recipe_retry_args(
                recipe,
                target=target,
                option_text=option_text,
                confirm_text=confirm_text,
                timeout=timeout,
                max_results=max_results,
                switch_tab_id=switch_tab_id,
            )
            if next_args is None:
                return {
                    "code": "use_layer_select_recipe",
                    "message": f"{message} The current failure does not include enough arguments to retry safely.",
                    "stop_retry": True,
                }
            return {
                "code": "use_layer_select_recipe",
                "message": message,
                "stop_retry": False,
                "next_tool": "browser_recipe",
                "next_args": next_args,
            }
        if recipe == "custom_select":
            if stage == "ambiguous_target":
                message = "Retry custom_select with a more specific target or option_text so only one overlay candidate matches."
            else:
                message = "Retry custom_select with a bounded trigger target and option_text that appears in the opened overlay."
            next_args = BrowserRecipeRunner._recipe_retry_args(
                recipe,
                target=target,
                option_text=option_text,
                timeout=timeout,
                max_results=max_results,
                switch_tab_id=switch_tab_id,
            )
            if next_args is None:
                return {
                    "code": "use_custom_select_recipe",
                    "message": f"{message} The current failure does not include enough arguments to retry safely.",
                    "stop_retry": True,
                }
            return {
                "code": "use_custom_select_recipe",
                "message": message,
                "stop_retry": False,
                "next_tool": "browser_recipe",
                "next_args": next_args,
            }
        return dict(failed_result(None, stage, "Recipe recovery is unavailable.")["recovery"])

    def _overlay_target_not_found(
        self,
        recipe: str,
        find_result: dict[str, Any],
        target_name: str,
        *,
        recovery_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = failed_result(None, "target_not_found", f"Recipe {target_name} was not found in an overlay layer.")
        result["recipe"] = recipe
        result["candidates"] = find_result.get("matches", [])
        if recipe in {"layer_select", "custom_select"}:
            result["recovery"] = self._recipe_recovery(recipe, "target_not_found", **(recovery_args or {}))
        return result

    def _ambiguous(
        self,
        recipe: str,
        find_result: dict[str, Any],
        *,
        recovery_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = failed_result(None, "ambiguous_target", "Recipe target is ambiguous.")
        result["recipe"] = recipe
        result["candidates"] = find_result.get("matches", [])
        if recipe in {"layer_select", "custom_select"}:
            result["recovery"] = self._recipe_recovery(recipe, "ambiguous_target", **(recovery_args or {}))
        return result

    def _find_one(
        self,
        driver: Any,
        *,
        recipe: str,
        target: dict[str, Any] | None = None,
        recovery_args: dict[str, Any] | None = None,
        switch_tab_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        target = target or {}
        index = self._target_index(target)
        if index is not None:
            return (
                {"status": "success", "matches": [{"index": index, "element": {"index": index}}], "ambiguous": False},
                {"index": index},
            )
        result = self.layer.find(
            driver,
            query=target.get("query") or kwargs.pop("query", None),
            max_results=kwargs.pop("max_results", 5),
            **self._tab_kwargs(switch_tab_id),
            **kwargs,
        )
        if result.get("status") != "success":
            return result, None
        if result.get("ambiguous"):
            return self._ambiguous(recipe, result, recovery_args=recovery_args), None
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
            if match is None:
                return False
            if (
                element.get("control_kind") in {"native_input", "textarea", "date_input", "native_select"}
                and element.get("value")
            ):
                return True
            if element.get("control_kind") == "contenteditable":
                return bool(str(element.get("text") or "").strip())
            return False
        return False

    def _match_for_condition(
        self,
        condition: str,
        matches: list[dict[str, Any]],
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if condition not in {"element_enabled", "field_value"}:
            return fallback
        for candidate in matches:
            if self._component_condition_met(condition, candidate):
                return candidate
        return fallback

    @staticmethod
    def _selection_texts(match: dict[str, Any] | None) -> list[str]:
        element = (match or {}).get("element", {})
        if not isinstance(element, dict):
            return []
        values = [element.get("value"), element.get("text")]
        values.extend(element.get("labels") or [])
        return [str(value) for value in values if str(value or "").strip()]

    @classmethod
    def _selection_landed(cls, match: dict[str, Any] | None, option_text: str) -> bool:
        expected = str(option_text or "").strip()
        if not expected:
            return False
        return any(expected in value for value in cls._selection_texts(match))

    def _component_not_ready(
        self,
        recipe: str,
        message: str,
        *,
        recovery_args: dict[str, Any],
        steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = failed_result(None, "component_not_ready", message)
        result["recipe"] = recipe
        result["recovery"] = self._recipe_recovery(recipe, "component_not_ready", **recovery_args)
        return self._with_steps(result, steps)

    def _verify_select_landed(
        self,
        driver: Any,
        *,
        recipe: str,
        target: dict[str, Any],
        option_text: str,
        timeout: int,
        max_results: int,
        recovery_args: dict[str, Any],
        steps: list[dict[str, Any]],
        require_overlay_closed: bool,
        switch_tab_id: str | None,
    ) -> dict[str, Any] | None:
        state = self.layer.get_state(driver, max_elements=120, **self._tab_kwargs(switch_tab_id))
        steps.append({"tool": "browser_state", "status": state.get("status")})
        if state.get("status") != "success":
            state["recipe"] = recipe
            return self._with_steps(state, steps)

        target_match: dict[str, Any] | None = None
        has_query_target = bool(str(target.get("query") or "").strip())
        if has_query_target:
            target_find, target_match = self._find_one(
                driver,
                recipe=recipe,
                target=target,
                max_results=max_results,
                recovery_args=recovery_args,
                switch_tab_id=switch_tab_id,
            )
            steps.append({"tool": "browser_find", **target_find})
            if target_find.get("status") != "success":
                target_find["recipe"] = recipe
                return self._with_steps(target_find, steps)
        else:
            # Indexes are scoped to the previous snapshot. After a select opens/closes
            # an overlay, a refreshed state may legitimately renumber elements.
            target_match = None

        if has_query_target and not self._selection_landed(target_match, option_text):
            return self._component_not_ready(
                recipe,
                "Selection did not land on the target field after clicking the option.",
                recovery_args=recovery_args,
                steps=steps,
            )

        if not require_overlay_closed:
            return None

        option_find, option = self._find_one(
            driver,
            recipe=recipe,
            target={"query": option_text},
            max_results=max_results,
            recovery_args=recovery_args,
            switch_tab_id=switch_tab_id,
        )
        steps.append({"tool": "browser_find", **option_find})
        if option_find.get("status") == "success" and self._prefer_overlay_match(option_find, option):
            return self._component_not_ready(
                recipe,
                "Selection overlay is still open after clicking the option.",
                recovery_args=recovery_args,
                steps=steps,
            )
        if option_find.get("status") != "success" and option_find.get("stage") != "target_not_found":
            option_find["recipe"] = recipe
            return self._with_steps(option_find, steps)
        if not has_query_target:
            return self._component_not_ready(
                recipe,
                "Selection cannot be verified for an index target after clicking the option.",
                recovery_args=recovery_args,
                steps=steps,
            )
        return None

    def _custom_select(
        self,
        driver: Any,
        *,
        target: dict[str, Any] | None,
        option_text: str,
        timeout: int,
        max_results: int,
        require_overlay_closed: bool = True,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        target_error = self._validate_target("custom_select", target)
        if target_error:
            return target_error

        steps: list[dict[str, Any]] = []
        recovery_args = {
            "target": target,
            "option_text": option_text,
            "timeout": timeout,
            "max_results": max_results,
            "switch_tab_id": switch_tab_id,
        }
        trigger_find, trigger = self._find_one(
            driver,
            recipe="custom_select",
            target=target,
            max_results=max_results,
            recovery_args=recovery_args,
            switch_tab_id=switch_tab_id,
        )
        steps.append({"tool": "browser_find", **trigger_find})
        if not trigger:
            return self._with_steps(trigger_find, steps)

        trigger_index = trigger["index"]
        click_trigger = self.layer.run_action(
            driver,
            action="click",
            index=trigger_index,
            timeout=timeout,
            **self._tab_kwargs(switch_tab_id),
        )
        steps.append({"tool": "browser_action", **click_trigger})
        if click_trigger.get("status") != "success":
            click_trigger["recipe"] = "custom_select"
            return self._with_steps(click_trigger, steps)

        state = self.layer.get_state(driver, max_elements=120, **self._tab_kwargs(switch_tab_id))
        steps.append({"tool": "browser_state", "status": state.get("status")})

        option_find, option = self._find_one(
            driver,
            recipe="custom_select",
            target={"query": option_text},
            max_results=max_results,
            recovery_args=recovery_args,
            switch_tab_id=switch_tab_id,
        )
        option = self._prefer_overlay_match(option_find, option)
        steps.append({"tool": "browser_find", **option_find})
        if not option:
            if option_find.get("status") == "success":
                option_find = self._overlay_target_not_found(
                    "custom_select",
                    option_find,
                    "option",
                    recovery_args=recovery_args,
                )
            return self._with_steps(option_find, steps)

        option_index = option["index"]
        click_option = self.layer.run_action(
            driver,
            action="click",
            index=option_index,
            timeout=timeout,
            **self._tab_kwargs(switch_tab_id),
        )
        steps.append({"tool": "browser_action", **click_option})
        if click_option.get("status") != "success":
            click_option["recipe"] = "custom_select"
            return self._with_steps(click_option, steps)
        verification = self._verify_select_landed(
            driver,
            recipe="custom_select",
            target=target or {},
            option_text=option_text,
            timeout=timeout,
            max_results=max_results,
            recovery_args=recovery_args,
            steps=steps,
            require_overlay_closed=require_overlay_closed,
            switch_tab_id=switch_tab_id,
        )
        if verification:
            return verification
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
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        target_error = self._validate_target("layer_select", target)
        if target_error:
            return target_error

        result = self._custom_select(
            driver,
            target=target,
            option_text=option_text,
            timeout=timeout,
            max_results=max_results,
            require_overlay_closed=not bool(confirm_text),
            switch_tab_id=switch_tab_id,
        )
        result["recipe"] = "layer_select"
        if result.get("status") != "success":
            recovery = result.get("recovery")
            if not (isinstance(recovery, dict) and recovery.get("stop_retry") is True):
                result["recovery"] = self._recipe_recovery(
                    "layer_select",
                    str(result.get("stage") or ""),
                    target=target,
                    option_text=option_text,
                    confirm_text=confirm_text,
                    timeout=timeout,
                    max_results=max_results,
                    switch_tab_id=switch_tab_id,
                )
            return result

        if confirm_text:
            recovery_args = {
                "target": target,
                "option_text": option_text,
                "confirm_text": confirm_text,
                "timeout": timeout,
                "max_results": max_results,
                "switch_tab_id": switch_tab_id,
            }
            confirm_find, confirm = self._find_one(
                driver,
                recipe="layer_select",
                target={"query": confirm_text},
                max_results=max_results,
                recovery_args=recovery_args,
                switch_tab_id=switch_tab_id,
            )
            confirm = self._prefer_overlay_match(confirm_find, confirm)
            result["steps"].append({"tool": "browser_find", **confirm_find})
            if not confirm:
                if confirm_find.get("status") == "success":
                    confirm_find = self._overlay_target_not_found(
                        "layer_select",
                        confirm_find,
                        "confirm target",
                        recovery_args=recovery_args,
                    )
                else:
                    confirm_find["recipe"] = "layer_select"
                return self._with_steps(confirm_find, result["steps"])
            confirm_click = self.layer.run_action(
                driver,
                action="click",
                index=confirm["index"],
                timeout=timeout,
                **self._tab_kwargs(switch_tab_id),
            )
            result["steps"].append({"tool": "browser_action", **confirm_click})
            if confirm_click.get("status") != "success":
                confirm_click["recipe"] = "layer_select"
                return self._with_steps(confirm_click, result["steps"])
            if not str((target or {}).get("query") or "").strip():
                return self._component_not_ready(
                    "layer_select",
                    "Selection cannot be verified for an index target after confirming the option.",
                    recovery_args=recovery_args,
                    steps=result["steps"],
                )
        return result

    def _table_locate(
        self,
        driver: Any,
        *,
        table: dict[str, Any] | None,
        max_results: int,
        switch_tab_id: str | None = None,
    ) -> dict[str, Any]:
        table = table or {}
        if not any(table.get(key) for key in ("row_text", "column_text", "header_text")):
            return failed_result(None, "invalid_args", "table_locate requires row_text, column_text, or header_text.")

        result = self.layer.find(driver, table=table, max_results=max_results, **self._tab_kwargs(switch_tab_id))
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
        switch_tab_id: str | None,
    ) -> dict[str, Any]:
        if condition not in SUPPORTED_CONDITIONS:
            return failed_result(None, "invalid_args", f"Unsupported browser recipe condition: {condition}")
        safe_timeout = _safe_timeout(timeout)
        if isinstance(target, dict) and target.get("index") is not None:
            target_index = self._target_index(target)
            if target_index is None:
                result = failed_result(None, "invalid_args", "target.index must be a positive integer.")
                result["recipe"] = "component_wait"
                result["recovery"] = self._bounded_target_recovery("component_wait")
                return result
            result = failed_result(
                None,
                "invalid_args",
                "component_wait does not accept target.index; use browser_action wait_index/wait_enabled or a query target.",
            )
            result["recipe"] = "component_wait"
            next_args: dict[str, Any]
            if condition in {"element_enabled", "layer_open", "options_visible"}:
                result["recovery"]["code"] = "use_indexed_wait_action"
                result["recovery"]["next_tool"] = "browser_action"
                next_args = {
                    "action": "wait_enabled" if condition == "element_enabled" else "wait_index",
                    "index": target_index,
                    "timeout": safe_timeout,
                }
            elif str(target.get("query") or "").strip():
                result["recovery"]["code"] = "use_query_component_wait"
                result["recovery"]["next_tool"] = "browser_recipe"
                next_args = {
                    "recipe": "component_wait",
                    "condition": condition,
                    "target": {"query": str(target.get("query") or "").strip()},
                    "timeout": safe_timeout,
                }
            else:
                result["recovery"]["code"] = "use_query_component_wait"
                result["recovery"]["message"] = "Refresh state and retry component_wait with a query target; indexed waits cannot express this condition."
                result["recovery"]["next_tool"] = "browser_state"
                next_args = {}
            if switch_tab_id:
                next_args["switch_tab_id"] = switch_tab_id
            result["recovery"]["next_args"] = next_args
            return result
        target_error = self._validate_target("component_wait", target)
        if target_error:
            return target_error

        deadline = time.monotonic() + safe_timeout
        poll_interval = max(0, float(self._component_wait_poll_interval))
        steps: list[dict[str, Any]] = []
        last_find: dict[str, Any] | None = None

        while True:
            state = self.layer.get_state(driver, max_elements=120, **self._tab_kwargs(switch_tab_id))
            steps.append({"tool": "browser_state", "status": state.get("status")})
            if state.get("status") != "success":
                state["recipe"] = "component_wait"
                return self._with_steps(state, steps)

            find_result, match = self._find_one(
                driver,
                recipe="component_wait",
                target=target,
                max_results=max_results,
                switch_tab_id=switch_tab_id,
            )
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
                if condition in {"layer_closed", "not_busy"} and find_result.get("stage") == "ambiguous_target":
                    pass
                elif find_result.get("stage") == "target_not_found":
                    pass
                else:
                    find_result["recipe"] = "component_wait"
                    return self._with_steps(find_result, steps)
            else:
                match = self._match_for_condition(condition, find_result.get("matches") or [], match)
            if find_result.get("status") == "success" and self._component_condition_met(condition, match):
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
        if switch_tab_id:
            next_args["switch_tab_id"] = switch_tab_id
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
        switch_tab_id: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        recipe = str(recipe or "").strip()
        if recipe not in SUPPORTED_RECIPES:
            return failed_result(None, "invalid_args", f"Unsupported browser recipe: {recipe}")
        if recipe == "custom_select":
            if not option_text:
                return failed_result(None, "invalid_args", "option_text is required for custom_select.")
            return self._custom_select(
                driver,
                target=target,
                option_text=option_text,
                timeout=timeout,
                max_results=max_results,
                switch_tab_id=switch_tab_id,
            )
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
                switch_tab_id=switch_tab_id,
            )
        if recipe == "table_locate":
            return self._table_locate(driver, table=table, max_results=max_results, switch_tab_id=switch_tab_id)
        return self._component_wait(
            driver,
            condition=condition or "",
            target=target,
            timeout=timeout,
            max_results=max_results,
            switch_tab_id=switch_tab_id,
        )
