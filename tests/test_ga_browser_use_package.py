import browser_actions
import browser_indexer
from ga_browser_use import actions, indexer


def test_root_browser_indexer_reexports_package_functions():
    assert browser_indexer.build_browser_state_script is indexer.build_browser_state_script
    assert browser_indexer.normalize_state_result is indexer.normalize_state_result


def test_root_browser_actions_reexports_package_layer():
    assert browser_actions.BrowserActionLayer is actions.BrowserActionLayer
    assert browser_actions.build_browser_action_script is actions.build_browser_action_script
    assert browser_actions.SUPPORTED_ACTIONS == actions.SUPPORTED_ACTIONS
