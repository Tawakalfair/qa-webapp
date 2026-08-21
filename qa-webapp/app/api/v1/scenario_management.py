"""
Bridge module for backward compatibility.
All scenario endpoints and workers have been unified into app.api.v1.scenarios.
"""
from app.api.v1.scenarios import (
    router,
    BATCH_STATUS,
    run_selected_scenarios,
    _async_run_selected_scenarios,
    render_scenario_inventory,
    render_scenario_table_partial,
    render_scenario_detail_modal,
    save_scenario_detail_modal,
    render_bulk_copy_modal,
    process_bulk_copy,
    process_bulk_delete,
    process_bulk_run,
    get_batch_progress
)