import json
import os
from typing import Dict, Any

STATE_FILE = "data/state.json"

def load_state() -> Dict[str, Any]:
    """Loads the currently committed issuances from the state file."""
    if not os.path.exists(STATE_FILE):
        return {"committed_issuances": {}}
    
    # We do not catch JSON errors here. If the file is corrupted, 
    # we want the system to fail loudly so the maintainer is alerted (Section 3.8).
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_state(state_data: Dict[str, Any]) -> None:
    """Saves the state data back to the JSON file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state_data, f, indent=2)

def generate_state_key(regulator: str, identifier: str) -> str:
    """Generates a unique key for the state dictionary (e.g., 'BIR_RMC-2026-01')."""
    return f"{regulator}_{identifier}"

def is_issuance_known(regulator: str, identifier: str) -> bool:
    """Checks if an issuance is already processed and committed in the state."""
    state = load_state()
    key = generate_state_key(regulator, identifier)
    return key in state.get("committed_issuances", {})

def commit_issuance_to_state(regulator: str, identifier: str, record_data: Dict[str, Any]) -> None:
    """Adds a newly notified issuance to the state file and saves it (Section 3.6)."""
    state = load_state()
    key = generate_state_key(regulator, identifier)
    
    if "committed_issuances" not in state:
        state["committed_issuances"] = {}
        
    state["committed_issuances"][key] = record_data
    save_state(state)
